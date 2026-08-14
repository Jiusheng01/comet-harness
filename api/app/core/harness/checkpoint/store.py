from __future__ import annotations

import copy
import uuid
from typing import Protocol

from app.core.harness.checkpoint.models import HarnessCheckpoint


class CheckpointStore(Protocol):
    """Harness checkpoint 存储接口。"""

    async def save(
        self,
        checkpoint: HarnessCheckpoint,
    ) -> None:
        ...

    async def load(
        self,
        checkpoint_id: uuid.UUID,
    ) -> HarnessCheckpoint | None:
        ...

    async def delete(
        self,
        checkpoint_id: uuid.UUID,
    ) -> None:
        ...


class InMemoryCheckpointStore:
    """仅用于开发和测试的内存 CheckpointStore。"""

    def __init__(self) -> None:
        self._items: dict[uuid.UUID, HarnessCheckpoint] = {}

    async def save(
        self,
        checkpoint: HarnessCheckpoint,
    ) -> None:
        # 深拷贝，避免 Runtime 后续修改 messages
        # 影响已经保存的 checkpoint。
        self._items[checkpoint.checkpoint_id] = copy.deepcopy(
            checkpoint
        )

    async def load(
        self,
        checkpoint_id: uuid.UUID,
    ) -> HarnessCheckpoint | None:
        checkpoint = self._items.get(checkpoint_id)

        if checkpoint is None:
            return None

        return copy.deepcopy(checkpoint)

    async def delete(
        self,
        checkpoint_id: uuid.UUID,
    ) -> None:
        self._items.pop(checkpoint_id, None)