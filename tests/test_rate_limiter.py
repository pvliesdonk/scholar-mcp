import asyncio
import pytest
import httpx
from scholar_mcp._rate_limiter import RateLimiter, with_s2_retry

async def test_delay_between_requests():
    limiter = RateLimiter(delay=0.05)
    t0 = asyncio.get_event_loop().time()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = asyncio.get_event_loop().time() - t0
    assert elapsed >= 0.04  # at least one delay cycle

async def test_retry_on_429(respx_mock):
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
