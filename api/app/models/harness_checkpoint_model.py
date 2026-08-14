"""Harness Checkpoint ORM 模型。

持久化 Agent Runtime 的可恢复执行状态。
真正的 messages / tool_calls / metadata 等状态存入 payload JSONB。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class HarnessCheckpointRecord(Base):
    """一次可恢复的 Harness Runtime checkpoint。"""

    __tablename__ = "harness_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Checkpoint 属于哪个用户。
    # Store 会同时按 id + user_id 查询，避免跨用户读取。
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # function_calling / react
    runtime: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    # 恢复后应该继续执行的 0-based iteration。
    next_iteration: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # encode_checkpoint() 产生的完整 JSON-safe 状态。
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = ["HarnessCheckpointRecord"]