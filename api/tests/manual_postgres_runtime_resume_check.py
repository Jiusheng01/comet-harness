import asyncio
import uuid
from contextlib import asynccontextmanager

from sqlalchemy import text

import app.core.harness.runtime.agent_runtime as agent_runtime_module
from app.core.harness.checkpoint import PostgresCheckpointStore
from app.core.harness.context import ContextManager
from app.core.harness.runtime.agent_runtime import AgentRuntime
from app.core.harness.runtime.contracts import (
    ExecutionContext,
    HarnessMessage,
    ModelStreamEvent,
    ModelTurn,
    ToolCall,
)
from app.db.postgres import SessionLocal


class FakeSpan:
    """避免手动测试依赖真实 tracing。"""

    def set_payload(self, *args, **kwargs) -> None:
        pass

    def set_tokens(self, *args, **kwargs) -> None:
        pass


class FakeTracer:
    @asynccontextmanager
    async def llm_span(self, *args, **kwargs):
        yield FakeSpan()


class FakeToolResult:
    def __init__(self, content: str) -> None:
        self.content = content

    def to_event(self) -> dict:
        return {
            "type": "tool_result",
            "tool": "datetime",
            "status": "ok",
            "content": self.content,
        }


class CountingToolExecutor:
    """记录当前 Runtime 实例实际执行了多少次工具。"""

    def __init__(self) -> None:
        self.call_count = 0

    async def execute(
        self,
        *,
        tool_name: str,
        args: dict,
    ) -> FakeToolResult:
        self.call_count += 1

        assert tool_name == "datetime"

        return FakeToolResult(
            "2026-08-14 10:56:00"
        )


class CrashAfterToolModel:
    """第一轮请求工具，下一轮模拟进程异常。"""

    def __init__(self) -> None:
        self.call_count = 0

    @property
    def model_name(self) -> str:
        return "fake-crash-model"

    async def stream(self, messages, tools):
        self.call_count += 1

        # 第 0 轮：调用 datetime。
        if self.call_count == 1:
            yield ModelStreamEvent(
                type="completed",
                turn=ModelTurn(
                    tool_calls=[
                        ToolCall(
                            id="call_datetime_1",
                            name="datetime",
                            arguments={
                                "query": "current time",
                            },
                        )
                    ]
                ),
            )
            return

        # 第 1 轮开始前，上一轮稳定 checkpoint
        # 已经保存到 PostgreSQL。
        raise RuntimeError(
            "simulated process crash"
        )


class ResumeModel:
    """恢复后的新模型实例：读取旧 tool result 后直接完成。"""

    def __init__(self) -> None:
        self.call_count = 0
        self.seen_messages = []

    @property
    def model_name(self) -> str:
        return "fake-resume-model"

    async def stream(self, messages, tools):
        self.call_count += 1
        self.seen_messages = list(messages)

        yield ModelStreamEvent(
            type="completed",
            turn=ModelTurn(
                text="当前时间是 2026-08-14 10:56:00。"
            ),
        )


async def get_test_user_id() -> uuid.UUID:
    async with SessionLocal() as session:
        result = await session.execute(
            text("SELECT id FROM users LIMIT 1")
        )

        value = result.scalar_one_or_none()

    if value is None:
        raise RuntimeError(
            "users 表没有用户，无法测试 user_id 外键"
        )

    return uuid.UUID(str(value))


