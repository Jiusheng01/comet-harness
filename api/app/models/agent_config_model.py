"""Agent runtime/context behavior configuration.

Persona owns presentation concerns such as system prompt and temperature.
AgentConfig only exposes cross-cutting runtime/context toggles.

The database still contains several legacy NOT NULL columns created by the
original Comet schema. They remain privately mapped here so inserts stay
compatible without coupling runtime configuration back to persona/tool UI.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )

    # Legacy database compatibility only. These columns are intentionally not
    # exposed by AgentConfigService; persona/tool configuration owns them now.
    _legacy_system_prompt: Mapped[str] = mapped_column(
        "system_prompt", Text, default=""
    )
    _legacy_temperature: Mapped[float] = mapped_column(
        "temperature", Float, default=0.7
    )
    _legacy_enable_knowledge: Mapped[bool] = mapped_column(
        "enable_knowledge", Boolean, default=True
    )
    _legacy_enable_memory: Mapped[bool] = mapped_column(
        "enable_memory", Boolean, default=True
    )
    _legacy_enable_web_search: Mapped[bool] = mapped_column(
        "enable_web_search", Boolean, default=False
    )

    # Active memory recall: inject relevant long-term memory into the turn.
    enable_active_recall: Mapped[bool] = mapped_column(Boolean, default=True)
    # Cross-session context: include recent context from other conversations.
    enable_cross_session: Mapped[bool] = mapped_column(Boolean, default=False)
    # UI preference: show user/persona avatars in chat.
    show_avatar: Mapped[bool] = mapped_column(Boolean, default=False)
    # Conversational rendering mode; persona prompt/temperature remain in AgentPersona.
    human_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
