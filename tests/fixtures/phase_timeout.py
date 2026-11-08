"""Fail a stuck test phase in bounded time, with a traceback (#512).

A test that waits on something that never answers would otherwise run until
the CI job's own timeout cancels it, which prints no stack and gives no hint
of which test hung. :func:`phase_timeout` arms ``SIGALRM`` so a phase that
overruns fails through ``pytest.fail`` with the stack where it was stuck, and
the run continues with the next test. A ``faulthandler`` backstop a little
later dumps every thread and exits the process, for a main thread blocked in
C code that the signal cannot interrupt.

``pytest-timeout`` does the same, but adding it would change the
template-owned dependency groups and pytest settings; this keeps the change
in project-owned files.
"""

from __future__ import annotations

import faulthandler
import signal
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from types import FrameType

import pytest

PHASE_TIMEOUT_S = 60.0
"""Longest a single setup, call or teardown phase may run.

The slowest phase in CI takes about one second, so this leaves wide headroom
while turning a hang into a failure after a minute instead of at the 20-minute
job timeout.
"""

BACKSTOP_GRACE_S = 30.0
"""Extra time before the faulthandler backstop exits the whole process."""


def can_time_out() -> bool:
    """Return whether this platform supports the ``SIGALRM`` timer.

    Returns:
        ``True`` on POSIX platforms with ``signal.setitimer``.
    """
    return hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")


@contextmanager
def phase_timeout(
    seconds: float, *, backstop_grace: float = BACKSTOP_GRACE_S
) -> Iterator[None]:
    """Fail the enclosed block if it runs longer than *seconds*.

    Does nothing on platforms without ``SIGALRM``, or off the main thread,
    where Python cannot install a signal handler.

    Args:
        seconds: Time limit for the block.
        backstop_grace: Extra time before the process-exiting backstop fires.

    Yields:
        Nothing; the block runs under the timer.
    """
    if not can_time_out() or not _on_main_thread():
        yield
        return

    def _expire(signum: int, frame: FrameType | None) -> None:  # noqa: ARG001
        pytest.fail(
            f"Test phase exceeded {seconds:g} s; see the traceback for where "
            "it was stuck (#512).",
            pytrace=True,
        )

    # Saving the handler and the remaining time of any timer already running
    # lets a nested use (a test of this helper, inside a timed phase) hand
    # the outer limit back when it ends instead of switching it off.
    previous_handler = signal.signal(signal.SIGALRM, _expire)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    faulthandler.dump_traceback_later(seconds + backstop_grace, exit=True)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        faulthandler.cancel_dump_traceback_later()
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)
            faulthandler.dump_traceback_later(
                previous_timer[0] + backstop_grace, exit=True
            )


def _on_main_thread() -> bool:
    """Return whether the caller runs on the main thread.

    Returns:
        ``True`` when signal handlers can be installed from here.
    """
    return threading.current_thread() is threading.main_thread()


def timeout_applies(item: pytest.Item) -> bool:
    """Return whether *item* runs under the phase timeout.

    Live tests wait on real services by design, and a debugger session would
    trip the timer while paused.

    Args:
        item: The test about to run.

    Returns:
        ``False`` for ``live`` tests and under ``--pdb`` or ``--trace``.
    """
    if item.get_closest_marker("live"):
        return False
    config = item.config
    if config.getoption("usepdb", False) or config.getoption("trace", False):
        return False
    return "pydevd" not in sys.modules
