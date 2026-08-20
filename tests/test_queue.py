import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from app import worker
from app.queue import DEAD_KEY, PROCESSING_KEY, QUEUE_KEY, enqueue_webhook, event_key


@pytest.mark.asyncio
async def test_enqueue_is_idempotent_per_account_event_and_id():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    payload = {"event": "message_created", "id": 10, "account": {"id": 2}}

    assert await enqueue_webhook(redis, payload) is True
    assert await enqueue_webhook(redis, payload) is False
    assert await redis.llen(QUEUE_KEY) == 1
    assert event_key(payload) != event_key({**payload, "event": "conversation_created"})
    await redis.aclose()


@pytest.mark.asyncio
async def test_worker_acknowledges_success(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    envelope = {"event_key": "event:test", "attempt": 0, "payload": {"event": "ignored"}}
    raw = json.dumps(envelope)
    await redis.lpush(PROCESSING_KEY, raw)
    monkeypatch.setattr(worker, "process_automation", AsyncMock(return_value="ignored"))
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace())

    await worker.process_envelope(redis, raw, envelope)

    assert await redis.llen(PROCESSING_KEY) == 0
    assert await redis.get("event:test") == "done:ignored"
    await redis.aclose()


@pytest.mark.asyncio
async def test_worker_moves_exhausted_failure_to_dead_letter(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    envelope = {"event_key": "event:failed", "attempt": 0, "payload": {}}
    raw = json.dumps(envelope)
    await redis.lpush(PROCESSING_KEY, raw)
    monkeypatch.setattr(worker, "process_automation", AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(webhook_max_attempts=1, webhook_max_backoff_seconds=1),
    )

    await worker.process_envelope(redis, raw, envelope)

    assert await redis.llen(DEAD_KEY) == 1
    assert await redis.get("event:failed") == "dead"
    await redis.aclose()
