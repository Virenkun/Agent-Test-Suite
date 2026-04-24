from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate
from app.schemas.common import Page
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreate, db: AsyncSession = Depends(get_db)
) -> AgentRead:
    agent = await AgentService(db).create(payload)
    return AgentRead.model_validate(agent)


@router.get("", response_model=Page[AgentRead])
async def list_agents(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[AgentRead]:
    items, total = await AgentService(db).list(limit=limit, offset=offset)
    return Page[AgentRead](
        items=[AgentRead.model_validate(a) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(agent_id: UUID, db: AsyncSession = Depends(get_db)) -> AgentRead:
    agent = await AgentService(db).get(agent_id)
    return AgentRead.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: UUID, payload: AgentUpdate, db: AsyncSession = Depends(get_db)
) -> AgentRead:
    agent = await AgentService(db).update(agent_id, payload)
    return AgentRead.model_validate(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    await AgentService(db).delete(agent_id)
