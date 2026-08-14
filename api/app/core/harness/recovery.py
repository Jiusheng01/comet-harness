"""Harness checkpoint process-crash recovery worker.

职责：
1. 周期扫描 PostgreSQL 中尚未 ACK 的 Harness checkpoint。
2. Redis execution lease 仍存活时，认为原执行进程仍健康，不抢占。
3. lease 消失后，通过严格 conversation lock 抢占恢复权。
4. 根据 user message.meta_data.harness_request 重建原 ChatStreamRequest。
5. 复用 ChatService._run_chat_turn_bg()，最终仍走同一 Runtime.resume() 链路。
6. 如果 assistant 已经持久化但 checkpoint ACK 删除失败，只清理 checkpoint，
   不重复生成 assistant。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from app.core.harness.checkpoint.codec import decode_checkpoint
from app.core.harness.checkpoint.postgres_store import (
    PostgresCheckpointStore,
)
from app.core.logging import get_logger
from app.core.realtime import bus
from app.db.postgres import SessionLocal
from app.models.conversation_model import (
    ROLE_ASSISTANT,
    ROLE_USER,
    Conversation,
    Message,
)
from app.models.harness_checkpoint_model import (
    HarnessCheckpointRecord,
)
from app.schemas.chat_schema import ChatStreamRequest
from app.services.chat_service import ChatService


logger = get_logger(__name__)

_DEFAULT_SCAN_INTERVAL = 10.0
_SCAN_LIMIT = 50


@dataclass(slots=True)
class RecoveryCandidate:
    checkpoint_id: uuid.UUID
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    body: ChatStreamRequest
    attachments: list[dict]


class CheckpointRecoveryWorker:
    """后台扫描并恢复硬进程崩溃遗留的 Harness checkpoint。

    注意：
    ChatService 捕获到的普通业务异常会把 checkpoint 标记为
    auto_recover=False，因此不会形成无限自动重试。

    真正的进程硬崩溃来不及写这个标记，Redis lease 过期后，
    才会被本 Worker 自动接管。
    """

    def __init__(
        self,
        *,
        scan_interval: float = _DEFAULT_SCAN_INTERVAL,
    ) -> None:
        self._scan_interval = scan_interval
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._recovery_tasks: set[asyncio.Task] = set()
        self._active_turn_ids: set[uuid.UUID] = set()
        self._warned_unrecoverable: set[uuid.UUID] = set()

    def is_running(self) -> bool:
        return (
            self._task is not None
            and not self._task.done()
        )

    async def start(self) -> None:
        if self.is_running():
            return

        self._stopping = False
        self._task = asyncio.create_task(
            self._run_loop(),
            name="harness_checkpoint_recovery",
        )

        logger.info(
            "Harness CheckpointRecoveryWorker 启动: scan_interval=%.1fs",
            self._scan_interval,
        )

    async def stop(self) -> None:
        self._stopping = True

        if self._task is not None:
            self._task.cancel()

            try:
                await self._task
            except asyncio.CancelledError:
                pass

            self._task = None

        active = list(self._recovery_tasks)

        for task in active:
            task.cancel()

        if active:
            await asyncio.gather(
                *active,
                return_exceptions=True,
            )

        self._recovery_tasks.clear()
        self._active_turn_ids.clear()

        logger.info(
            "Harness CheckpointRecoveryWorker 已停止"
        )

    async def wait_for_idle(self) -> None:
        """等待当前已经派出的恢复任务结束，主要用于测试/优雅收尾。"""

        tasks = list(self._recovery_tasks)

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

    async def _run_loop(self) -> None:
        while not self._stopping:
            try:
                await self.recover_once()

            except asyncio.CancelledError:
                raise

            except Exception as e:
                logger.exception(
                    "Harness checkpoint recovery scan failed: %s",
                    e,
                )

            await asyncio.sleep(
                self._scan_interval
            )

    async def recover_once(
        self,
        checkpoint_ids: set[uuid.UUID] | None = None,
    ) -> None:
        """执行一轮扫描。

        checkpoint_ids 仅用于手工测试精确限定扫描范围；
        生产 Worker 默认扫描所有 checkpoint。
        """

        candidates = await self._load_candidates(
            checkpoint_ids
        )

        for candidate in candidates:
            turn_id = candidate.checkpoint_id

            if turn_id in self._active_turn_ids:
                continue

            turn_key = str(turn_id)

            # 正常运行中的进程会持续刷新 execution lease。
            if await bus.has_execution_lease(
                turn_key
            ):
                continue

            cid = str(
                candidate.conversation_id
            )

            # Recovery 必须 fail-closed。
            # Redis 故障时宁可暂不恢复，也不能多 worker 重复执行。
            locked = await bus.acquire_turn_lock_strict(
                cid
            )

            if not locked:
                continue

            # 抢到 conversation lock 后立刻写 lease，
            # 尽量缩小多 worker 之间的竞争窗口。
            lease_ok = (
                await bus.refresh_execution_lease(
                    turn_key
                )
            )

            if not lease_ok:
                await bus.release_turn_lock(cid)
                continue

            self._active_turn_ids.add(
                turn_id
            )

            task = asyncio.create_task(
                self._run_candidate(
                    candidate
                ),
                name=(
                    "harness_recovery:"
                    f"{turn_id}"
                ),
            )

            self._recovery_tasks.add(task)

            task.add_done_callback(
                lambda finished,
                tid=turn_id: (
                    self._on_recovery_done(
                        tid,
                        finished,
                    )
                )
            )

            logger.warning(
                "Harness 自动恢复已接管: "
                "turn=%s conv=%s runtime checkpoint survived",
                turn_id,
                candidate.conversation_id,
            )

    def _on_recovery_done(
        self,
        turn_id: uuid.UUID,
        task: asyncio.Task,
    ) -> None:
        self._recovery_tasks.discard(
            task
        )

        self._active_turn_ids.discard(
            turn_id
        )

        if task.cancelled():
            return

        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return

        if exc is not None:
            logger.error(
                "Harness recovery task failed: "
                "turn=%s err=%s",
                turn_id,
                exc,
            )

    async def _run_candidate(
        self,
        candidate: RecoveryCandidate,
    ) -> None:
        """复用真实 Chat 后台执行链。

        _run_chat_turn_bg() 自己负责：
        - Runtime.resume()
        - assistant 落库
        - checkpoint ACK
        - stream buffer 清理
        - execution lease 清理
        - conversation lock 释放
        """

        entered_chat_runtime = False

        try:
            async with SessionLocal() as session:
                service = ChatService(
                    session
                )

                entered_chat_runtime = True

                await service._run_chat_turn_bg(
                    candidate.user_id,
                    candidate.conversation_id,
                    candidate.body,
                    candidate.attachments,
                    True,
                    candidate.checkpoint_id,
                )

        except asyncio.CancelledError:
            raise

        except Exception as e:
            logger.exception(
                "Harness recovery execution failed: "
                "turn=%s err=%s",
                candidate.checkpoint_id,
                e,
            )

        finally:
            # 正常情况下 ChatService 自己清理。
            # 只有在进入 ChatService 之前就异常时这里兜底。
            if not entered_chat_runtime:
                await bus.clear_execution_lease(
                    str(candidate.checkpoint_id)
                )

                await bus.release_turn_lock(
                    str(
                        candidate.conversation_id
                    )
                )

    async def _load_candidates(
        self,
        checkpoint_ids: set[uuid.UUID] | None,
    ) -> list[RecoveryCandidate]:
        candidates: list[RecoveryCandidate] = []

        async with SessionLocal() as session:
            stmt = (
                select(
                    HarnessCheckpointRecord
                )
                .order_by(
                    HarnessCheckpointRecord.updated_at.asc()
                )
                .limit(_SCAN_LIMIT)
            )

            if checkpoint_ids:
                stmt = stmt.where(
                    HarnessCheckpointRecord.id.in_(
                        checkpoint_ids
                    )
                )

            result = await session.execute(
                stmt
            )

            raw_records = [
                (
                    record.id,
                    record.user_id,
                    dict(record.payload),
                )
                for record
                in result.scalars().all()
            ]

            for (
                checkpoint_id,
                user_id,
                payload,
            ) in raw_records:
                try:
                    checkpoint = (
                        decode_checkpoint(
                            payload
                        )
                    )

                except Exception as e:
                    logger.error(
                        "无法解析 Harness checkpoint: "
                        "turn=%s err=%s",
                        checkpoint_id,
                        e,
                    )
                    continue

                user_message = (
                    await session.get(
                        Message,
                        checkpoint_id,
                    )
                )

                # turn_id 就是 user message id。
                # message 已不存在则业务任务本身也不存在，
                # checkpoint 可以安全回收。
                if (
                    user_message is None
                    or user_message.role
                    != ROLE_USER
                ):
                    await self._delete_checkpoint(
                        session,
                        user_id,
                        checkpoint_id,
                    )

                    logger.warning(
                        "清理孤儿 Harness checkpoint: "
                        "turn=%s",
                        checkpoint_id,
                    )
                    continue

                conversation = (
                    await session.get(
                        Conversation,
                        user_message.conversation_id,
                    )
                )

                if conversation is None:
                    await self._delete_checkpoint(
                        session,
                        user_id,
                        checkpoint_id,
                    )
                    continue

                if (
                    conversation.user_id
                    != user_id
                ):
                    logger.error(
                        "Harness checkpoint user mismatch: "
                        "turn=%s checkpoint_user=%s "
                        "conversation_user=%s",
                        checkpoint_id,
                        user_id,
                        conversation.user_id,
                    )
                    continue

                # 最关键的 ACK crash-window：
                #
                # assistant 已经落库，但是进程在 delete checkpoint
                # 前死亡。此时绝对不能再生成一次。
                if await self._has_completed_assistant(
                    session,
                    conversation.id,
                    checkpoint_id,
                ):
                    await self._delete_checkpoint(
                        session,
                        user_id,
                        checkpoint_id,
                    )

                    logger.info(
                        "清理已完成但未 ACK 的 checkpoint: "
                        "turn=%s",
                        checkpoint_id,
                    )
                    continue

                metadata = (
                    checkpoint.metadata
                    or {}
                )

                # ChatService 捕获到的普通异常会显式禁止自动重试。
                # 真正的进程硬崩溃不会来得及写此标记。
                if (
                    metadata.get(
                        "auto_recover",
                        True,
                    )
                    is False
                ):
                    continue

                built = self._build_request(
                    user_message,
                    conversation,
                )

                if built is None:
                    if (
                        checkpoint_id
                        not in self._warned_unrecoverable
                    ):
                        logger.warning(
                            "checkpoint 缺少可恢复请求快照，"
                            "跳过自动恢复: turn=%s",
                            checkpoint_id,
                        )

                        self._warned_unrecoverable.add(
                            checkpoint_id
                        )

                    continue

                body, attachments = built

                candidates.append(
                    RecoveryCandidate(
                        checkpoint_id=checkpoint_id,
                        user_id=user_id,
                        conversation_id=conversation.id,
                        body=body,
                        attachments=attachments,
                    )
                )

        return candidates

    @staticmethod
    async def _delete_checkpoint(
        session,
        user_id: uuid.UUID,
        checkpoint_id: uuid.UUID,
    ) -> None:
        store = PostgresCheckpointStore(
            session,
            user_id,
        )

        await store.delete(
            checkpoint_id
        )

    @staticmethod
    async def _has_completed_assistant(
        session,
        conversation_id: uuid.UUID,
        turn_id: uuid.UUID,
    ) -> bool:
        stmt = (
            select(Message)
            .where(
                Message.conversation_id
                == conversation_id
            )
            .where(
                Message.role
                == ROLE_ASSISTANT
            )
            .order_by(
                Message.created_at.desc()
            )
            .limit(500)
        )

        result = await session.execute(
            stmt
        )

        turn_text = str(turn_id)

        for message in result.scalars().all():
            meta = message.meta_data or {}

            if (
                str(
                    meta.get(
                        "turn_id",
                        "",
                    )
                )
                == turn_text
            ):
                return True

        return False

    @staticmethod
    def _build_request(
        user_message: Message,
        conversation: Conversation,
    ) -> tuple[
        ChatStreamRequest,
        list[dict],
    ] | None:
        meta = (
            user_message.meta_data
            or {}
        )

        request_snapshot = meta.get(
            "harness_request"
        )

        if not isinstance(
            request_snapshot,
            dict,
        ):
            return None

        if request_snapshot.get(
            "version"
        ) != 1:
            return None

        raw_attachments = meta.get(
            "attachments"
        ) or []

        attachments = [
            {
                "file_name": str(
                    item.get(
                        "file_name",
                        "",
                    )
                ),
                "text": str(
                    item.get(
                        "text",
                        "",
                    )
                ),
            }
            for item in raw_attachments
            if (
                isinstance(item, dict)
                and item.get("text")
            )
        ]

        raw_image_keys = (
            meta.get("image_keys")
            or []
        )

        image_keys = [
            str(key)
            for key in raw_image_keys
            if key
        ]

        body = ChatStreamRequest(
            conversation_id=conversation.id,
            message=user_message.content,
            skill_id=request_snapshot.get(
                "skill_id"
            ),
            image_keys=image_keys,
            attachments=attachments,
            enable_knowledge=(
                request_snapshot.get(
                    "enable_knowledge"
                )
            ),
            enable_memory=(
                request_snapshot.get(
                    "enable_memory"
                )
            ),
            enable_web_search=(
                request_snapshot.get(
                    "enable_web_search"
                )
            ),
        )

        return body, attachments


_worker = CheckpointRecoveryWorker()


def get_recovery_worker() -> CheckpointRecoveryWorker:
    return _worker


__all__ = [
    "CheckpointRecoveryWorker",
    "RecoveryCandidate",
    "get_recovery_worker",
]
