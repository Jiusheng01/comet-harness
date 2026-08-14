from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.harness.checkpoint.codec import (
    decode_checkpoint,
    encode_checkpoint,
)
from app.core.harness.checkpoint.models import HarnessCheckpoint
from app.models.harness_checkpoint_model import (
    HarnessCheckpointRecord,
)


class PostgresCheckpointStore:
    """PostgreSQL 持久化 CheckpointStore。

    Store 绑定当前 user_id：
    - load / delete 始终同时校验 checkpoint_id + user_id
    - Runtime 本身不感知用户与数据库
    """

    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
    ) -> None:
        self._session = session
        self._user_id = user_id

    async def save(
        self,
        checkpoint: HarnessCheckpoint,
    ) -> None:
        payload = encode_checkpoint(checkpoint)

        try:
            # 使用主键读取是为了区分：
            # 1. checkpoint 不存在 -> INSERT
            # 2. checkpoint 属于当前用户 -> UPDATE
            # 3. checkpoint 属于其他用户 -> 拒绝覆盖
            record = await self._session.get(
                HarnessCheckpointRecord,
                checkpoint.checkpoint_id,
            )

            if record is None:
                record = HarnessCheckpointRecord(
                    id=checkpoint.checkpoint_id,
                    user_id=self._user_id,
                    runtime=checkpoint.runtime,
                    next_iteration=checkpoint.next_iteration,
                    payload=payload,
                )
                self._session.add(record)

            else:
                if record.user_id != self._user_id:
                    raise PermissionError(
                        "checkpoint 不属于当前用户"
                    )

                record.runtime = checkpoint.runtime
                record.next_iteration = (
                    checkpoint.next_iteration
                )
                record.payload = payload

            await self._session.commit()

        except Exception:
            await self._session.rollback()
            raise

    async def load(
        self,
        checkpoint_id: uuid.UUID,
    ) -> HarnessCheckpoint | None:
        stmt = (
            select(HarnessCheckpointRecord)
            .where(
                HarnessCheckpointRecord.id
                == checkpoint_id
            )
            .where(
                HarnessCheckpointRecord.user_id
                == self._user_id
            )
        )

        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            return None

        return decode_checkpoint(
            dict(record.payload)
        )

    async def delete(
        self,
        checkpoint_id: uuid.UUID,
    ) -> None:
        stmt = (
            delete(HarnessCheckpointRecord)
            .where(
                HarnessCheckpointRecord.id
                == checkpoint_id
            )
            .where(
                HarnessCheckpointRecord.user_id
                == self._user_id
            )
        )

        try:
            await self._session.execute(stmt)
            await self._session.commit()

        except Exception:
            await self._session.rollback()
            raise