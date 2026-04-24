from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.models.agent import Agent
from app.models.call import Call, CallStatus
from app.models.test_case import TestCase
from app.models.test_run import TestRun, TestRunStatus
from app.models.test_suite import TestSuite, TestSuiteCase, TestSuiteRun
from app.schemas.test_suite import (
    AddCasePayload,
    TestSuiteCreate,
    TestSuiteRunCreate,
    TestSuiteUpdate,
)


class TestSuiteService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- CRUD ----------

    async def create(self, payload: TestSuiteCreate) -> TestSuite:
        suite = TestSuite(name=payload.name, description=payload.description)
        for idx, tc_id in enumerate(payload.test_case_ids):
            suite.cases.append(
                TestSuiteCase(test_case_id=tc_id, order_index=idx)
            )
        self.db.add(suite)
        await self.db.commit()
        await self.db.refresh(suite, attribute_names=["cases"])
        return suite

    async def get(self, suite_id: UUID) -> TestSuite:
        result = await self.db.execute(
            select(TestSuite)
            .options(selectinload(TestSuite.cases).selectinload(TestSuiteCase.test_case))
            .where(TestSuite.id == suite_id, TestSuite.deleted_at.is_(None))
        )
        suite = result.scalar_one_or_none()
        if suite is None:
            raise NotFoundError(f"TestSuite {suite_id} not found")
        return suite

    async def list(
        self, limit: int = 100, offset: int = 0
    ) -> tuple[list[TestSuite], int]:
        total = await self.db.scalar(
            select(func.count(TestSuite.id)).where(TestSuite.deleted_at.is_(None))
        )
        result = await self.db.execute(
            select(TestSuite)
            .options(selectinload(TestSuite.cases).selectinload(TestSuiteCase.test_case))
            .where(TestSuite.deleted_at.is_(None))
            .order_by(TestSuite.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update(self, suite_id: UUID, payload: TestSuiteUpdate) -> TestSuite:
        suite = await self.get(suite_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(suite, field, value)
        await self.db.commit()
        await self.db.refresh(suite)
        return suite

    async def delete(self, suite_id: UUID) -> None:
        suite = await self.get(suite_id)
        suite.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def add_case(
        self, suite_id: UUID, payload: AddCasePayload
    ) -> TestSuite:
        suite = await self.get(suite_id)
        # Check test case exists
        tc = await self.db.get(TestCase, payload.test_case_id)
        if tc is None or tc.deleted_at is not None:
            raise NotFoundError(f"TestCase {payload.test_case_id} not found")
        # Skip if already in suite
        if any(c.test_case_id == payload.test_case_id for c in suite.cases):
            return suite
        idx = payload.order_index if payload.order_index is not None else len(
            suite.cases
        )
        suite.cases.append(
            TestSuiteCase(test_case_id=payload.test_case_id, order_index=idx)
        )
        await self.db.commit()
        return await self.get(suite_id)

    async def remove_case(self, suite_id: UUID, test_case_id: UUID) -> None:
        result = await self.db.execute(
            select(TestSuiteCase).where(
                TestSuiteCase.test_suite_id == suite_id,
                TestSuiteCase.test_case_id == test_case_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError("Case not in suite")
        await self.db.delete(row)
        await self.db.commit()

    # ---------- Running a suite ----------

    async def launch_suite_run(
        self, payload: TestSuiteRunCreate
    ) -> TestSuiteRun:
        from app.config import get_settings

        settings = get_settings()
        suite = await self.get(payload.test_suite_id)
        if not suite.cases:
            raise ValidationError("Test suite has no test cases")

        # Resolve agent phone
        resolved_phone = payload.agent_phone_number
        resolved_agent_id = payload.agent_id
        if not resolved_phone:
            if resolved_agent_id is None:
                raise ValidationError(
                    "Either agent_phone_number or agent_id must be provided"
                )
            agent_row = await self.db.execute(
                select(Agent).where(
                    Agent.id == resolved_agent_id, Agent.deleted_at.is_(None)
                )
            )
            agent = agent_row.scalar_one_or_none()
            if agent is None:
                raise NotFoundError(f"Agent {resolved_agent_id} not found")
            resolved_phone = agent.phone_number

        max_cost = payload.max_cost_usd or Decimal(str(settings.max_cost_per_run_usd))
        max_duration = (
            payload.max_duration_sec or settings.max_call_duration_sec
        )
        if payload.calls_per_case * len(suite.cases) > settings.max_calls_per_run * 10:
            raise ValidationError(
                "Too many total calls for this suite. Reduce calls_per_case."
            )

        # Pre-load each test case with criteria to validate
        test_case_ids = [c.test_case_id for c in suite.cases]
        tc_rows = await self.db.execute(
            select(TestCase)
            .options(selectinload(TestCase.criteria))
            .where(TestCase.id.in_(test_case_ids), TestCase.deleted_at.is_(None))
        )
        test_cases_by_id = {tc.id: tc for tc in tc_rows.scalars().all()}
        for tc_id in test_case_ids:
            tc = test_cases_by_id.get(tc_id)
            if tc is None:
                raise ValidationError(
                    f"Test case {tc_id} is missing or deleted"
                )
            if not tc.criteria:
                raise ValidationError(
                    f"Test case {tc.name} has no evaluation criteria"
                )

        suite_run = TestSuiteRun(
            test_suite_id=suite.id,
            agent_id=resolved_agent_id,
            agent_phone_number=resolved_phone,
            status=TestRunStatus.PENDING,
            calls_per_case=payload.calls_per_case,
            max_cost_usd=max_cost,
            max_duration_sec=max_duration,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(suite_run)
        await self.db.flush()  # need suite_run.id for child rows

        # Create child TestRun per test case in order
        child_runs: list[TestRun] = []
        for sc in suite.cases:
            tc = test_cases_by_id[sc.test_case_id]
            run = TestRun(
                test_case_id=tc.id,
                agent_phone_number=resolved_phone,
                agent_id=resolved_agent_id,
                requested_calls=payload.calls_per_case,
                max_cost_usd=max_cost,
                max_duration_sec=max_duration,
                status=TestRunStatus.PENDING,
                test_suite_run_id=suite_run.id,
            )
            for _ in range(payload.calls_per_case):
                run.calls.append(Call(status=CallStatus.QUEUED))
            self.db.add(run)
            child_runs.append(run)

        await self.db.commit()
        await self.db.refresh(suite_run)

        # Dispatch all queued calls after commit
        from app.workers.tasks_calls import place_call

        for run in child_runs:
            for call in run.calls:
                place_call.delay(str(call.id))

        return suite_run

    async def get_suite_run(self, suite_run_id: UUID) -> TestSuiteRun:
        result = await self.db.execute(
            select(TestSuiteRun)
            .options(selectinload(TestSuiteRun.test_runs))
            .where(TestSuiteRun.id == suite_run_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise NotFoundError(f"TestSuiteRun {suite_run_id} not found")
        return run

    async def list_suite_runs(
        self,
        *,
        test_suite_id: UUID | None = None,
        status: TestRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TestSuiteRun], int]:
        stmt = select(TestSuiteRun)
        count_stmt = select(func.count(TestSuiteRun.id))
        if test_suite_id:
            stmt = stmt.where(TestSuiteRun.test_suite_id == test_suite_id)
            count_stmt = count_stmt.where(
                TestSuiteRun.test_suite_id == test_suite_id
            )
        if status:
            stmt = stmt.where(TestSuiteRun.status == status)
            count_stmt = count_stmt.where(TestSuiteRun.status == status)
        total = await self.db.scalar(count_stmt)
        result = await self.db.execute(
            stmt.order_by(TestSuiteRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)
