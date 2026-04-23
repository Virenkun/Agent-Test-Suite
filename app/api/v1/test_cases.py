from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.criterion import CriterionCreate, CriterionRead
from app.schemas.test_case import TestCaseCreate, TestCaseRead, TestCaseUpdate
from app.services.test_case_service import TestCaseService

router = APIRouter(prefix="/test-cases", tags=["test-cases"])


@router.post("", response_model=TestCaseRead, status_code=status.HTTP_201_CREATED)
async def create_test_case(
    payload: TestCaseCreate, db: AsyncSession = Depends(get_db)
) -> TestCaseRead:
    tc = await TestCaseService(db).create(payload)
    return TestCaseRead.model_validate(tc)


@router.get("", response_model=Page[TestCaseRead])
async def list_test_cases(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[TestCaseRead]:
    items, total = await TestCaseService(db).list(limit=limit, offset=offset)
    return Page[TestCaseRead](
        items=[TestCaseRead.model_validate(tc) for tc in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{test_case_id}", response_model=TestCaseRead)
async def get_test_case(test_case_id: UUID, db: AsyncSession = Depends(get_db)) -> TestCaseRead:
    tc = await TestCaseService(db).get(test_case_id)
    return TestCaseRead.model_validate(tc)


@router.patch("/{test_case_id}", response_model=TestCaseRead)
async def update_test_case(
    test_case_id: UUID, payload: TestCaseUpdate, db: AsyncSession = Depends(get_db)
) -> TestCaseRead:
    tc = await TestCaseService(db).update(test_case_id, payload)
    return TestCaseRead.model_validate(tc)


@router.delete("/{test_case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_test_case(test_case_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    await TestCaseService(db).delete(test_case_id)


@router.post(
    "/{test_case_id}/criteria",
    response_model=CriterionRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_criterion(
    test_case_id: UUID, payload: CriterionCreate, db: AsyncSession = Depends(get_db)
) -> CriterionRead:
    crit = await TestCaseService(db).add_criterion(test_case_id, payload)
    return CriterionRead.model_validate(crit)
