import asyncio
import uuid
from contextlib import asynccontextmanager

import app.core.harness.runtime.agent_runtime as agent_runtime_module
from app.core.harness.checkpoint import InMemoryCheckpointStore
from app.core.harness.context import ContextManager
from app.core.harness.runtime.agent_runtime import AgentRuntime
from app.core.harness.runtime.contracts import (
    ExecutionContext,
    HarnessMessage,
    ModelStreamEvent,
    ModelTurn,
    ToolCall,
)


class FakeSpan:
    """避免手动测试依赖真实 tracing / DB。"""

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
    """记录工具实际执行了多少次。"""

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
            "2026-08-14 09:24:00"
        )


class CrashAfterToolModel:
    """第一轮请求工具，第二轮模拟进程异常。"""

    def __init__(self) -> None:
        self.call_count = 0

    @property
    def model_name(self) -> str:
        return "fake-crash-model"

    async def stream(self, messages, tools):
        self.call_count += 1

        # 第 0 轮：请求 datetime 工具。
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

        # 第 1 轮：checkpoint 已经保存，
        # 在下一次模型调用时模拟进程崩溃。
        raise RuntimeError("simulated crash")


class ResumeModel:
    """恢复后的模型：读取已有 tool result，直接给最终答案。"""

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
                text="当前时间是 2026-08-14 09:24:00。"
            ),
        )


async def main() -> None:
    # 手动测试不需要真实 tracing。
    original_get_tracer = agent_runtime_module.get_tracer
    agent_runtime_module.get_tracer = lambda: FakeTracer()

    try:
        store = InMemoryCheckpointStore()
        tool_executor = CountingToolExecutor()
        checkpoint_id = uuid.uuid4()

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

        # ── 第一阶段：运行，然后模拟中断 ──

        crash_model = CrashAfterToolModel()

        runtime = AgentRuntime(
            model=crash_model,
            tool_executor=tool_executor,
            model_tools=[],
            context_manager=ContextManager(),
            checkpoint_store=store,
        )

        crashed = False

        try:
            async for _event in runtime.run(
                ctx,
                checkpoint_id=checkpoint_id,
            ):
                pass
        except RuntimeError as exc:
            assert str(exc) == "simulated crash"
            crashed = True

        assert crashed

        # 工具在中断前只应该执行一次。
        assert tool_executor.call_count == 1

        checkpoint = await store.load(checkpoint_id)

        assert checkpoint is not None
        assert checkpoint.runtime == "function_calling"

        # 第 0 轮已经完整完成，
        # 所以恢复应该从 iteration 1 开始。
        assert checkpoint.next_iteration == 1

        # 原始 system + user
        # 再加 assistant(tool_calls) + tool(result)
        assert len(checkpoint.messages) == 4

        assert checkpoint.messages[-2].role == "assistant"
        assert checkpoint.messages[-2].tool_calls
        assert checkpoint.messages[-1].role == "tool"
        assert (
            checkpoint.messages[-1].content
            == "2026-08-14 09:24:00"
        )

        print("phase 1: simulated crash")
        print(
            "checkpoint next_iteration:",
            checkpoint.next_iteration,
        )
        print(
            "tool calls before resume:",
            tool_executor.call_count,
        )

        # ── 第二阶段：创建一个新的 Runtime 恢复 ──

        resume_model = ResumeModel()

        resumed_runtime = AgentRuntime(
            model=resume_model,
            tool_executor=tool_executor,
            model_tools=[],
            context_manager=ContextManager(),
            checkpoint_store=store,
        )

        resumed_events = []

        async for event in resumed_runtime.resume(
            checkpoint_id
        ):
            resumed_events.append(event)

        # 恢复以后不应该重新执行之前的 datetime 工具。
        assert tool_executor.call_count == 1

        # 恢复模型应该看到已经保存的 tool result。
        assert resume_model.call_count == 1
        assert resume_model.seen_messages
        assert resume_model.seen_messages[-1].role == "tool"
        assert (
            resume_model.seen_messages[-1].content
            == "2026-08-14 09:24:00"
        )

        final_events = [
            event
            for event in resumed_events
            if event["type"] == "final"
        ]

        assert len(final_events) == 1
        assert (
            final_events[0]["text"]
            == "当前时间是 2026-08-14 09:24:00。"
        )

        # 正常结束后 checkpoint 应该被清理。
        assert await store.load(checkpoint_id) is None

        print(
            "resume final:",
            final_events[0]["text"],
        )
        print(
            "tool calls after resume:",
            tool_executor.call_count,
        )
        print("checkpoint deleted: True")
        print()
        print(
            "Checkpoint runtime resume check passed."
        )

    finally:
        agent_runtime_module.get_tracer = original_get_tracer


if __name__ == "__main__":
    asyncio.run(main())