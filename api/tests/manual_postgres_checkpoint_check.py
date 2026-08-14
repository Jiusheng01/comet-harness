import asyncio
import uuid

from sqlalchemy import text

from app.core.harness.checkpoint import (
    HarnessCheckpoint,
    PostgresCheckpointStore,
)
from app.core.harness.runtime import (
    HarnessMessage,
    ToolCall,
)
from app.db.postgres import SessionLocal


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

    checkpoint = HarnessCheckpoint(
        checkpoint_id=checkpoint_id,
        runtime="function_calling",
        next_iteration=1,
        messages=[
            HarnessMessage(
                role="user",
                content="现在几点？",
            ),
            HarnessMessage(
                role="assistant",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="datetime",
                        arguments={
                            "query": "current time",
                        },
                    )
                ],
            ),
            HarnessMessage(
                role="tool",
                content="2026-08-14 10:10:00",
                tool_call_id="call_1",
            ),
        ],
        user_input="现在几点？",
        max_iterations=5,
        metadata={
            "model_name": "qwen-test",
        },
    )

    # 第一阶段：保存。
    async with SessionLocal() as session:
        store = PostgresCheckpointStore(
            session=session,
            user_id=user_id,
        )

        await store.save(checkpoint)

    print("saved:", checkpoint_id)

    # 第二阶段：重新创建 Session + Store。
    # 证明不是依赖 Python 内存对象。
    async with SessionLocal() as session:
        store = PostgresCheckpointStore(
            session=session,
            user_id=user_id,
        )

        restored = await store.load(
            checkpoint_id
        )

    assert restored is not None
    assert restored.checkpoint_id == checkpoint_id
    assert restored.runtime == "function_calling"
    assert restored.next_iteration == 1
    assert len(restored.messages) == 3

    assert restored.messages[1].tool_calls
    assert (
        restored.messages[1].tool_calls[0].name
        == "datetime"
    )

    assert restored.messages[2].role == "tool"
    assert (
        restored.messages[2].tool_call_id
        == "call_1"
    )

    print(
        "loaded after new session:",
        restored.checkpoint_id,
    )
    print(
        "next_iteration:",
        restored.next_iteration,
    )
    print(
        "messages:",
        len(restored.messages),
    )

    # 第三阶段：删除。
    async with SessionLocal() as session:
        store = PostgresCheckpointStore(
            session=session,
            user_id=user_id,
        )

        await store.delete(checkpoint_id)

    # 第四阶段：再用全新 Session 验证确实删除。
    async with SessionLocal() as session:
        store = PostgresCheckpointStore(
            session=session,
            user_id=user_id,
        )

        missing = await store.load(
            checkpoint_id
        )

    assert missing is None

    print("deleted: True")
    print()
    print(
        "Postgres checkpoint round-trip check passed."
    )


if __name__ == "__main__":
    asyncio.run(main())