async def main() -> None:
    user_id = await get_test_user_id()
    checkpoint_id = uuid.uuid4()

    original_get_tracer = (
        agent_runtime_module.get_tracer
    )

    agent_runtime_module.get_tracer = (
        lambda: FakeTracer()
    )

    try:
        # ============================================================
        # Phase 1
        # Session A + Runtime A
        #
        # 执行工具 -> PostgreSQL checkpoint -> 模拟异常
        # ============================================================

        first_tool_executor = (
            CountingToolExecutor()
        )

        crash_model = CrashAfterToolModel()

        ctx = ExecutionContext(
            messages=[
                HarnessMessage(
                    role="system",
                    content="你是一个测试 Agent。",
                ),
                HarnessMessage(
                    role="user",
                    content="现在几点？",
                ),
            ],
            max_iterations=5,
        )

        crashed = False

        async with SessionLocal() as session:
            first_store = (
                PostgresCheckpointStore(
                    session=session,
                    user_id=user_id,
                )
            )

            first_runtime = AgentRuntime(
                model=crash_model,
                tool_executor=first_tool_executor,
                model_tools=[],
                context_manager=ContextManager(),
                checkpoint_store=first_store,
            )

            try:
                async for _event in (
                    first_runtime.run(
                        ctx,
                        checkpoint_id=checkpoint_id,
                    )
                ):
                    pass

            except RuntimeError as exc:
                assert (
                    str(exc)
                    == "simulated process crash"
                )
                crashed = True

            assert crashed

            # 第一阶段工具只执行一次。
            assert (
                first_tool_executor.call_count
                == 1
            )

            checkpoint = await first_store.load(
                checkpoint_id
            )

            assert checkpoint is not None
            assert (
                checkpoint.runtime
                == "function_calling"
            )
            assert (
                checkpoint.next_iteration
                == 1
            )

            assert (
                checkpoint.messages[-2].role
                == "assistant"
            )
            assert (
                checkpoint.messages[-2].tool_calls
            )

            assert (
                checkpoint.messages[-1].role
                == "tool"
            )
            assert (
                checkpoint.messages[-1].content
                == "2026-08-14 10:56:00"
            )

        # 到这里 Session A 已经关闭。
        print(
            "phase 1: simulated process crash"
        )
        print(
            "tool calls before crash:",
            first_tool_executor.call_count,
        )

        # ============================================================
        # Phase 2
        # Session B
        #
        # 验证旧 Session 关闭后 checkpoint 仍存在。
        # ============================================================

        async with SessionLocal() as session:
            persisted_store = (
                PostgresCheckpointStore(
                    session=session,
                    user_id=user_id,
                )
            )

            persisted = (
                await persisted_store.load(
                    checkpoint_id
                )
            )

            assert persisted is not None
            assert (
                persisted.next_iteration
                == 1
            )

        # Session B 也关闭。
        print(
            "checkpoint survived new session: True"
        )
        print(
            "checkpoint next_iteration:",
            persisted.next_iteration,
        )

        # ============================================================
        # Phase 3
        # Session C + Runtime B + ToolExecutor B + Model B
        #
        # 全部重新创建，只从 PostgreSQL checkpoint 恢复。
        # ============================================================

        second_tool_executor = (
            CountingToolExecutor()
        )

        resume_model = ResumeModel()

        resumed_events: list[dict] = []

        async with SessionLocal() as session:
            resumed_store = (
                PostgresCheckpointStore(
                    session=session,
                    user_id=user_id,
                )
            )

            resumed_runtime = AgentRuntime(
                model=resume_model,
                tool_executor=(
                    second_tool_executor
                ),
                model_tools=[],
                context_manager=ContextManager(),
                checkpoint_store=resumed_store,
            )

            async for event in (
                resumed_runtime.resume(
                    checkpoint_id
                )
            ):
                resumed_events.append(event)

        # 这是一个全新的 ToolExecutor。
        #
        # 如果恢复逻辑错误地重跑第 0 轮工具，
        # 这里就会变成 1。
        assert (
            second_tool_executor.call_count
            == 0
        )

        assert resume_model.call_count == 1
        assert resume_model.seen_messages

        # 新模型应该直接看到 PostgreSQL 恢复出来的
        # tool result。
        assert (
            resume_model.seen_messages[-1].role
            == "tool"
        )

        assert (
            resume_model.seen_messages[-1].content
            == "2026-08-14 10:56:00"
        )

        final_events = [
            event
            for event in resumed_events
            if event["type"] == "final"
        ]

        assert len(final_events) == 1

        assert (
            final_events[0]["text"]
            == "当前时间是 2026-08-14 10:56:00。"
        )

        # ============================================================
        # Phase 4
        # Session D
        #
        # 正常完成以后 checkpoint 应被 Runtime 删除。
        # ============================================================

        async with SessionLocal() as session:
            verify_store = (
                PostgresCheckpointStore(
                    session=session,
                    user_id=user_id,
                )
            )

            missing = await verify_store.load(
                checkpoint_id
            )

        assert missing is None

        print(
            "resume final:",
            final_events[0]["text"],
        )
        print(
            "new runtime tool calls:",
            second_tool_executor.call_count,
        )
        print(
            "checkpoint deleted after resume: True"
        )
        print()
        print(
            "Postgres runtime resume check passed."
        )

    finally:
        agent_runtime_module.get_tracer = (
            original_get_tracer
        )

        # 如果测试中途 assert 失败，
        # 尽量清理残留测试 checkpoint。
        try:
            async with SessionLocal() as session:
                cleanup_store = (
                    PostgresCheckpointStore(
                        session=session,
                        user_id=user_id,
                    )
                )

                await cleanup_store.delete(
                    checkpoint_id
                )

        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())