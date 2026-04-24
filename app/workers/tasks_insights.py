"""LLM-generated failure insights for completed test runs."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.db.session import sync_session
from app.integrations.openai_client import OpenAIEvaluator
from app.models.call import Call, CallStatus
from app.models.call_evaluation import CallEvaluation
from app.models.criterion import CriterionType, EvaluationCriterion
from app.models.test_case import TestCase
from app.models.test_run import TestRun
from app.services.run_events import publish_run_event

log = get_logger(__name__)


@shared_task(name="app.workers.tasks_insights.generate_insights")
def generate_insights(test_run_id: str) -> None:
    """Analyze a completed run and write actionable insights to test_runs.insights."""
    try:
        with sync_session() as session:
            run = session.get(TestRun, UUID(test_run_id))
            if run is None:
                return
            # Load criteria + calls + evaluations
            tc = session.execute(
                select(TestCase)
                .options(selectinload(TestCase.criteria))
                .where(TestCase.id == run.test_case_id)
            ).scalar_one()
            criteria_by_id: dict[UUID, EvaluationCriterion] = {
                c.id: c for c in tc.criteria
            }

            calls = list(
                session.execute(
                    select(Call)
                    .options(selectinload(Call.evaluations))
                    .where(Call.test_run_id == run.id)
                ).scalars()
            )

            # Build a compact summary to send to the LLM.
            per_crit: dict[UUID, dict] = {
                cid: {
                    "name": c.name,
                    "type": c.type.value,
                    "weight": str(c.weight),
                    "max_score": c.max_score,
                    "fail_rate": 0.0,
                    "failures": [],
                }
                for cid, c in criteria_by_id.items()
            }
            fail_counts: dict[UUID, int] = {cid: 0 for cid in criteria_by_id}
            eval_counts: dict[UUID, int] = {cid: 0 for cid in criteria_by_id}

            for call in calls:
                if call.status != CallStatus.COMPLETED:
                    continue
                for ev in call.evaluations:
                    crit = criteria_by_id.get(ev.criterion_id)
                    if crit is None:
                        continue
                    eval_counts[crit.id] += 1
                    failed = False
                    if crit.type == CriterionType.BOOLEAN and ev.passed is False:
                        failed = True
                    elif (
                        crit.type == CriterionType.SCORE
                        and ev.score is not None
                        and crit.max_score
                        and Decimal(ev.score) / Decimal(crit.max_score) < Decimal("0.5")
                    ):
                        failed = True
                    if failed:
                        fail_counts[crit.id] += 1
                        per_crit[crit.id]["failures"].append(
                            {
                                "reasoning": (ev.reasoning or "")[:400],
                                "score": str(ev.score)
                                if ev.score is not None
                                else None,
                                "passed": ev.passed,
                            }
                        )

            for cid, bucket in per_crit.items():
                total = eval_counts.get(cid, 0)
                bucket["fail_rate"] = (
                    round(fail_counts[cid] / total, 3) if total else 0.0
                )
                # Cap reasoning samples so prompt stays compact.
                bucket["failures"] = bucket["failures"][:5]

            payload = {
                "test_case": {"name": tc.name, "context": tc.context or ""},
                "aggregate_score": str(run.aggregate_score)
                if run.aggregate_score is not None
                else None,
                "pass_threshold": "0.7",
                "overall_pass": run.pass_,
                "criteria": list(per_crit.values()),
            }

        # LLM call outside the DB session
        result = OpenAIEvaluator().summarize_failures(payload=payload)

        with sync_session() as session:
            run = session.get(TestRun, UUID(test_run_id))
            if run is None:
                return
            run.insights = {
                "top_issues": result.get("top_issues", []),
                "suggestions": result.get("suggestions", []),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        publish_run_event(
            test_run_id,
            "insights_ready",
            {"suggestion_count": len(result.get("suggestions", []))},
        )
    except Exception as e:
        log.warning("insights_failed", run_id=test_run_id, error=str(e))
