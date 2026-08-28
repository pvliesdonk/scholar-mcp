"""Tests for `with_epo_retry`, the EPO analogue of `with_s2_retry`.

The reason this helper exists is timing: EPO's traffic light is consulted
before any network call, so a throttled request fails in milliseconds. Without
backoff there is nothing long-running for the jobs framework to promote, and
the caller gets an immediate error where they used to get a background retry.
"""

from __future__ import annotations

import asyncio

import pytest

from scholar_mcp import _epo_client
from scholar_mcp._epo_client import (
    EpoQuotaExhaustedError,
    EpoRateLimitedError,
    with_epo_retry,
)


async def test_returns_immediately_when_nothing_is_throttled() -> None:
    """The happy path costs no delay and one call."""
    calls = 0

    async def work() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    assert await with_epo_retry(work) == "ok"
    assert calls == 1


async def test_retries_until_the_light_clears() -> None:
    """A throttle that clears on the second attempt yields the real result."""
    calls = 0

    async def work() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise EpoRateLimitedError("yellow", service="search")
        return "cleared"

    assert await with_epo_retry(work, base_delay=0.001) == "cleared"
    assert calls == 2


async def test_reraises_once_retries_are_spent() -> None:
    """A throttle that never clears surfaces, rather than looping forever."""
    calls = 0

    async def work() -> str:
        nonlocal calls
        calls += 1
        raise EpoRateLimitedError("red", service="retrieval")

    with pytest.raises(EpoRateLimitedError):
        await with_epo_retry(work, max_retries=2, base_delay=0.001)
    assert calls == 3, "one initial attempt plus two retries"


async def test_quota_exhaustion_is_not_retried() -> None:
    """A spent daily quota fails at once: waiting cannot clear it today.

    Retrying would cost the caller the full backoff for an answer that is
    already known.
    """
    calls = 0

    async def work() -> str:
        nonlocal calls
        calls += 1
        raise EpoQuotaExhaustedError

    with pytest.raises(EpoQuotaExhaustedError):
        await with_epo_retry(work, base_delay=0.001)
    assert calls == 1


async def test_other_errors_propagate_untouched() -> None:
    """Only throttles are retried; a real failure is not masked by waiting."""
    calls = 0

    async def work() -> str:
        nonlocal calls
        calls += 1
        raise ValueError("no such patent")

    with pytest.raises(ValueError, match="no such patent"):
        await with_epo_retry(work, base_delay=0.001)
    assert calls == 1


async def test_backoff_doubles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Waits grow exponentially from the base delay."""
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def work() -> str:
        raise EpoRateLimitedError("red")

    with pytest.raises(EpoRateLimitedError):
        await with_epo_retry(work, max_retries=3, base_delay=10.0)
    assert slept == [10.0, 20.0, 40.0]


@pytest.mark.real_epo_backoff
def test_default_delay_outlasts_the_throttle_cache() -> None:
    """The default wait must exceed the cached traffic light's lifetime.

    A shorter wait is worse than useless: `_is_service_throttled` would still
    be holding the last-seen colour, so the retry would short-circuit without
    reaching EPO and fail exactly as the first attempt did. This asserts the
    relationship rather than the numbers, so tuning either constant cannot
    silently break it.
    """
    assert _epo_client._THROTTLE_RETRY_DELAY_S > _epo_client._THROTTLE_CACHE_TTL_S


async def test_defaults_are_read_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Patching the module constant changes the delay actually used.

    The whole suite relies on this to avoid sleeping for real minutes; if the
    defaults were bound at definition time the autouse fixture in conftest
    would silently stop working.
    """
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(_epo_client, "_THROTTLE_RETRY_DELAY_S", 7.0)
    monkeypatch.setattr(_epo_client, "_THROTTLE_MAX_RETRIES", 1)

    async def work() -> str:
        raise EpoRateLimitedError("red")

    with pytest.raises(EpoRateLimitedError):
        await with_epo_retry(work)
    assert slept == [7.0]
