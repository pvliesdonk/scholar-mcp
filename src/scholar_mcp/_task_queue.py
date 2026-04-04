"""In-memory task queue for background async operations."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 600.0  # 10 minutes


@dataclass
class TaskResult:
    """Status and result of a queued background task.

    Attributes:
        task_id: Unique identifier for the task.
        status: One of ``pending``, ``running``, ``completed``, ``failed``.
        result: JSON string result when completed.
        error: Error message when failed.
        created_at: Unix timestamp when the task was created.
        ttl: Time-to-live in seconds before auto-expiry.
    """

    task_id: str
    status: str  # "pending" | "running" | "completed" | "failed"
    result: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    ttl: float = _DEFAULT_TTL


class TaskQueue:
    """In-memory queue that runs coroutines in the background.

    Submitted coroutines execute as ``asyncio.Task``s.  Results are kept
    until their TTL expires.

    Args:
        default_ttl: Default time-to-live for task results in seconds.
    """

    def __init__(self, default_ttl: float = _DEFAULT_TTL) -> None:
        self._tasks: dict[str, TaskResult] = {}
        self._default_ttl = default_ttl

    def submit(
        self,
        coro: Coroutine[Any, Any, str],
        *,
        ttl: float | None = None,
    ) -> str:
        """Submit a coroutine for background execution.

        Args:
            coro: Async callable that returns a JSON string.
            ttl: Optional per-task TTL override.

        Returns:
            Unique task ID for polling via :meth:`get`.
        """
        task_id = uuid4().hex[:12]
        task = TaskResult(
            task_id=task_id,
            status="pending",
            ttl=ttl if ttl is not None else self._default_ttl,
        )
        self._tasks[task_id] = task
        bg = asyncio.create_task(self._run(task, coro))
        bg.add_done_callback(lambda _: None)  # prevent unhandled warnings
        logger.info("task_submitted task_id=%s", task_id)
        return task_id

    async def _run(self, task: TaskResult, coro: Coroutine[Any, Any, str]) -> None:
        task.status = "running"
        try:
            task.result = await coro
            task.status = "completed"
            logger.info("task_completed task_id=%s", task.task_id)
        except Exception:
            task.status = "failed"
            task.error = "internal_error"
            logger.exception("task_failed task_id=%s", task.task_id)

    def get(self, task_id: str) -> TaskResult | None:
        """Retrieve a task by ID, returning ``None`` if expired or unknown.

        Args:
            task_id: The task ID returned by :meth:`submit`.

        Returns:
            :class:`TaskResult` or ``None``.
        """
        self._cleanup()
        return self._tasks.get(task_id)

    def list_active(self) -> list[TaskResult]:
        """Return all non-expired tasks.

        Returns:
            List of active :class:`TaskResult` instances.
        """
        self._cleanup()
        return list(self._tasks.values())

    def _cleanup(self) -> None:
        now = time.time()
        expired = [
            k
            for k, v in self._tasks.items()
            if now - v.created_at > v.ttl
        ]
        for k in expired:
            del self._tasks[k]
