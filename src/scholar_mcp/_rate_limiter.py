"""Rate limiter and retry helper for external API calls.

S2 rate-limit reference: ``docs/design/reference/semantic-scholar-api.md``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RateLimitedError(Exception):
    """Raised on HTTP 429 in try-once mode.

    Callers use it to distinguish throttling from other upstream failures.
    """


class S2RetryDeadlineExceeded(Exception):
    """The caller's job can no longer retain an eventual S2 answer."""


@dataclass
class S2RetryContext:
    """Per-tool throttle signal and last useful retry deadline."""

    deadline: float
    throttled: asyncio.Event = field(default_factory=asyncio.Event)
    retry_after_s: float = 1.0

    def notify(self, wait: float) -> None:
        """Expose an S2 gate wait to the tool wrapper."""
        self.retry_after_s = max(wait, 0.001)
        self.throttled.set()


S2_RETRY_CONTEXT: ContextVar[S2RetryContext | None] = ContextVar(
    "s2_retry_context", default=None
)


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
                context = S2_RETRY_CONTEXT.get()
                if context is not None and self._cooldown_until > now:
                    context.notify(self._cooldown_until - now)
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

    Under an S2 tool context, retry until the job's last useful deadline.
    Direct client calls keep the finite retry ladder.

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
        S2RetryDeadlineExceeded: If the contextual retry window closes.
        httpx.HTTPStatusError: If direct-call retries are exhausted or a
            non-429 error occurs.
    """
    retries = _S2_MAX_RETRIES if max_retries is None else max_retries
    delay_base = _S2_BASE_DELAY_S if base_delay is None else base_delay
    context = S2_RETRY_CONTEXT.get()
    attempt = 0
    while True:
        await _acquire_within_deadline(limiter, context)
        try:
            return await coro_func()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429:
                raise
            if _back_off(limiter, context, attempt, retries, delay_base):
                raise
            attempt += 1


async def _acquire_within_deadline(
    limiter: RateLimiter, context: S2RetryContext | None
) -> None:
    """Acquire the limiter, within the job's deadline once S2 has throttled.

    Args:
        limiter: Rate limiter to acquire.
        context: The S2 tool's retry context, or ``None`` for a direct call.

    Raises:
        S2RetryDeadlineExceeded: If the context's retry window has closed.
    """
    if context is None or not context.throttled.is_set():
        await limiter.acquire()
        return
    remaining = context.deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise S2RetryDeadlineExceeded()
    try:
        await asyncio.wait_for(limiter.acquire(), timeout=remaining)
    except TimeoutError as exc:
        raise S2RetryDeadlineExceeded() from exc


def _back_off(
    limiter: RateLimiter,
    context: S2RetryContext | None,
    attempt: int,
    retries: int,
    delay_base: float,
) -> bool:
    """Start the shared cooldown after a 429 and say whether to give up.

    Under an S2 tool context the job is told how long to wait and the retry
    continues until its deadline; a direct call gives up after *retries*.

    Args:
        limiter: Rate limiter whose cooldown every caller shares.
        context: The S2 tool's retry context, or ``None`` for a direct call.
        attempt: Attempts that have failed so far, minus one.
        retries: Attempts a direct call may make after the first failure.
        delay_base: Base delay in seconds for exponential backoff.

    Returns:
        True when a direct call has used up its retries and should re-raise.
    """
    wait = min(delay_base * (2 ** min(attempt, 16)), 60.0)
    limiter.cooldown(wait)
    if context is not None:
        context.notify(wait)
        logger.warning("s2_rate_limited attempt=%d waiting_s=%.1f", attempt + 1, wait)
        return False
    if attempt == retries:
        return True
    logger.warning(
        "s2_rate_limited attempt=%d max_attempts=%d waiting_s=%.1f",
        attempt + 1,
        retries + 1,
        wait,
    )
    return False


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
