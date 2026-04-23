"""Redis pub/sub for real-time run updates streamed to the Next.js UI via SSE."""
import json
from typing import Any
from uuid import UUID

import redis

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_RUN_CHANNEL = "run:{run_id}"
_sync_redis: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _sync_redis
    if _sync_redis is None:
        _sync_redis = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _sync_redis


def channel_for(run_id: UUID | str) -> str:
    return _RUN_CHANNEL.format(run_id=str(run_id))


def publish_run_event(run_id: UUID | str, event: str, payload: dict[str, Any] | None = None) -> None:
    """Fire-and-forget pub/sub. Swallow errors so workers never fail on telemetry."""
    try:
        message = json.dumps({"event": event, **(payload or {})})
        _redis().publish(channel_for(run_id), message)
    except Exception as e:
        log.warning("run_event_publish_failed", error=str(e), run_id=str(run_id), event=event)
