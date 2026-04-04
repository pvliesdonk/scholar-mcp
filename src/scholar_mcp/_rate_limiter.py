"""Rate limiter and retry helper for external API calls."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RateLimitedError(Exception):
    """Raised on HTTP 429 in try-once mode.

    Signals the caller to queue the operation for background retry.
    """


@dataclass
class RateLimiter:
    """Inter-request delay enforcer.

    Args:
        delay: Minimum seconds between requests.
    """

    delay: float
    _last: float = field(default=0.0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def acquire(self) -> None:
        """Wait until the minimum inter-request delay has elapsed."""
        async with self._lock:
            now = asyncio.get_running_loop().time()
            wait = self._last + self.delay - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = asyncio.get_running_loop().time()


async def with_s2_retry(
    coro_func: Callable[[], Awaitable[Any]],
    limiter: RateLimiter,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> Any:
    """Call an async function with exponential backoff on HTTP 429.

    Args:
        coro_func: Zero-argument async callable to invoke.
        limiter: Rate limiter to acquire before each attempt.
        max_retries: Maximum number of retry attempts after the first failure.
        base_delay: Base delay in seconds for exponential backoff.

    Returns:
        The return value of ``coro_func`` on success.

    Raises:
        httpx.HTTPStatusError: If retries are exhausted or a non-429 error occurs.
    """
    for attempt in range(max_retries + 1):
        await limiter.acquire()
        try:
            return await coro_func()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < max_retries:
                wait = base_delay * (2**attempt)
                logger.warning(
                    "s2_rate_limited attempt=%d/%d waiting=%.1fs",
                    attempt + 1,
                    max_retries + 1,
                    wait,
                )
                await asyncio.sleep(wait)
            else:
                raise
    raise RuntimeError("unreachable")  # pragma: no cover


async def with_s2_try_once(
    coro_func: Callable[[], Awaitable[Any]],
    limiter: RateLimiter,
) -> Any:
    """Call an async function once; raise :class:`RateLimitedError` on 429.

    Unlike :func:`with_s2_retry`, this does **not** retry.  It is used
    for the initial optimistic attempt before falling back to background
    queueing.

    Args:
        coro_func: Zero-argument async callable to invoke.
        limiter: Rate limiter to acquire before the attempt.

    Returns:
        The return value of ``coro_func`` on success.

    Raises:
        RateLimitedError: If the API responds with HTTP 429.
        httpx.HTTPStatusError: For non-429 HTTP errors.
    """
    await limiter.acquire()
    try:
        return await coro_func()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise RateLimitedError() from exc
        raise
