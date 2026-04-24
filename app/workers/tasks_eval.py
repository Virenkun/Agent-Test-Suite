from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from celery import shared_task
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.logging import get_logger
from app.db.session import sync_session
from app.integrations.openai_client import OpenAIEvaluator
from app.models.call import Call, CallStatus
from app.models.call_evaluation import CallEvaluation
from app.models.criterion import CriterionType, EvaluationCriterion
from app.models.test_case import TestCase
from app.models.test_run import TestRun, TestRunStatus
from app.services.run_events import publish_run_event

log = get_logger(__name__)

_TERMINAL_STATUSES = {CallStatus.COMPLETED, CallStatus.FAILED, CallStatus.TIMEOUT}


@shared_task(
    bind=True,
    name="app.workers.tasks_eval.evaluate_call",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def evaluate_call(self, call_id: str) -> None:
    """Run each criterion on the call's transcript and store evaluations."""
    with sync_session() as session:
        call = session.get(Call, UUID(call_id))
        if call is None:
            log.warning("evaluate_call_not_found", call_id=call_id)
            return
        if call.status != CallStatus.COMPLETED or not call.transcript:
            log.info("evaluate_call_skip", call_id=call_id, status=call.status.value)
            return

        run = session.get(TestRun, call.test_run_id)
        tc = session.execute(
            select(TestCase)
            .options(selectinload(TestCase.criteria))
            .where(TestCase.id == run.test_case_id)
        ).scalar_one()

        existing = {
            row.criterion_id
            for row in session.execute(
                select(CallEvaluation).where(CallEvaluation.call_id == call.id)
            ).scalars()
        }

        evaluator = OpenAIEvaluator()
        for crit in tc.criteria:
            if crit.id in existing:
                continue
            result = evaluator.evaluate(transcript=call.transcript, criterion=crit)
            session.add(
                CallEvaluation(
                    call_id=call.id,
                    criterion_id=crit.id,
                    passed=result.passed,
                    score=Decimal(str(result.score)) if result.score is not None else None,
                    reasoning=result.reasoning,
                    confidence=Decimal(str(result.confidence)),
                    llm_cost_usd=result.cost_usd,
                )
            )

    publish_run_event(
        run.id, "call_evaluated", {"call_id": call_id}
    )
    aggregate_run_if_complete.delay(str(run.id))


@shared_task(name="app.workers.tasks_eval.aggregate_run_if_complete")
def aggregate_run_if_complete(test_run_id: str) -> None:
    settings = get_settings()
    with sync_session() as session:
        run = session.get(TestRun, UUID(test_run_id))
        if run is None:
            return

        calls = list(
            session.execute(
                select(Call)
                .options(selectinload(Call.evaluations))
                .where(Call.test_run_id == run.id)
            ).scalars()
        )
        if not calls:
            return
        if any(c.status not in _TERMINAL_STATUSES for c in calls):
            return

        tc = session.execute(
            select(TestCase)
            .options(selectinload(TestCase.criteria))
            .where(TestCase.id == run.test_case_id)
        ).scalar_one()
        criteria_by_id = {c.id: c for c in tc.criteria}

        # Weighted aggregate across completed calls
        total_weight = sum((c.weight for c in tc.criteria), start=Decimal("0"))
        sum_normalized = Decimal("0")
        count = 0
        total_cost = Decimal("0")
        completed = 0
        failed = 0

        for call in calls:
            total_cost += call.cost_usd or Decimal("0")
            if call.status != CallStatus.COMPLETED:
                failed += 1
                continue
            completed += 1
            for ev in call.evaluations:
                crit = criteria_by_id.get(ev.criterion_id)
                if crit is None:
                    continue
                total_cost += ev.llm_cost_usd or Decimal("0")
                if crit.type == CriterionType.BOOLEAN and ev.passed is not None:
                    normalized = Decimal("1") if ev.passed else Decimal("0")
                elif (
                    crit.type == CriterionType.SCORE
                    and ev.score is not None
                    and crit.max_score
                ):
                    normalized = Decimal(ev.score) / Decimal(crit.max_score)
                else:
                    continue
                sum_normalized += normalized * crit.weight
            count += 1

        aggregate = None
        if count and total_weight > 0:
            aggregate = sum_normalized / (Decimal(count) * total_weight)
            aggregate = aggregate.quantize(Decimal("0.0001"))

        run.total_cost_usd = total_cost.quantize(Decimal("0.0001"))
        run.completed_calls = completed
        run.failed_calls = failed
        run.aggregate_score = aggregate
        run.pass_ = (
            bool(aggregate is not None and aggregate >= Decimal(str(settings.default_pass_threshold)))
            if aggregate is not None
            else None
        )
        run.completed_at = datetime.now(timezone.utc)
        if completed == 0:
            run.status = TestRunStatus.FAILED
            terminal_event = "run_failed"
        elif failed > 0:
            run.status = TestRunStatus.PARTIAL
            terminal_event = "run_partial"
        else:
            run.status = TestRunStatus.COMPLETED
            terminal_event = "run_completed"

    publish_run_event(
        test_run_id,
        terminal_event,
        {
            "aggregate_score": str(aggregate) if aggregate is not None else None,
            "pass": run.pass_,
            "completed_calls": completed,
            "failed_calls": failed,
            "total_cost_usd": str(run.total_cost_usd),
        },
    )

    # Phase 3: generate LLM failure insights asynchronously.
    try:
        from app.workers.tasks_insights import generate_insights

        generate_insights.delay(test_run_id)
    except Exception as e:
        log.warning("enqueue_insights_failed", error=str(e))

    # Phase 3: if this run is part of a suite run, check if the parent is done.
    if run.test_suite_run_id is not None:
        maybe_finalize_suite_run.delay(str(run.test_suite_run_id))


@shared_task(name="app.workers.tasks_eval.maybe_finalize_suite_run")
def maybe_finalize_suite_run(suite_run_id: str) -> None:
    """If every child TestRun is terminal, compute parent aggregates."""
    from app.models.test_suite import TestSuiteRun
    from app.services.run_events import publish_run_event as _pub

    with sync_session() as session:
        suite_run = session.get(TestSuiteRun, UUID(suite_run_id))
        if suite_run is None:
            return
        child_runs = list(
            session.execute(
                select(TestRun).where(TestRun.test_suite_run_id == suite_run.id)
            ).scalars()
        )
        if not child_runs:
            return
        terminal_states = {
            TestRunStatus.COMPLETED,
            TestRunStatus.FAILED,
            TestRunStatus.PARTIAL,
        }
        if any(r.status not in terminal_states for r in child_runs):
            # Still running; emit an incremental update instead.
            _pub(
                suite_run.id,
                "child_updated",
                {
                    "terminal": sum(
                        1 for r in child_runs if r.status in terminal_states
                    ),
                    "total": len(child_runs),
                },
            )
            return

        scores = [r.aggregate_score for r in child_runs if r.aggregate_score is not None]
        passing = [r for r in child_runs if r.pass_ is True]
        avg = (
            (sum(scores, Decimal("0")) / Decimal(len(scores))).quantize(
                Decimal("0.0001")
            )
            if scores
            else None
        )
        pass_rate = (
            (Decimal(len(passing)) / Decimal(len(child_runs))).quantize(
                Decimal("0.0001")
            )
            if child_runs
            else Decimal("0")
        )
        total_cost = sum(
            (r.total_cost_usd or Decimal("0") for r in child_runs),
            start=Decimal("0"),
        ).quantize(Decimal("0.0001"))

        suite_run.average_aggregate_score = avg
        suite_run.pass_rate = pass_rate
        suite_run.total_cost_usd = total_cost
        suite_run.completed_at = datetime.now(timezone.utc)
        if all(r.status == TestRunStatus.COMPLETED for r in child_runs):
            suite_run.status = TestRunStatus.COMPLETED
            terminal = "suite_run_completed"
        elif all(r.status == TestRunStatus.FAILED for r in child_runs):
            suite_run.status = TestRunStatus.FAILED
            terminal = "suite_run_failed"
        else:
            suite_run.status = TestRunStatus.PARTIAL
            terminal = "suite_run_partial"

    publish_run_event(
        suite_run_id,
        terminal,
        {
            "average_aggregate_score": str(avg) if avg is not None else None,
            "pass_rate": str(pass_rate),
            "total_cost_usd": str(total_cost),
        },
    )
