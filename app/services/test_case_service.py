from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.criterion import EvaluationCriterion
from app.models.persona import Persona
from app.models.test_case import TestCase
from app.schemas.criterion import CriterionCreate, CriterionUpdate
from app.schemas.test_case import TestCaseCreate, TestCaseUpdate


class TestCaseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _assert_persona_exists(self, persona_id: UUID) -> None:
        result = await self.db.execute(
            select(Persona.id).where(
                Persona.id == persona_id, Persona.deleted_at.is_(None)
            )
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundError(f"Persona {persona_id} not found")

    async def create(self, payload: TestCaseCreate) -> TestCase:
        await self._assert_persona_exists(payload.persona_id)
        data = payload.model_dump(exclude={"criteria"})
        test_case = TestCase(**data)
        for idx, crit in enumerate(payload.criteria):
            test_case.criteria.append(
                EvaluationCriterion(
                    **{**crit.model_dump(), "order_index": crit.order_index or idx}
                )
            )
        self.db.add(test_case)
        await self.db.commit()
        await self.db.refresh(test_case, attribute_names=["criteria"])
        return test_case

    async def get(self, test_case_id: UUID) -> TestCase:
        result = await self.db.execute(
            select(TestCase)
            .options(selectinload(TestCase.criteria))
            .where(TestCase.id == test_case_id, TestCase.deleted_at.is_(None))
        )
        tc = result.scalar_one_or_none()
        if tc is None:
            raise NotFoundError(f"TestCase {test_case_id} not found")
        return tc

    async def list(self, limit: int = 50, offset: int = 0) -> tuple[list[TestCase], int]:
        total = await self.db.scalar(
            select(func.count(TestCase.id)).where(TestCase.deleted_at.is_(None))
        )
        result = await self.db.execute(
            select(TestCase)
            .options(selectinload(TestCase.criteria))
            .where(TestCase.deleted_at.is_(None))
            .order_by(TestCase.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update(self, test_case_id: UUID, payload: TestCaseUpdate) -> TestCase:
        tc = await self.get(test_case_id)
        data = payload.model_dump(exclude_unset=True)
        if "persona_id" in data:
            await self._assert_persona_exists(data["persona_id"])
        for field, value in data.items():
            setattr(tc, field, value)
        await self.db.commit()
        await self.db.refresh(tc, attribute_names=["criteria"])
        return tc

    async def delete(self, test_case_id: UUID) -> None:
        tc = await self.get(test_case_id)
        tc.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()

    # ----- criteria -----

    async def add_criterion(
        self, test_case_id: UUID, payload: CriterionCreate
    ) -> EvaluationCriterion:
        tc = await self.get(test_case_id)
        crit = EvaluationCriterion(**payload.model_dump(), test_case_id=tc.id)
        self.db.add(crit)
        await self.db.commit()
        await self.db.refresh(crit)
        return crit

    async def get_criterion(self, criterion_id: UUID) -> EvaluationCriterion:
        result = await self.db.execute(
            select(EvaluationCriterion).where(EvaluationCriterion.id == criterion_id)
        )
        crit = result.scalar_one_or_none()
        if crit is None:
            raise NotFoundError(f"Criterion {criterion_id} not found")
        return crit

    async def update_criterion(
        self, criterion_id: UUID, payload: CriterionUpdate
    ) -> EvaluationCriterion:
        crit = await self.get_criterion(criterion_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(crit, field, value)
        await self.db.commit()
        await self.db.refresh(crit)
        return crit

    async def delete_criterion(self, criterion_id: UUID) -> None:
        crit = await self.get_criterion(criterion_id)
        await self.db.delete(crit)
        await self.db.commit()
