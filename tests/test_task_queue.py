"""Tests for the in-memory task queue."""

from __future__ import annotations

import asyncio

from scholar_mcp._task_queue import TaskQueue


async def test_submit_and_poll() -> None:
    """Submitted coroutine runs in background and result is pollable."""
    queue = TaskQueue()

    async def _work() -> str:
        return '{"ok": true}'

    task_id = queue.submit(_work())
    assert len(task_id) == 12

    # Let the background task run
    await asyncio.sleep(0.05)

    task = queue.get(task_id)
    assert task is not None
    assert task.status == "completed"
    assert task.result == '{"ok": true}'


async def test_failed_task() -> None:
    """Task that raises is marked failed with error message."""
    queue = TaskQueue()

    async def _fail() -> str:
        raise ValueError("boom")

    task_id = queue.submit(_fail())
    await asyncio.sleep(0.05)

    task = queue.get(task_id)
    assert task is not None
    assert task.status == "failed"
    assert task.error == "ValueError: boom"


async def test_ttl_expiry() -> None:
    """Expired tasks are cleaned up on next get()."""
    queue = TaskQueue(default_ttl=0.1)

    async def _work() -> str:
        return '{"done": true}'

    task_id = queue.submit(_work())
    await asyncio.sleep(0.05)
    assert queue.get(task_id) is not None

    # Wait for TTL expiry
    await asyncio.sleep(0.15)
    assert queue.get(task_id) is None


async def test_custom_ttl() -> None:
    """Per-task TTL overrides default."""
    queue = TaskQueue(default_ttl=0.1)

    async def _work() -> str:
        return '{"ok": true}'

    task_id = queue.submit(_work(), ttl=10.0)
    await asyncio.sleep(0.05)

    task = queue.get(task_id)
    assert task is not None
    assert task.ttl == 10.0


async def test_unknown_task() -> None:
    """Unknown task_id returns None."""
    queue = TaskQueue()
    assert queue.get("nonexistent") is None


async def test_list_active() -> None:
    """list_active returns all non-expired tasks."""
    queue = TaskQueue()

    async def _work() -> str:
        return '{"ok": true}'

    queue.submit(_work())
    queue.submit(_work())
    await asyncio.sleep(0.05)

    active = queue.list_active()
    assert len(active) == 2
    assert all(t.status == "completed" for t in active)


async def test_pending_then_running_then_completed() -> None:
    """Task transitions through pending -> running -> completed."""
    queue = TaskQueue()
    started = asyncio.Event()
    proceed = asyncio.Event()

    async def _controlled() -> str:
        started.set()
        await proceed.wait()
        return '{"done": true}'

    task_id = queue.submit(_controlled())

    # Task should be pending/running before started fires
    await started.wait()
    task = queue.get(task_id)
    assert task is not None
    assert task.status == "running"

    # Complete the task
    proceed.set()
    await asyncio.sleep(0.05)

    task = queue.get(task_id)
    assert task is not None
    assert task.status == "completed"
