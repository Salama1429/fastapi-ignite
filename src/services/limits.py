"""Rate limiting and idempotency helpers."""
from __future__ import annotations

import time
from typing import Optional

import redis.asyncio as redis
from fastapi import HTTPException, status

from src.core.config import settings

_redis_client: redis.Redis | None = None


async def _get_client() -> redis.Redis:
    """Return a cached Redis client instance."""

    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            str(settings.REDIS_URI), decode_responses=True
        )
    return _redis_client


async def check_rate_limit(tenant_id: str) -> None:
    """Enforce a simple fixed-window rate limit per tenant."""

    client = await _get_client()
    minute_window = int(time.time() // 60)
    key = f"rl:{tenant_id}:{minute_window}"
    current = await client.incr(key)
    if current == 1:
        await client.expire(key, 60)
    if current > settings.RATE_LIMIT_RPM:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )


async def ensure_idempotent(tenant_id: str, key: Optional[str]) -> None:
    """Reject duplicate POST requests sharing the same idempotency key."""

    if not key:
        return
    client = await _get_client()
    redis_key = f"idemp:{tenant_id}:{key}"
    was_set = await client.set(redis_key, "1", ex=60 * 30, nx=True)
    if not was_set:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate request (idempotency)",
        )
