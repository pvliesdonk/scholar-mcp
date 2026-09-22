"""Rate limiter and retry helper for external API calls.

S2 rate-limit reference: ``docs/design/reference/semantic-scholar-api.md``.
"""

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

    Callers use it to distinguish throttling from other upstream failures.
    """


@dataclass
class RateLimiter:
    """Inter-request delay enforcer with a shared cooldown.

    Args:
        delay: Minimum seconds between requests.
    """

    delay: float
    _last: float = field(default=0.0, init=False)
    _cooldown_until: float = field(default=0.0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def acquire(self) -> None:
        """Wait for both spacing and the latest shared cooldown."""
        loop = asyncio.get_running_loop()
        while True:
            async with self._lock:
                now = loop.time()
                wait = max(self._last + self.delay, self._cooldown_until) - now
                if wait <= 0:
                    self._last = now
                    return
            await asyncio.sleep(wait)

    def cooldown(self, seconds: float) -> None:
        """Hold later requests after a throttle, without shortening an active hold.

        Args:
            seconds: Minimum wait from now before another request can start.
        """
        until = asyncio.get_running_loop().time() + seconds
        self._cooldown_until = max(self._cooldown_until, until)


_S2_MAX_RETRIES = 3
"""Attempts after the first failure when retrying a 429."""

_S2_BASE_DELAY_S = 1.0
"""First backoff wait in seconds; doubled on each subsequent retry."""


async def with_s2_retry(
    coro_func: Callable[[], Awaitable[Any]],
    limiter: RateLimiter,
    *,
    max_retries: int | None = None,
    base_delay: float | None = None,
) -> Any:
    """Call an async function with a shared exponential cooldown on HTTP 429.

    Args:
        coro_func: Zero-argument async callable to invoke.
        limiter: Rate limiter to acquire before each attempt.
        max_retries: Attempts after the first failure. Defaults to
            :data:`_S2_MAX_RETRIES`, resolved at call time so tests can
            shrink it rather than sleeping for real seconds.
        base_delay: Base delay in seconds for exponential backoff. Defaults
            to :data:`_S2_BASE_DELAY_S`, resolved the same way.

    Returns:
        The return value of ``coro_func`` on success.

    Raises:
        httpx.HTTPStatusError: If retries are exhausted or a non-429 error occurs.
    """
    retries = _S2_MAX_RETRIES if max_retries is None else max_retries
    delay_base = _S2_BASE_DELAY_S if base_delay is None else base_delay
    for attempt in range(retries + 1):
        await limiter.acquire()
        try:
            return await coro_func()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429:
                raise
            wait = delay_base * (2**attempt)
            limiter.cooldown(wait)
            if attempt == retries:
                raise
            logger.warning(
                "s2_rate_limited attempt=%d/%d waiting=%.1fs",
                attempt + 1,
                retries + 1,
                wait,
            )
    raise RuntimeError("unreachable")  # pragma: no cover


async def with_s2_try_once(
    coro_func: Callable[[], Awaitable[Any]],
    limiter: RateLimiter,
) -> Any:
    """Call an async function once; raise :class:`RateLimitedError` on 429.

    Unlike :func:`with_s2_retry`, this does not retry. The keepalive uses it
    for a single probe. A 429 still delays later requests through the limiter.

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
            limiter.cooldown(_S2_BASE_DELAY_S)
            raise RateLimitedError() from exc
        raise
