from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.test_run import TestRunStatus
from app.schemas.common import Page
from app.schemas.test_run import TestRunRead
from app.schemas.test_suite import (
    AddCasePayload,
    TestSuiteCaseRead,
    TestSuiteCreate,
    TestSuiteRead,
    TestSuiteRunCreate,
    TestSuiteRunDetailRead,
    TestSuiteRunRead,
    TestSuiteUpdate,
)
from app.services.test_suite_service import TestSuiteService


def _serialize_suite(suite) -> TestSuiteRead:
    cases_out = [
        TestSuiteCaseRead(
            test_case_id=c.test_case_id,
            order_index=c.order_index,
            name=getattr(c.test_case, "name", None) if c.test_case else None,
        )
        for c in suite.cases
    ]
    return TestSuiteRead(
        id=suite.id,
        name=suite.name,
        description=suite.description,
        created_at=suite.created_at,
        updated_at=suite.updated_at,
        cases=cases_out,
    )


test_suites_router = APIRouter(prefix="/test-suites", tags=["test-suites"])


@test_suites_router.post(
    "", response_model=TestSuiteRead, status_code=status.HTTP_201_CREATED
)
async def create_test_suite(
    payload: TestSuiteCreate, db: AsyncSession = Depends(get_db)
) -> TestSuiteRead:
    svc = TestSuiteService(db)
    suite = await svc.create(payload)
    # refetch to populate joined test_case relationships
    suite = await svc.get(suite.id)
    return _serialize_suite(suite)


@test_suites_router.get("", response_model=Page[TestSuiteRead])
async def list_test_suites(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[TestSuiteRead]:
    items, total = await TestSuiteService(db).list(limit=limit, offset=offset)
    return Page[TestSuiteRead](
        items=[_serialize_suite(s) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@test_suites_router.get("/{suite_id}", response_model=TestSuiteRead)
async def get_test_suite(
    suite_id: UUID, db: AsyncSession = Depends(get_db)
) -> TestSuiteRead:
    suite = await TestSuiteService(db).get(suite_id)
    return _serialize_suite(suite)


@test_suites_router.patch("/{suite_id}", response_model=TestSuiteRead)
async def update_test_suite(
    suite_id: UUID,
    payload: TestSuiteUpdate,
    db: AsyncSession = Depends(get_db),
) -> TestSuiteRead:
    svc = TestSuiteService(db)
    await svc.update(suite_id, payload)
    suite = await svc.get(suite_id)
    return _serialize_suite(suite)


@test_suites_router.delete("/{suite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_test_suite(
    suite_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    await TestSuiteService(db).delete(suite_id)


@test_suites_router.post(
    "/{suite_id}/cases",
    response_model=TestSuiteRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_case(
    suite_id: UUID,
    payload: AddCasePayload,
    db: AsyncSession = Depends(get_db),
) -> TestSuiteRead:
    suite = await TestSuiteService(db).add_case(suite_id, payload)
    return _serialize_suite(suite)


@test_suites_router.delete(
    "/{suite_id}/cases/{test_case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_case(
    suite_id: UUID,
    test_case_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    await TestSuiteService(db).remove_case(suite_id, test_case_id)


# ----- Test Suite Runs (batch execution) -----

test_suite_runs_router = APIRouter(
    prefix="/test-suite-runs", tags=["test-suite-runs"]
)


@test_suite_runs_router.post(
    "", response_model=TestSuiteRunRead, status_code=status.HTTP_201_CREATED
)
async def launch_test_suite_run(
    payload: TestSuiteRunCreate, db: AsyncSession = Depends(get_db)
) -> TestSuiteRunRead:
    run = await TestSuiteService(db).launch_suite_run(payload)
    return TestSuiteRunRead.model_validate(run)


@test_suite_runs_router.get("", response_model=Page[TestSuiteRunRead])
async def list_test_suite_runs(
    test_suite_id: UUID | None = None,
    status_: TestRunStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> Page[TestSuiteRunRead]:
    items, total = await TestSuiteService(db).list_suite_runs(
        test_suite_id=test_suite_id,
        status=status_,
        limit=limit,
        offset=offset,
    )
    return Page[TestSuiteRunRead](
        items=[TestSuiteRunRead.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@test_suite_runs_router.get(
    "/{suite_run_id}", response_model=TestSuiteRunDetailRead
)
async def get_test_suite_run(
    suite_run_id: UUID, db: AsyncSession = Depends(get_db)
) -> TestSuiteRunDetailRead:
    run = await TestSuiteService(db).get_suite_run(suite_run_id)
    return TestSuiteRunDetailRead(
        **TestSuiteRunRead.model_validate(run).model_dump(by_alias=False),
        test_runs=[TestRunRead.model_validate(r) for r in run.test_runs],
    )
