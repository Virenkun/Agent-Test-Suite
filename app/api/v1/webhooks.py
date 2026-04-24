from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.integrations.retell_client import RetellClient
from app.models.call import Call, CallStatus
from app.services.run_events import publish_run_event

log = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _extract_call_data(event: dict) -> dict:
    # Retell nests call details under `data` or `call` depending on event.
    data = event.get("data") or event.get("call") or event
    return data if isinstance(data, dict) else {}


@router.post("/retell")
async def retell_webhook(
    request: Request,
    x_retell_signature: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    raw = await request.body()
    log.info(
        "retell_webhook_received",
        headers={k: v for k, v in request.headers.items() if k.lower().startswith(("x-retell", "retell", "content-type"))},
        body_preview=raw[:300].decode("utf-8", errors="replace"),
    )
    client = RetellClient.__new__(RetellClient)
    try:
        client = RetellClient()
    except Exception:
        pass

    if x_retell_signature and not client.verify_webhook_signature(
        payload=raw, signature=x_retell_signature
    ):
        log.warning("retell_webhook_signature_invalid", signature=x_retell_signature[:40])
        raise HTTPException(status_code=401, detail="invalid signature")

    event = await request.json()
    event_type = event.get("event") or event.get("type") or "unknown"
    data = _extract_call_data(event)
    retell_call_id = data.get("call_id") or data.get("id")
    if not retell_call_id:
        log.warning("retell_webhook_missing_call_id", event=event_type)
        return {"status": "ignored"}

    result = await db.execute(select(Call).where(Call.retell_call_id == retell_call_id))
    call = result.scalar_one_or_none()
    if call is None:
        log.warning("retell_webhook_unknown_call", retell_call_id=retell_call_id)
        return {"status": "unknown_call"}

    terminal_events = {"call_ended", "call_analyzed", "call.ended"}
    if event_type not in terminal_events:
        log.info("retell_webhook_non_terminal", event=event_type)
        return {"status": "ok"}

    from app.services.call_ingestion import ingest_terminal_call

    ingest_terminal_call(call=call, data=data)
    await db.commit()

    publish_run_event(
        call.test_run_id,
        "call_finished",
        {"call_id": str(call.id), "status": call.status.value},
    )

    if call.status == CallStatus.COMPLETED:
        from app.workers.tasks_eval import evaluate_call

        evaluate_call.delay(str(call.id))
    else:
        from app.workers.tasks_eval import aggregate_run_if_complete

        aggregate_run_if_complete.delay(str(call.test_run_id))

    return {"status": "ok"}


def _flatten_transcript(messages: list) -> str:
    lines = []
    for m in messages or []:
        if isinstance(m, dict):
            role = m.get("role", "speaker")
            content = m.get("content") or m.get("text") or ""
            if content:
                lines.append(f"{role}: {content}")
    return "\n".join(lines)
