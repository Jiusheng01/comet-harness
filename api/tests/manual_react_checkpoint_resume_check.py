import asyncio
import uuid
from contextlib import asynccontextmanager

import app.core.harness.runtime.react_runtime as react_runtime_module
from app.core.harness.checkpoint import InMemoryCheckpointStore
from app.core.harness.context import ContextManager
from app.core.harness.runtime.react_runtime import ReactRuntime
from app.core.harness.runtime.contracts import (
    ExecutionContext,
    HarnessMessage,
    ModelStreamEvent,
    ModelTurn,
)


class FakeSpan:
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
        assert args["query"] == "current time"

        return FakeToolResult(
            "2026-08-14 09:37:00"
        )


class CrashAfterToolModel:
    """第一轮产生 Action，第二轮模拟崩溃。"""

    def __init__(self) -> None:
        self.call_count = 0

    @property
    def model_name(self) -> str:
        return "fake-react-crash-model"

    async def stream(self, messages, tools):
        self.call_count += 1

        if self.call_count == 1:
            yield ModelStreamEvent(
                type="completed",
                turn=ModelTurn(
                    text=(
                        "Thought: 我需要查询当前时间。\n"
                        "Action: datetime\n"
                        "Action Input: current time"
                    )
                ),
            )
            return

        raise RuntimeError("simulated react crash")


class ResumeModel:
    """恢复后读取 Observation，直接生成 Final Answer。"""

    def __init__(self) -> None:
        self.call_count = 0
        self.seen_messages = []

    @property
    def model_name(self) -> str:
        return "fake-react-resume-model"

    async def stream(self, messages, tools):
        self.call_count += 1
        self.seen_messages = list(messages)

        yield ModelStreamEvent(
            type="completed",
            turn=ModelTurn(
                text=(
                    "Thought: 已经获得工具结果。\n"
                    "Final Answer: 当前时间是 "
                    "2026-08-14 09:37:00。"
                )
            ),
        )


async def main() -> None:
    original_get_tracer = react_runtime_module.get_tracer
    react_runtime_module.get_tracer = lambda: FakeTracer()

    try:
        store = InMemoryCheckpointStore()
        tool_executor = CountingToolExecutor()
        checkpoint_id = uuid.uuid4()

        ctx = ExecutionContext(
            messages=[
                HarnessMessage(
                    role="system",
                    content="你是一个测试 ReAct Agent。",
                ),
                HarnessMessage(
                    role="user",
                    content="现在几点？",
                ),
            ],
            user_input="现在几点？",
            max_iterations=5,
        )

        # 第一阶段：执行一轮并模拟中断。
        crash_model = CrashAfterToolModel()

        runtime = ReactRuntime(
            model=crash_model,
            tool_executor=tool_executor,
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
            assert str(exc) == "simulated react crash"
            crashed = True

        assert crashed

        # 已完成的工具只能执行一次。
        assert tool_executor.call_count == 1

        checkpoint = await store.load(checkpoint_id)

        assert checkpoint is not None
        assert checkpoint.runtime == "react"
        assert checkpoint.next_iteration == 1

        # system + user + assistant(Action) + user(Observation)
        assert len(checkpoint.messages) == 4

        assert checkpoint.messages[-2].role == "assistant"
        assert "Action: datetime" in checkpoint.messages[-2].content

        assert checkpoint.messages[-1].role == "user"
        assert checkpoint.messages[-1].content.startswith(
            "Observation:"
        )
        assert (
            "2026-08-14 09:37:00"
            in checkpoint.messages[-1].content
        )

        print("phase 1: simulated react crash")
        print(
            "checkpoint next_iteration:",
            checkpoint.next_iteration,
        )
        print(
            "tool calls before resume:",
            tool_executor.call_count,
        )

        # 第二阶段：新建 Runtime 并恢复。
        resume_model = ResumeModel()

        resumed_runtime = ReactRuntime(
            model=resume_model,
            tool_executor=tool_executor,
            context_manager=ContextManager(),
            checkpoint_store=store,
        )

        resumed_events = []

        async for event in resumed_runtime.resume(
            checkpoint_id
        ):
            resumed_events.append(event)

        # 恢复后不能重新执行 datetime。
        assert tool_executor.call_count == 1

        assert resume_model.call_count == 1
        assert resume_model.seen_messages

        last_message = resume_model.seen_messages[-1]

        assert last_message.role == "user"
        assert last_message.content.startswith(
            "Observation:"
        )

        final_events = [
            event
            for event in resumed_events
            if event["type"] == "final"
        ]

        assert len(final_events) == 1
        assert (
            final_events[0]["text"]
            == "当前时间是 2026-08-14 09:37:00。"
        )

        # 正常完成后 checkpoint 应删除。
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
            "ReAct checkpoint runtime resume check passed."
        )

    finally:
        react_runtime_module.get_tracer = original_get_tracer


if __name__ == "__main__":
    asyncio.run(main())