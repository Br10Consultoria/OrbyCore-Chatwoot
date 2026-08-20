from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from redis.asyncio import Redis

from .automation import process_automation
from .config import get_settings
from .queue import DEAD_KEY, EVENT_TTL_SECONDS, PROCESSING_KEY, QUEUE_KEY

logger = logging.getLogger(__name__)


async def recover_interrupted(redis: Redis) -> int:
    recovered = 0
    while await redis.rpoplpush(PROCESSING_KEY, QUEUE_KEY):
        recovered += 1
    return recovered


async def process_envelope(redis: Redis, raw: str, envelope: dict[str, Any]) -> None:
    settings = get_settings()
    event_key = str(envelope["event_key"])
    attempt = int(envelope.get("attempt") or 0)
    try:
        result = await process_automation(envelope["payload"], settings)
    except Exception:
        attempt += 1
        envelope["attempt"] = attempt
        retry_raw = json.dumps(envelope, separators=(",", ":"), default=str)
        if attempt >= settings.webhook_max_attempts:
            async with redis.pipeline(transaction=True) as pipe:
                pipe.lrem(PROCESSING_KEY, 1, raw)
                pipe.lpush(DEAD_KEY, retry_raw)
                pipe.set(event_key, "dead", ex=EVENT_TTL_SECONDS)
                await pipe.execute()
            logger.exception("Webhook enviado para dead-letter", extra={"attempt": attempt})
            return
        await redis.set(event_key, f"retry:{attempt}", ex=EVENT_TTL_SECONDS)
        await asyncio.sleep(min(2**attempt, settings.webhook_max_backoff_seconds))
        async with redis.pipeline(transaction=True) as pipe:
            pipe.lrem(PROCESSING_KEY, 1, raw)
            pipe.lpush(QUEUE_KEY, retry_raw)
            await pipe.execute()
        logger.exception("Webhook reagendado", extra={"attempt": attempt})
        return

    async with redis.pipeline(transaction=True) as pipe:
        pipe.lrem(PROCESSING_KEY, 1, raw)
        pipe.set(event_key, f"done:{result}", ex=EVENT_TTL_SECONDS)
        await pipe.execute()


async def run_worker() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.ping()
        recovered = await recover_interrupted(redis)
        if recovered:
            logger.warning("Webhooks interrompidos recuperados", extra={"count": recovered})
        while True:
            raw = await redis.brpoplpush(QUEUE_KEY, PROCESSING_KEY, timeout=5)
            if raw is None:
                continue
            try:
                envelope = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                await redis.lrem(PROCESSING_KEY, 1, raw)
                await redis.lpush(DEAD_KEY, raw)
                logger.exception("Envelope de webhook inválido")
                continue
            await process_envelope(redis, raw, envelope)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(run_worker())
