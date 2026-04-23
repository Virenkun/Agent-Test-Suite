from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from celery import shared_task
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.db.session import sync_session
from app.integrations.retell_client import RetellClient, build_dynamic_variables
from app.models.call import Call, CallStatus
from app.models.test_case import TestCase
from app.models.test_run import TestRun, TestRunStatus
from app.services.run_events import publish_run_event

log = get_logger(__name__)


@shared_task(
    bind=True,
    name="app.workers.tasks_calls.place_call",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def place_call(self, call_id: str) -> None:
    """Place an outbound Retell call for a given `calls.id`."""
    with sync_session() as session:
        call = session.get(Call, UUID(call_id))
        if call is None:
            log.warning("place_call_not_found", call_id=call_id)
            return
        if call.status != CallStatus.QUEUED:
            log.info("place_call_skip_non_queued", call_id=call_id, status=call.status.value)
            return

        run = session.get(TestRun, call.test_run_id)
        if run is None:
            return
        tc = session.execute(
            select(TestCase)
            .options(selectinload(TestCase.persona))
            .where(TestCase.id == run.test_case_id)
        ).scalar_one()

        # Cost cap enforcement (batch granularity)
        current_cost = session.scalar(
            select(func.coalesce(func.sum(Call.cost_usd), 0)).where(
                Call.test_run_id == run.id
            )
        ) or Decimal("0")
        if run.max_cost_usd is not None and Decimal(current_cost) >= run.max_cost_usd:
            call.status = CallStatus.FAILED
            call.error_message = "cost_cap_exceeded"
            call.completed_at = datetime.now(timezone.utc)
            run.failed_calls = (run.failed_calls or 0) + 1
            publish_run_event(
                run.id,
                "call_cost_capped",
                {"call_id": str(call.id)},
            )
            return

        # Mark run running on first placed call
        if run.status == TestRunStatus.PENDING:
            run.status = TestRunStatus.RUNNING
            run.started_at = datetime.now(timezone.utc)

        client = RetellClient()
        placed = client.place_call(
            to_number=run.agent_phone_number,
            dynamic_variables=build_dynamic_variables(tc.persona, tc),
            metadata={"call_id": str(call.id), "test_run_id": str(run.id)},
            max_duration_sec=run.max_duration_sec,
        )

        call.retell_call_id = placed.retell_call_id
        call.status = CallStatus.IN_PROGRESS
        call.started_at = datetime.now(timezone.utc)
        log.info(
            "place_call_ok",
            call_id=call_id,
            retell_call_id=placed.retell_call_id,
        )
        publish_run_event(
            run.id,
            "call_placed",
            {"call_id": str(call.id), "retell_call_id": placed.retell_call_id},
        )
