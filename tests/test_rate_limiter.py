import asyncio

import httpx
import pytest

from scholar_mcp._rate_limiter import (
    RateLimitedError,
    RateLimiter,
    with_s2_retry,
    with_s2_try_once,
)


async def test_delay_between_requests():
    limiter = RateLimiter(delay=0.05)
    t0 = asyncio.get_event_loop().time()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = asyncio.get_event_loop().time() - t0
    assert elapsed >= 0.04  # at least one delay cycle


async def test_retry_on_429(respx_mock):  # noqa: ARG001
    limiter = RateLimiter(delay=0.0)
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.HTTPStatusError(
                "rate limited",
                request=httpx.Request("GET", "http://x"),
                response=httpx.Response(429),
            )
        return "ok"

    result = await with_s2_retry(flaky, limiter, max_retries=3, base_delay=0.01)
    assert result == "ok"
    assert call_count == 3


async def test_retry_exhausted():
    limiter = RateLimiter(delay=0.0)

    async def always_429():
        raise httpx.HTTPStatusError(
            "rate limited",
            request=httpx.Request("GET", "http://x"),
            response=httpx.Response(429),
        )

    with pytest.raises(httpx.HTTPStatusError):
        await with_s2_retry(always_429, limiter, max_retries=2, base_delay=0.01)


async def test_exhausted_429_slows_the_next_caller() -> None:
    limiter = RateLimiter(delay=0.0)

    async def refused() -> None:
        raise httpx.HTTPStatusError(
            "rate limited",
            request=httpx.Request("GET", "http://x"),
            response=httpx.Response(429),
        )

    with pytest.raises(httpx.HTTPStatusError):
        await with_s2_retry(refused, limiter, max_retries=0, base_delay=0.04)

    started = asyncio.get_running_loop().time()
    await limiter.acquire()
    assert asyncio.get_running_loop().time() - started >= 0.03


async def test_try_once_429_slows_the_next_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scholar_mcp import _rate_limiter

    monkeypatch.setattr(_rate_limiter, "_S2_BASE_DELAY_S", 0.04)
    limiter = RateLimiter(delay=0.0)

    async def refused() -> None:
        raise httpx.HTTPStatusError(
            "rate limited",
            request=httpx.Request("GET", "http://x"),
            response=httpx.Response(429),
        )

    with pytest.raises(RateLimitedError):
        await with_s2_try_once(refused, limiter)

    started = asyncio.get_running_loop().time()
    await limiter.acquire()
    assert asyncio.get_running_loop().time() - started >= 0.03


async def test_shorter_cooldown_does_not_release_earlier() -> None:
    limiter = RateLimiter(delay=0.0)
    limiter.cooldown(0.04)
    limiter.cooldown(0.01)

    started = asyncio.get_running_loop().time()
    await limiter.acquire()
    assert asyncio.get_running_loop().time() - started >= 0.03


async def test_waiting_caller_rechecks_extended_cooldown() -> None:
    limiter = RateLimiter(delay=0.0)
    limiter.cooldown(0.1)
    started = asyncio.get_running_loop().time()
    waiting = asyncio.create_task(limiter.acquire())
    await asyncio.sleep(0)
    limiter.cooldown(0.15)
    await waiting
    assert asyncio.get_running_loop().time() - started >= 0.12
