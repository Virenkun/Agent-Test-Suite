from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.integrations.openai_client import OpenAIEvaluator
from app.models.persona import Persona


class AIGenerationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _persona_hint(self, persona_id: UUID | None) -> str | None:
        if persona_id is None:
            return None
        result = await self.db.execute(
            select(Persona).where(
                Persona.id == persona_id, Persona.deleted_at.is_(None)
            )
        )
        p = result.scalar_one_or_none()
        if p is None:
            raise NotFoundError(f"Persona {persona_id} not found")
        return (
            f"{p.name}; tone: {p.tone or '—'}; goal: {p.goal or '—'}; "
            f"personality: {p.personality or '—'}"
        )

    def generate_persona(self, brief: str) -> dict:
        return OpenAIEvaluator().generate_persona(brief)

    async def generate_test_case(
        self,
        *,
        brief: str,
        persona_id: UUID | None,
        desired_criteria_count: int,
    ) -> dict:
        hint = await self._persona_hint(persona_id)
        return OpenAIEvaluator().generate_test_case(
            brief=brief,
            persona_hint=hint,
            desired_criteria_count=desired_criteria_count,
        )
