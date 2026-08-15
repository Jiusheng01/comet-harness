"""Agent runtime configuration schema."""
from pydantic import BaseModel


class AgentConfigUpdate(BaseModel):
    """Update runtime/context behavior only."""

    enable_active_recall: bool | None = None
    enable_cross_session: bool | None = None
    show_avatar: bool | None = None
    human_mode: bool | None = None
