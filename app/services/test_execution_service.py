from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.agent import Agent
from app.models.call import Call, CallStatus
from app.models.call_evaluation import CallEvaluation
from app.models.criterion import CriterionType
from app.models.test_case import TestCase
from app.models.test_run import TestRun, TestRunStatus
from app.schemas.test_run import CriterionBreakdown, TestRunCreate


class TestExecutionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_run(self, payload: TestRunCreate) -> TestRun:
        settings = get_settings()
        if payload.num_calls > settings.max_calls_per_run:
            raise ValidationError(
                f"num_calls {payload.num_calls} exceeds MAX_CALLS_PER_RUN ({settings.max_calls_per_run})"
            )
        max_cost = payload.max_cost_usd or Decimal(str(settings.max_cost_per_run_usd))
        max_duration = payload.max_duration_sec or settings.max_call_duration_sec

        # Resolve agent phone: prefer explicit phone, otherwise look up via agent_id.
        resolved_agent_id = payload.agent_id
        resolved_phone = payload.agent_phone_number
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

        tc = await self.db.execute(
            select(TestCase)
            .options(selectinload(TestCase.criteria))
            .where(TestCase.id == payload.test_case_id, TestCase.deleted_at.is_(None))
        )
        test_case = tc.scalar_one_or_none()
        if test_case is None:
            raise NotFoundError(f"TestCase {payload.test_case_id} not found")
        if not test_case.criteria:
            raise ValidationError("Test case has no evaluation criteria defined")

        run = TestRun(
            test_case_id=test_case.id,
            agent_phone_number=resolved_phone,
            agent_id=resolved_agent_id,
            requested_calls=payload.num_calls,
            max_cost_usd=max_cost,
            max_duration_sec=max_duration,
            status=TestRunStatus.PENDING,
        )
        for _ in range(payload.num_calls):
            run.calls.append(Call(status=CallStatus.QUEUED))
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run, attribute_names=["calls"])

        # Enqueue work after commit so worker can read the rows.
        from app.workers.tasks_calls import place_call

        for call in run.calls:
            place_call.delay(str(call.id))

        return run

    async def list_runs(
        self,
        *,
        test_case_id: UUID | None = None,
        status: TestRunStatus | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TestRun], int]:
        stmt = select(TestRun)
        count_stmt = select(func.count(TestRun.id))
        if test_case_id:
            stmt = stmt.where(TestRun.test_case_id == test_case_id)
            count_stmt = count_stmt.where(TestRun.test_case_id == test_case_id)
        if status:
            stmt = stmt.where(TestRun.status == status)
            count_stmt = count_stmt.where(TestRun.status == status)
        if date_from:
            stmt = stmt.where(TestRun.created_at >= date_from)
            count_stmt = count_stmt.where(TestRun.created_at >= date_from)
        if date_to:
            stmt = stmt.where(TestRun.created_at <= date_to)
            count_stmt = count_stmt.where(TestRun.created_at <= date_to)

        total = await self.db.scalar(count_stmt)
        result = await self.db.execute(
            stmt.order_by(TestRun.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)

    async def get_run_detail(
        self, run_id: UUID
    ) -> tuple[TestRun, list[CriterionBreakdown]]:
        result = await self.db.execute(
            select(TestRun)
            .options(selectinload(TestRun.calls))
            .where(TestRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise NotFoundError(f"TestRun {run_id} not found")

        tc = await self.db.execute(
            select(TestCase)
            .options(selectinload(TestCase.criteria))
            .where(TestCase.id == run.test_case_id)
        )
        test_case = tc.scalar_one()

        evals = await self.db.execute(
            select(CallEvaluation)
            .join(Call, Call.id == CallEvaluation.call_id)
            .where(Call.test_run_id == run.id)
        )
        breakdown_bucket: dict[UUID, list[CallEvaluation]] = defaultdict(list)
        for ev in evals.scalars():
            breakdown_bucket[ev.criterion_id].append(ev)

        breakdowns: list[CriterionBreakdown] = []
        for crit in test_case.criteria:
            rows = breakdown_bucket.get(crit.id, [])
            if not rows:
                breakdowns.append(
                    CriterionBreakdown(
                        criterion_id=crit.id,
                        criterion_name=crit.name,
                        calls_evaluated=0,
                    )
                )
                continue
            if crit.type == CriterionType.BOOLEAN:
                passed = [r.passed for r in rows if r.passed is not None]
                pass_rate = (
                    float(sum(1 for p in passed if p)) / len(passed) if passed else None
                )
                breakdowns.append(
                    CriterionBreakdown(
                        criterion_id=crit.id,
                        criterion_name=crit.name,
                        calls_evaluated=len(rows),
                        pass_rate=pass_rate,
                    )
                )
            else:
                scores = [float(r.score) for r in rows if r.score is not None]
                avg = sum(scores) / len(scores) if scores else None
                breakdowns.append(
                    CriterionBreakdown(
                        criterion_id=crit.id,
                        criterion_name=crit.name,
                        calls_evaluated=len(rows),
                        average_score=avg,
                    )
                )
        return run, breakdowns

    async def retry_failed(self, run_id: UUID) -> int:
        result = await self.db.execute(
            select(Call).where(
                Call.test_run_id == run_id,
                Call.status.in_([CallStatus.FAILED, CallStatus.TIMEOUT]),
            )
        )
        failed_calls = list(result.scalars().all())
        if not failed_calls:
            return 0

        for c in failed_calls:
            c.status = CallStatus.QUEUED
            c.error_message = None
            c.retell_call_id = None
            c.started_at = None
            c.completed_at = None

        await self.db.commit()

        from app.workers.tasks_calls import place_call

        for c in failed_calls:
            place_call.delay(str(c.id))

        return len(failed_calls)
