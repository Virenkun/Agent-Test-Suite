from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.persona import Persona
from app.schemas.persona import PersonaCreate, PersonaUpdate


class PersonaService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, payload: PersonaCreate) -> Persona:
        persona = Persona(**payload.model_dump())
        self.db.add(persona)
        await self.db.commit()
        await self.db.refresh(persona)
        return persona

    async def get(self, persona_id: UUID) -> Persona:
        result = await self.db.execute(
            select(Persona).where(
                Persona.id == persona_id, Persona.deleted_at.is_(None)
            )
        )
        persona = result.scalar_one_or_none()
        if persona is None:
            raise NotFoundError(f"Persona {persona_id} not found")
        return persona

    async def list(self, limit: int = 50, offset: int = 0) -> tuple[list[Persona], int]:
        total = await self.db.scalar(
            select(func.count(Persona.id)).where(Persona.deleted_at.is_(None))
        )
        result = await self.db.execute(
            select(Persona)
            .where(Persona.deleted_at.is_(None))
            .order_by(Persona.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update(self, persona_id: UUID, payload: PersonaUpdate) -> Persona:
        persona = await self.get(persona_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(persona, field, value)
        await self.db.commit()
        await self.db.refresh(persona)
        return persona

    async def delete(self, persona_id: UUID) -> None:
        persona = await self.get(persona_id)
        persona.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
