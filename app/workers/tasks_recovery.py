"""Fallback poller for calls whose Retell webhook was missed."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from celery import shared_task
from sqlalchemy import select

from app.core.logging import get_logger
from app.db.session import sync_session
from app.integrations.retell_client import RetellClient
from app.models.call import Call, CallStatus
from app.services.call_ingestion import ingest_terminal_call
from app.services.run_events import publish_run_event

log = get_logger(__name__)

STUCK_THRESHOLD_MIN = 10     # consider a call stuck after this many minutes in_progress
TIMEOUT_THRESHOLD_MIN = 30   # hard timeout past this window


@shared_task(name="app.workers.tasks_recovery.recover_stuck_calls")
def recover_stuck_calls() -> dict:
    """Find in_progress calls older than 10 min. Fetch from Retell; ingest if terminal.

    Returns a small dict with counts for observability.
    """
    recovered = 0
    still_running = 0
    timed_out = 0
    errors = 0

    now = datetime.now(timezone.utc)
    cutoff_stuck = now - timedelta(minutes=STUCK_THRESHOLD_MIN)
    cutoff_timeout = now - timedelta(minutes=TIMEOUT_THRESHOLD_MIN)

    with sync_session() as session:
        stuck = list(
            session.execute(
                select(Call).where(
                    Call.status == CallStatus.IN_PROGRESS,
                    Call.started_at.is_not(None),
                    Call.started_at < cutoff_stuck,
                )
            ).scalars()
        )

    if not stuck:
        return {"recovered": 0, "still_running": 0, "timed_out": 0, "errors": 0}

    client = None
    try:
        client = RetellClient()
    except Exception as e:
        log.warning("recover_skip_no_retell", error=str(e))
        return {"recovered": 0, "still_running": 0, "timed_out": 0, "errors": 1}

    # Process each candidate in its own session so one failure doesn't roll back others.
    for candidate in stuck:
        try:
            with sync_session() as session:
                call = session.get(Call, candidate.id)
                if call is None or call.status != CallStatus.IN_PROGRESS:
                    continue
                if not call.retell_call_id:
                    # Never got a Retell id — nothing to recover.
                    if call.started_at and call.started_at < cutoff_timeout:
                        call.status = CallStatus.TIMEOUT
                        call.error_message = "no_retell_call_id"
                        call.completed_at = now
                        publish_run_event(
                            call.test_run_id,
                            "call_finished",
                            {"call_id": str(call.id), "status": "timeout"},
                        )
                        timed_out += 1
                    continue

                retell_data = client.get_call(call.retell_call_id)
                rstatus = str(
                    retell_data.get("call_status") or ""
                ).lower()
                terminal_statuses = {"ended", "error", "not_connected", "completed"}
                if rstatus in terminal_statuses or retell_data.get("end_timestamp"):
                    ingest_terminal_call(call=call, data=retell_data)
                    run_id = call.test_run_id
                    status_value = call.status.value
                    session.commit()
                    publish_run_event(
                        run_id,
                        "call_finished",
                        {
                            "call_id": str(call.id),
                            "status": status_value,
                            "source": "poller",
                        },
                    )
                    # Enqueue evaluation or aggregate
                    if call.status == CallStatus.COMPLETED:
                        from app.workers.tasks_eval import evaluate_call

                        evaluate_call.delay(str(call.id))
                    else:
                        from app.workers.tasks_eval import (
                            aggregate_run_if_complete,
                        )

                        aggregate_run_if_complete.delay(str(run_id))
                    recovered += 1
                elif call.started_at and call.started_at < cutoff_timeout:
                    call.status = CallStatus.TIMEOUT
                    call.error_message = "recovery_timeout"
                    call.completed_at = now
                    run_id = call.test_run_id
                    session.commit()
                    publish_run_event(
                        run_id,
                        "call_finished",
                        {"call_id": str(call.id), "status": "timeout"},
                    )
                    from app.workers.tasks_eval import (
                        aggregate_run_if_complete,
                    )

                    aggregate_run_if_complete.delay(str(run_id))
                    timed_out += 1
                else:
                    still_running += 1
        except Exception as e:
            log.error(
                "recover_call_error",
                call_id=str(candidate.id),
                error=str(e),
            )
            errors += 1

    log.info(
        "recover_stuck_calls_done",
        recovered=recovered,
        still_running=still_running,
        timed_out=timed_out,
        errors=errors,
    )
    return {
        "recovered": recovered,
        "still_running": still_running,
        "timed_out": timed_out,
        "errors": errors,
    }
