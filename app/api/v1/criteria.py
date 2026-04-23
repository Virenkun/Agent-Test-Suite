from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.criterion import CriterionRead, CriterionUpdate
from app.services.test_case_service import TestCaseService

router = APIRouter(prefix="/criteria", tags=["criteria"])


@router.get("/{criterion_id}", response_model=CriterionRead)
async def get_criterion(criterion_id: UUID, db: AsyncSession = Depends(get_db)) -> CriterionRead:
    crit = await TestCaseService(db).get_criterion(criterion_id)
    return CriterionRead.model_validate(crit)


@router.patch("/{criterion_id}", response_model=CriterionRead)
async def update_criterion(
    criterion_id: UUID, payload: CriterionUpdate, db: AsyncSession = Depends(get_db)
) -> CriterionRead:
    crit = await TestCaseService(db).update_criterion(criterion_id, payload)
    return CriterionRead.model_validate(crit)


@router.delete("/{criterion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_criterion(criterion_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    await TestCaseService(db).delete_criterion(criterion_id)
