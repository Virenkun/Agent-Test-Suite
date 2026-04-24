from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentUpdate


class AgentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _assert_phone_unique(
        self, phone: str, exclude_id: UUID | None = None
    ) -> None:
        stmt = select(Agent.id).where(
            Agent.phone_number == phone, Agent.deleted_at.is_(None)
        )
        if exclude_id is not None:
            stmt = stmt.where(Agent.id != exclude_id)
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise ConflictError(f"Agent with phone_number {phone} already exists")

    async def create(self, payload: AgentCreate) -> Agent:
        await self._assert_phone_unique(payload.phone_number)
        agent = Agent(**payload.model_dump())
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def get(self, agent_id: UUID) -> Agent:
        result = await self.db.execute(
            select(Agent).where(
                and_(Agent.id == agent_id, Agent.deleted_at.is_(None))
            )
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise NotFoundError(f"Agent {agent_id} not found")
        return agent

    async def list(
        self, limit: int = 50, offset: int = 0
    ) -> tuple[list[Agent], int]:
        total = await self.db.scalar(
            select(func.count(Agent.id)).where(Agent.deleted_at.is_(None))
        )
        result = await self.db.execute(
            select(Agent)
            .where(Agent.deleted_at.is_(None))
            .order_by(Agent.name.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update(self, agent_id: UUID, payload: AgentUpdate) -> Agent:
        agent = await self.get(agent_id)
        data = payload.model_dump(exclude_unset=True)
        if "phone_number" in data and data["phone_number"] != agent.phone_number:
            await self._assert_phone_unique(data["phone_number"], exclude_id=agent.id)
        for field, value in data.items():
            setattr(agent, field, value)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def delete(self, agent_id: UUID) -> None:
        agent = await self.get(agent_id)
        agent.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
