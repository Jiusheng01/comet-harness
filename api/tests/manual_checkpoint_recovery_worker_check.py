import asyncio
import uuid

from sqlalchemy import delete, select, text

import app.core.harness.recovery as recovery_module
from app.core.harness.checkpoint.models import HarnessCheckpoint
from app.core.harness.checkpoint.postgres_store import (
    PostgresCheckpointStore,
)
from app.core.harness.recovery import (
    CheckpointRecoveryWorker,
)
from app.core.harness.runtime.contracts import (
    HarnessMessage,
)
from app.db.postgres import SessionLocal
from app.models.conversation_model import (
    ROLE_ASSISTANT,
    ROLE_USER,
    Conversation,
    Message,
)
from app.services.chat_service import ChatService


async def main() -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id FROM users "
                "ORDER BY created_at ASC "
                "LIMIT 1"
            )
        )

        user_id = result.scalar_one_or_none()

    if user_id is None:
        raise RuntimeError(
            "users 表为空，无法执行 recovery worker 测试"
        )

    conv_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    skill_id = uuid.uuid4()

    original_has_lease = (
        recovery_module.bus.has_execution_lease
    )

    original_acquire_lock = (
        recovery_module.bus.acquire_turn_lock_strict
    )

    original_refresh_lease = (
        recovery_module.bus.refresh_execution_lease
    )

    original_run_bg = (
        ChatService._run_chat_turn_bg
    )

    seen: list[dict] = []

    async def fake_has_lease(
        turn_key: str,
    ) -> bool:
        return False

    async def fake_acquire_lock(
        conv_key: str,
    ) -> bool:
        return True

    async def fake_refresh_lease(
        turn_key: str,
    ) -> bool:
        return True

    async def fake_run_bg(
        self,
        recovered_user_id,
        recovered_conv_id,
        body,
        attachments,
        skip_user_message,
        recovered_turn_id,
    ) -> None:
        seen.append(
            {
                "user_id": recovered_user_id,
                "conv_id": recovered_conv_id,
                "body": body,
                "attachments": attachments,
                "skip_user_message": (
                    skip_user_message
                ),
                "turn_id": recovered_turn_id,
            }
        )

        # 模拟真实 ChatService 最终 ACK。
        async with SessionLocal() as session:
            store = PostgresCheckpointStore(
                session,
                recovered_user_id,
            )

            await store.delete(
                recovered_turn_id
            )

    recovery_module.bus.has_execution_lease = (
        fake_has_lease
    )

    recovery_module.bus.acquire_turn_lock_strict = (
        fake_acquire_lock
    )

    recovery_module.bus.refresh_execution_lease = (
        fake_refresh_lease
    )

    ChatService._run_chat_turn_bg = (
        fake_run_bg
    )

    try:
        # Phase 1:
        # 创建一条真实 PostgreSQL user turn + checkpoint。
        async with SessionLocal() as session:
            session.add(
                Conversation(
                    id=conv_id,
                    user_id=user_id,
                    title="Harness Recovery Test",
                )
            )

            session.add(
                Message(
                    id=turn_id,
                    conversation_id=conv_id,
                    role=ROLE_USER,
                    content="恢复这次 Harness 执行",
                    meta_data={
                        "attachments": [
                            {
                                "file_name": "recovery.txt",
                                "text": "durable attachment",
                            }
                        ],
                        "image_keys": [],
                        "harness_request": {
                            "version": 1,
                            "skill_id": str(
                                skill_id
                            ),
                            "enable_knowledge": True,
                            "enable_memory": False,
                            "enable_web_search": True,
                        },
                    },
                )
            )

            await session.commit()

        async with SessionLocal() as session:
            store = PostgresCheckpointStore(
                session,
                user_id,
            )

            await store.save(
                HarnessCheckpoint(
                    checkpoint_id=turn_id,
                    runtime="function_calling",
                    next_iteration=1,
                    messages=[
                        HarnessMessage(
                            role="user",
                            content=(
                                "恢复这次 Harness 执行"
                            ),
                        )
                    ],
                    user_input=(
                        "恢复这次 Harness 执行"
                    ),
                    max_iterations=5,
                    metadata={
                        "model_name": "fake-model",
                    },
                )
            )

        worker = CheckpointRecoveryWorker(
            scan_interval=999,
        )

        await worker.recover_once(
            {turn_id}
        )

        await worker.wait_for_idle()

        assert len(seen) == 1

        call = seen[0]
        body = call["body"]

        assert call["user_id"] == user_id
        assert call["conv_id"] == conv_id
        assert call["turn_id"] == turn_id
        assert (
            call["skip_user_message"]
            is True
        )

        assert body.skill_id == skill_id
        assert body.enable_knowledge is True
        assert body.enable_memory is False
        assert body.enable_web_search is True
        assert len(body.attachments) == 1
        assert (
            body.attachments[0].text
            == "durable attachment"
        )

        async with SessionLocal() as session:
            store = PostgresCheckpointStore(
                session,
                user_id,
            )

            assert (
                await store.load(turn_id)
                is None
            )

        print(
            "recovery scheduled: True"
        )
        print(
            "request snapshot restored: True"
        )
        print(
            "skill restored: True"
        )
        print(
            "tool overrides restored: True"
        )

        # Phase 2:
        # 模拟 assistant 已成功落库，
        # 但进程在 checkpoint ACK 前死亡。
        #
        # Worker 应只清 checkpoint，绝不能再次调用生成。
        async with SessionLocal() as session:
            store = PostgresCheckpointStore(
                session,
                user_id,
            )

            await store.save(
                HarnessCheckpoint(
                    checkpoint_id=turn_id,
                    runtime="function_calling",
                    next_iteration=1,
                    messages=[
                        HarnessMessage(
                            role="user",
                            content=(
                                "恢复这次 Harness 执行"
                            ),
                        )
                    ],
                    user_input=(
                        "恢复这次 Harness 执行"
                    ),
                    max_iterations=5,
                    metadata={
                        "model_name": "fake-model",
                    },
                )
            )

        async with SessionLocal() as session:
            session.add(
                Message(
                    conversation_id=conv_id,
                    role=ROLE_ASSISTANT,
                    content="已经持久化的最终回答",
                    meta_data={
                        "turn_id": str(
                            turn_id
                        ),
                    },
                )
            )

            await session.commit()

        seen.clear()

        await worker.recover_once(
            {turn_id}
        )

        await worker.wait_for_idle()

        assert seen == []

        async with SessionLocal() as session:
            store = PostgresCheckpointStore(
                session,
                user_id,
            )

            assert (
                await store.load(turn_id)
                is None
            )

        print(
            "completed turn regenerated: False"
        )
        print(
            "stale ACK checkpoint cleaned: True"
        )
        print()
        print(
            "Checkpoint recovery worker check passed."
        )

    finally:
        recovery_module.bus.has_execution_lease = (
            original_has_lease
        )

        recovery_module.bus.acquire_turn_lock_strict = (
            original_acquire_lock
        )

        recovery_module.bus.refresh_execution_lease = (
            original_refresh_lease
        )

        ChatService._run_chat_turn_bg = (
            original_run_bg
        )

        async with SessionLocal() as session:
            try:
                store = (
                    PostgresCheckpointStore(
                        session,
                        user_id,
                    )
                )

                await store.delete(
                    turn_id
                )

            except Exception:
                await session.rollback()

            await session.execute(
                delete(Conversation).where(
                    Conversation.id
                    == conv_id
                )
            )

            await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
