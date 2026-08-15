"""对话人格（角色卡）路由：CRUD + 设为当前生效。"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.agent_persona_schema import PersonaCreate, PersonaUpdate
from app.services.agent_persona_service import AgentPersonaService

router = APIRouter(prefix="/personas", tags=["agent"])


@router.post("/optimize-prompt")
async def optimize_prompt(
    body: PersonaCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    optimized = await AgentPersonaService(session).optimize_prompt(
        user.id, body.system_prompt
    )
    return success({"optimized": optimized})


@router.get("")
async def list_personas(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    items = await AgentPersonaService(session).list(user.id)
    return success([AgentPersonaService.to_out_dict(p) for p in items])


@router.post("")
async def create_persona(body: PersonaCreate, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    persona = await AgentPersonaService(session).create(user.id, body)
    return success(AgentPersonaService.to_out_dict(persona), "已创建")


@router.put("/{persona_id}")
async def update_persona(persona_id: uuid.UUID, body: PersonaUpdate, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    persona = await AgentPersonaService(session).update(user.id, persona_id, body)
    return success(AgentPersonaService.to_out_dict(persona), "已保存")


@router.delete("/{persona_id}")
async def delete_persona(persona_id: uuid.UUID, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await AgentPersonaService(session).delete(user.id, persona_id)
    return success(message="已删除")


@router.post("/{persona_id}/activate")
async def activate_persona(persona_id: uuid.UUID, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    persona = await AgentPersonaService(session).activate(user.id, persona_id)
    return success(AgentPersonaService.to_out_dict(persona), "已切换")
