"""Agent runtime configuration service."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_config_model import AgentConfig
from app.repositories.agent_config_repository import AgentConfigRepository
from app.schemas.agent_config_schema import AgentConfigUpdate


class AgentConfigService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AgentConfigRepository(session)

    async def get_or_create(self, user_id: uuid.UUID) -> AgentConfig:
        config = await self.repo.get_by_user(user_id)
        if config is None:
            config = await self.repo.create(AgentConfig(user_id=user_id))
        return config

    async def update(
        self, user_id: uuid.UUID, body: AgentConfigUpdate
    ) -> AgentConfig:
        config = await self.get_or_create(user_id)
        fields = body.model_dump(exclude_unset=True)
        for key, value in fields.items():
            setattr(config, key, value)
        return await self.repo.save(config)

    @staticmethod
    def to_out_dict(config: AgentConfig) -> dict:
        return {
            "enable_active_recall": config.enable_active_recall,
            "enable_cross_session": config.enable_cross_session,
            "show_avatar": config.show_avatar,
            "human_mode": config.human_mode,
        }
