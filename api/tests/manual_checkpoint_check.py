import asyncio
import uuid

from app.core.harness.checkpoint import (
    HarnessCheckpoint,
    InMemoryCheckpointStore,
)
from app.core.harness.runtime import HarnessMessage


async def main() -> None:
    store = InMemoryCheckpointStore()

    checkpoint_id = uuid.uuid4()

    messages = [
        HarnessMessage(
            role="system",
            content="你是一个测试 Agent。",
        ),
        HarnessMessage(
            role="user",
            content="帮我查询当前时间。",
        ),
    ]

    checkpoint = HarnessCheckpoint(
        checkpoint_id=checkpoint_id,
        runtime="function_calling",
        next_iteration=1,
        messages=messages,
        max_iterations=5,
    )

    # 保存 checkpoint
    await store.save(checkpoint)

    # 模拟 Runtime 在保存后继续修改原始状态。
    messages.append(
        HarnessMessage(
            role="assistant",
            content="这条不应该出现在旧 checkpoint 中。",
        )
    )

    # 模拟“进程恢复”读取 checkpoint。
    restored = await store.load(checkpoint_id)

    assert restored is not None
    assert restored.runtime == "function_calling"
    assert restored.next_iteration == 1
    assert restored.max_iterations == 5
    assert len(restored.messages) == 2
    assert restored.messages[-1].content == "帮我查询当前时间。"

    print("checkpoint_id:", restored.checkpoint_id)
    print("runtime:", restored.runtime)
    print("next_iteration:", restored.next_iteration)
    print("messages:", len(restored.messages))
    print()
    print("Checkpoint restore check passed.")

    await store.delete(checkpoint_id)

    assert await store.load(checkpoint_id) is None


if __name__ == "__main__":
    asyncio.run(main())