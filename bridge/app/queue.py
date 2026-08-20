from __future__ import annotations

import hashlib
import json
from typing import Any

from redis.asyncio import Redis

QUEUE_KEY = "orbybridge:webhooks:queued"
PROCESSING_KEY = "orbybridge:webhooks:processing"
DEAD_KEY = "orbybridge:webhooks:dead"
EVENT_TTL_SECONDS = 7 * 24 * 60 * 60


def event_key(payload: dict[str, Any]) -> str:
    event = str(payload.get("event") or "unknown")
    account = payload.get("account") or {}
    account_id = str(account.get("id") or "unknown")
    event_id = payload.get("id")
    if event_id is None:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        event_id = hashlib.sha256(canonical.encode()).hexdigest()
    return f"orbybridge:event:{account_id}:{event}:{event_id}"


async def enqueue_webhook(redis: Redis, payload: dict[str, Any]) -> bool:
    key = event_key(payload)
    first_delivery = await redis.set(key, "queued", ex=EVENT_TTL_SECONDS, nx=True)
    if not first_delivery:
        return False
    envelope = {"event_key": key, "attempt": 0, "payload": payload}
    try:
        await redis.lpush(QUEUE_KEY, json.dumps(envelope, separators=(",", ":"), default=str))
    except Exception:
        await redis.delete(key)
        raise
    return True
