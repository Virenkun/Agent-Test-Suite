"""Server-Sent Events endpoints for live test run updates."""
import asyncio
import json
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.test_run import TestRun, TestRunStatus
from app.services.run_events import channel_for

log = get_logger(__name__)

router = APIRouter(tags=["streams"])

_TERMINAL = {TestRunStatus.COMPLETED, TestRunStatus.FAILED, TestRunStatus.PARTIAL}
_HEARTBEAT_SEC = 15


def _sse(data: str, event: str | None = None) -> bytes:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {data}\n\n".encode()


async def _run_snapshot(db: AsyncSession, run_id: UUID) -> dict:
    result = await db.execute(select(TestRun).where(TestRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise NotFoundError(f"TestRun {run_id} not found")
    return {
        "id": str(run.id),
        "status": run.status.value,
        "completed_calls": run.completed_calls,
        "failed_calls": run.failed_calls,
        "requested_calls": run.requested_calls,
        "total_cost_usd": str(run.total_cost_usd),
        "aggregate_score": str(run.aggregate_score) if run.aggregate_score is not None else None,
        "pass": run.pass_,
    }


@router.get("/test-runs/{run_id}/stream")
async def stream_test_run(
    run_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream run state changes via SSE.

    Emits an initial snapshot, then relays Redis pub/sub messages for this run.
    Ends when the run is terminal or the client disconnects.
    """
    snapshot = await _run_snapshot(db, run_id)

    async def event_gen():
        # Initial snapshot so the client doesn't need a separate fetch.
        yield _sse(json.dumps(snapshot), event="snapshot")

        if snapshot["status"] in {s.value for s in _TERMINAL}:
            yield _sse(json.dumps({"reason": "already_terminal"}), event="end")
            return

        client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        pubsub = client.pubsub()
        await pubsub.subscribe(channel_for(run_id))
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=_HEARTBEAT_SEC,
                    )
                except asyncio.TimeoutError:
                    yield _sse("{}", event="heartbeat")
                    continue
                if not message:
                    continue
                data = message.get("data")
                if not isinstance(data, str):
                    continue
                yield _sse(data, event="update")
                # If the worker emitted a terminal update, refresh snapshot and stop.
                try:
                    parsed = json.loads(data)
                except Exception:
                    parsed = {}
                if parsed.get("event") in {"run_completed", "run_failed", "run_partial"}:
                    final = await _run_snapshot(db, run_id)
                    yield _sse(json.dumps(final), event="snapshot")
                    yield _sse(json.dumps({"reason": "terminal"}), event="end")
                    break
        finally:
            try:
                await pubsub.unsubscribe(channel_for(run_id))
                await pubsub.close()
                await client.aclose()
            except Exception:
                pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _suite_run_snapshot(db: AsyncSession, suite_run_id: UUID) -> dict:
    from app.models.test_suite import TestSuiteRun

    result = await db.execute(
        select(TestSuiteRun).where(TestSuiteRun.id == suite_run_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise NotFoundError(f"TestSuiteRun {suite_run_id} not found")
    return {
        "id": str(run.id),
        "status": run.status.value,
        "average_aggregate_score": str(run.average_aggregate_score)
        if run.average_aggregate_score is not None
        else None,
        "pass_rate": str(run.pass_rate) if run.pass_rate is not None else None,
        "total_cost_usd": str(run.total_cost_usd),
    }


@router.get("/test-suite-runs/{suite_run_id}/stream")
async def stream_test_suite_run(
    suite_run_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """SSE for a test-suite-run: parent + child updates."""
    snapshot = await _suite_run_snapshot(db, suite_run_id)

    async def event_gen():
        yield _sse(json.dumps(snapshot), event="snapshot")
        if snapshot["status"] in {s.value for s in _TERMINAL}:
            yield _sse(json.dumps({"reason": "already_terminal"}), event="end")
            return
        client = aioredis.from_url(
            get_settings().redis_url, decode_responses=True
        )
        pubsub = client.pubsub()
        await pubsub.subscribe(channel_for(suite_run_id))
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=_HEARTBEAT_SEC,
                    )
                except asyncio.TimeoutError:
                    yield _sse("{}", event="heartbeat")
                    continue
                if not message:
                    continue
                data = message.get("data")
                if not isinstance(data, str):
                    continue
                yield _sse(data, event="update")
                try:
                    parsed = json.loads(data)
                except Exception:
                    parsed = {}
                if parsed.get("event") in {
                    "suite_run_completed",
                    "suite_run_failed",
                    "suite_run_partial",
                }:
                    final = await _suite_run_snapshot(db, suite_run_id)
                    yield _sse(json.dumps(final), event="snapshot")
                    yield _sse(json.dumps({"reason": "terminal"}), event="end")
                    break
        finally:
            try:
                await pubsub.unsubscribe(channel_for(suite_run_id))
                await pubsub.close()
                await client.aclose()
            except Exception:
                pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
