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


class NoopToolExecutor:
    async def execute(self, **kwargs):
        raise AssertionError(
            "final-only model must not execute tools"
        )


class FinalOnlyModel:
    @property
    def model_name(self) -> str:
        return "fake-final-only-model"

    async def stream(self, messages, tools):
        yield ModelStreamEvent(
            type="completed",
            turn=ModelTurn(
                text="ACK boundary works."
            ),
        )


async def main() -> None:
    original_get_tracer = (
        agent_runtime_module.get_tracer
    )

    agent_runtime_module.get_tracer = (
        lambda: FakeTracer()
    )

    try:
        checkpoint_id = uuid.uuid4()
        store = InMemoryCheckpointStore()

        runtime = AgentRuntime(
            model=FinalOnlyModel(),
            tool_executor=NoopToolExecutor(),
            model_tools=[],
            context_manager=ContextManager(),
            checkpoint_store=store,
        )

        ctx = ExecutionContext(
            messages=[
                HarnessMessage(
                    role="user",
                    content="test ACK boundary",
                ),
            ],
            max_iterations=5,
        )

        events = []

        async for event in runtime.run(
            ctx,
            checkpoint_id=checkpoint_id,
            cleanup_checkpoint_on_finish=False,
        ):
            events.append(event)

        final_events = [
            event
            for event in events
            if event["type"] == "final"
        ]

        assert len(final_events) == 1
        assert (
            final_events[0]["text"]
            == "ACK boundary works."
        )

        # Even though the model completed without any tool call,
        # the initial checkpoint must still exist until business ACK.
        checkpoint = await store.load(
            checkpoint_id
        )

        assert checkpoint is not None
        assert checkpoint.next_iteration == 0
        assert (
            checkpoint.runtime
            == "function_calling"
        )

        print(
            "checkpoint retained after final: True"
        )
        print(
            "checkpoint next_iteration:",
            checkpoint.next_iteration,
        )

        # Simulate ChatService successfully persisting
        # the assistant message and ACKing the checkpoint.
        await store.delete(checkpoint_id)

        assert (
            await store.load(checkpoint_id)
            is None
        )

        print(
            "checkpoint deleted after business ACK: True"
        )
        print()
        print(
            "Checkpoint ACK boundary check passed."
        )

    finally:
        agent_runtime_module.get_tracer = (
            original_get_tracer
        )


if __name__ == "__main__":
    asyncio.run(main())
