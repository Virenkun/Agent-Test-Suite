"""Shared ingestion logic for terminal call data — used by both the Retell webhook and the fallback poller."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.models.call import Call, CallStatus


def _flatten_transcript(messages: Any) -> str:
    if not messages:
        return ""
    lines = []
    for m in messages:
        if isinstance(m, dict):
            role = m.get("role", "speaker")
            content = m.get("content") or m.get("text") or ""
            if content:
                lines.append(f"{role}: {content}")
    return "\n".join(lines)


def ingest_terminal_call(*, call: Call, data: dict) -> None:
    """Mutate `call` with data from a Retell terminal-call payload.

    `data` is the `call` object from a Retell webhook event or the response body
    of retell.call.retrieve().
    """
    transcript = data.get("transcript") or _flatten_transcript(
        data.get("transcript_object") or data.get("messages") or []
    )
    recording_url = data.get("recording_url") or data.get("audio_url")

    duration_ms = data.get("duration_ms") or data.get("call_length_ms") or 0
    duration_sec = (
        int(duration_ms / 1000) if duration_ms else data.get("duration_sec")
    )

    # Retell returns combined_cost in CENTS; convert to dollars.
    if isinstance(data.get("call_cost"), dict):
        cost_cents = data["call_cost"].get("combined_cost")
    else:
        cost_cents = data.get("cost")

    disconnect_reason = (
        data.get("disconnection_reason")
        or data.get("end_reason")
        or data.get("call_status")
    )

    call.transcript = transcript or call.transcript
    call.recording_url = recording_url or call.recording_url
    if duration_sec is not None:
        call.duration_sec = duration_sec
    if cost_cents is not None:
        try:
            call.cost_usd = (Decimal(str(cost_cents)) / Decimal("100")).quantize(
                Decimal("0.0001")
            )
        except Exception:
            pass
    call.completed_at = datetime.now(timezone.utc)

    if disconnect_reason and "error" in str(disconnect_reason).lower():
        call.status = CallStatus.FAILED
        call.error_message = str(disconnect_reason)
    elif not transcript and not call.transcript:
        call.status = CallStatus.FAILED
        call.error_message = "no_transcript"
    else:
        call.status = CallStatus.COMPLETED
