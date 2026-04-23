from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.test_run import TestRunStatus
from app.schemas.call import CallRead
from app.schemas.common import Page
from app.schemas.test_run import TestRunCreate, TestRunDetailRead, TestRunRead
from app.services.test_execution_service import TestExecutionService

router = APIRouter(prefix="/test-runs", tags=["test-runs"])


@router.post("", response_model=TestRunRead, status_code=status.HTTP_201_CREATED)
async def create_test_run(
    payload: TestRunCreate, db: AsyncSession = Depends(get_db)
) -> TestRunRead:
    run = await TestExecutionService(db).create_run(payload)
    return TestRunRead.model_validate(run)


@router.get("", response_model=Page[TestRunRead])
async def list_test_runs(
    test_case_id: UUID | None = None,
    status_: TestRunStatus | None = Query(None, alias="status"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[TestRunRead]:
    items, total = await TestExecutionService(db).list_runs(
        test_case_id=test_case_id,
        status=status_,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return Page[TestRunRead](
        items=[TestRunRead.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=TestRunDetailRead)
async def get_test_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> TestRunDetailRead:
    run, breakdown = await TestExecutionService(db).get_run_detail(run_id)
    return TestRunDetailRead(
        **TestRunRead.model_validate(run).model_dump(by_alias=False),
        calls=[CallRead.model_validate(c) for c in run.calls],
        criteria_breakdown=breakdown,
    )


@router.get("/{run_id}/calls", response_model=list[CallRead])
async def list_run_calls(run_id: UUID, db: AsyncSession = Depends(get_db)) -> list[CallRead]:
    run, _ = await TestExecutionService(db).get_run_detail(run_id)
    return [CallRead.model_validate(c) for c in run.calls]


@router.post("/{run_id}/retry")
async def retry_failed(run_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    retried = await TestExecutionService(db).retry_failed(run_id)
    return {"retried": retried}
