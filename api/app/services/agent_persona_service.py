"""对话人格业务服务：CRUD + 设为当前生效。"""
from __future__ import annotations

import uuid

from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.prompt_renderer import render_agent_prompt
from app.core.exceptions import BizError
from app.core.llm.chat_model import build_default_chat_model
from app.core.logging import get_logger
from app.core.storage import get_storage
from app.models.agent_persona_model import AgentPersona
from app.repositories.agent_persona_repository import AgentPersonaRepository
from app.schemas.agent_persona_schema import PersonaCreate, PersonaUpdate

logger = get_logger(__name__)
MAX_PERSONAS = 200


class AgentPersonaService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AgentPersonaRepository(session)

    async def list(self, user_id: uuid.UUID) -> list[AgentPersona]:
        items = await self.repo.list_by_user(user_id)
        if not items:
            from app.services.persona_scenario_builtins import DEFAULT_PERSONA
            await self.repo.add(
                AgentPersona(
                    user_id=user_id,
                    name=DEFAULT_PERSONA["name"],
                    system_prompt=DEFAULT_PERSONA["system_prompt"],
                    temperature=DEFAULT_PERSONA["temperature"],
                    is_active=True,
                )
            )
            items = await self.repo.list_by_user(user_id)
        return items

    async def _get_or_404(self, user_id: uuid.UUID, persona_id: uuid.UUID):
        persona = await self.repo.get(user_id, persona_id)
        if persona is None:
            raise BizError("角色不存在", code=4040, status_code=404)
        return persona

    async def create(self, user_id: uuid.UUID, body: PersonaCreate):
        if await self.repo.count(user_id) >= MAX_PERSONAS:
            raise BizError(f"角色数量已达上限（{MAX_PERSONAS}）", code=4041)
        persona = AgentPersona(
            user_id=user_id,
            name=body.name.strip(),
            avatar_key=body.avatar_key or None,
            system_prompt=body.system_prompt or "",
            temperature=body.temperature,
        )
        if await self.repo.count(user_id) == 0:
            persona.is_active = True
        return await self.repo.add(persona)

    async def update(self, user_id: uuid.UUID, persona_id: uuid.UUID, body: PersonaUpdate):
        persona = await self._get_or_404(user_id, persona_id)
        fields = body.model_dump(exclude_unset=True)
        for key in ("name", "system_prompt", "temperature"):
            if key in fields and fields[key] is not None:
                setattr(persona, key, fields[key])
        if "avatar_key" in fields:
            persona.avatar_key = fields["avatar_key"] or None
        return await self.repo.save(persona)

    async def optimize_prompt(self, user_id: uuid.UUID, raw_prompt: str) -> str:
        raw = (raw_prompt or "").strip()
        if not raw:
            raise BizError("请先填写要优化的人设提示词", code=4060)
        model, _ = await build_default_chat_model(
            self.session, user_id, temperature=0.4, streaming=False
        )
        result = await model.ainvoke(
            [HumanMessage(content=render_agent_prompt("optimize_prompt.jinja2", raw_prompt=raw))]
        )
        content = result.content if isinstance(result.content, str) else str(result.content)
        return content.strip()

    @staticmethod
    def to_out_dict(persona: AgentPersona) -> dict:
        avatar_url = None
        if persona.avatar_key:
            try:
                avatar_url = get_storage().get_url(persona.avatar_key)
            except Exception:
                pass
        return {
            "id": str(persona.id),
            "name": persona.name,
            "avatar_key": persona.avatar_key,
            "avatar_url": avatar_url,
            "system_prompt": persona.system_prompt,
            "temperature": persona.temperature,
            "is_active": persona.is_active,
        }
