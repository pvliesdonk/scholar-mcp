"""Tests for the per-phase test timeout (#512)."""

from __future__ import annotations

import asyncio
import signal
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from tests.fixtures.phase_timeout import (
    PHASE_TIMEOUT_S,
    can_time_out,
    phase_timeout,
    timeout_applies,
)

pytestmark = pytest.mark.skipif(
    not can_time_out(), reason="SIGALRM is not available on this platform"
)


def test_a_stuck_block_fails_with_a_traceback() -> None:
    with (
        pytest.raises(pytest.fail.Exception, match=r"exceeded 0\.2 s"),
        phase_timeout(0.2, backstop_grace=30),
    ):
        time.sleep(5)


def test_a_stuck_event_loop_fails_too() -> None:
    """A coroutine waiting forever is interrupted out of the loop's select."""
    with (
        pytest.raises(pytest.fail.Exception, match="exceeded"),
        phase_timeout(0.2, backstop_grace=30),
    ):
        asyncio.run(asyncio.sleep(5))


def test_a_block_that_finishes_leaves_no_timer_of_its_own() -> None:
    before = signal.getsignal(signal.SIGALRM)
    with phase_timeout(5, backstop_grace=30):
        pass
    assert signal.getsignal(signal.SIGALRM) is before


def test_a_nested_block_hands_the_outer_limit_back() -> None:
    """The phase timer running this test survives a nested use."""
    remaining_before = signal.getitimer(signal.ITIMER_REAL)[0]
    assert remaining_before > 0
    with phase_timeout(5, backstop_grace=30):
        pass
    remaining_after = signal.getitimer(signal.ITIMER_REAL)[0]
    assert 0 < remaining_after <= remaining_before


def test_off_the_main_thread_the_block_runs_untimed() -> None:
    """A worker thread cannot install a signal handler, so it is left alone."""
    seen: list[object] = []

    def worker() -> None:
        with phase_timeout(0.01, backstop_grace=30):
            time.sleep(0.05)
            seen.append(signal.getsignal(signal.SIGALRM))

    handler = signal.getsignal(signal.SIGALRM)
    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert seen == [handler]


def test_every_phase_runs_under_the_timer(phase_timer_at_setup: float) -> None:
    """The conftest hooks arm the timer for setup and call alike."""
    assert 0 < phase_timer_at_setup <= PHASE_TIMEOUT_S
    assert 0 < signal.getitimer(signal.ITIMER_REAL)[0] <= PHASE_TIMEOUT_S


@pytest.fixture
def phase_timer_at_setup() -> float:
    """Report the timer's remaining time while this fixture is set up."""
    return signal.getitimer(signal.ITIMER_REAL)[0]


def _item(*, live: bool = False, usepdb: bool = False, trace: bool = False) -> Any:
    options = {"usepdb": usepdb, "trace": trace}
    return SimpleNamespace(
        get_closest_marker=lambda name: object() if live and name == "live" else None,
        config=SimpleNamespace(getoption=lambda name, _default=None: options[name]),
    )


@pytest.mark.parametrize(
    ("kwargs", "applies"),
    [
        ({}, True),
        ({"live": True}, False),
        ({"usepdb": True}, False),
        ({"trace": True}, False),
    ],
    ids=["plain", "live", "pdb", "trace"],
)
def test_timeout_skips_live_tests_and_debugger_sessions(
    kwargs: dict[str, bool], applies: bool
) -> None:
    assert timeout_applies(_item(**kwargs)) is applies
