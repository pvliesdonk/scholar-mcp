"""Job registration for tool bodies that can wait on Semantic Scholar."""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Any

from fastmcp.utilities.tasks import TaskConfig
from fastmcp_pvl_core import JobsConfig
from fastmcp_tasks.context import get_task_context

from ._rate_limiter import (
    S2_RETRY_CONTEXT,
    S2RetryContext,
    S2RetryDeadlineExceeded,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from fastmcp import FastMCP
    from fastmcp_pvl_core import Jobs

_S2_THROTTLE_REASON = "Semantic Scholar is throttling requests; work continues."


async def _await_task(task: asyncio.Task[dict[str, Any]]) -> dict[str, Any]:
    """Keep the original tool body attached to a job record."""
    return await task


async def _body(
    coro: Coroutine[Any, Any, dict[str, Any]], context: S2RetryContext
) -> dict[str, Any]:
    token = S2_RETRY_CONTEXT.set(context)
    try:
        try:
            return await coro
        except S2RetryDeadlineExceeded:
            return {"error": "rate_limited", "retryable": True}
    finally:
        S2_RETRY_CONTEXT.reset(token)


async def _run_s2_body(
    coro: Coroutine[Any, Any, dict[str, Any]],
    *,
    jobs: Jobs,
    config: JobsConfig,
    tool: str,
) -> dict[str, Any]:
    """Return an answer, or attach the same running body to a job."""
    loop = asyncio.get_running_loop()
    # Keep the retry window inside the record's TTL, including the inline
    # period before a job is created. At the default TTL this is 50 minutes.
    context = S2RetryContext(deadline=loop.time() + config.result_ttl_s * 5 / 6)
    if get_task_context() is not None:
        # The negotiated task already has a client-visible handle and owns
        # its lifecycle. A fallback Jobs handle here would be nested inside
        # that native task's result (pvl-core#324).
        return await _body(coro, context)
    task = asyncio.create_task(_body(coro, context))
    signal = asyncio.create_task(context.throttled.wait())
    try:
        done, _ = await asyncio.wait(
            {task, signal},
            timeout=config.soft_deadline_s,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if task in done:
            return task.result()
        continuation = _await_task(task)
        try:
            if signal in done:
                return dict(
                    await jobs.defer(
                        continuation,
                        tool=tool,
                        reason=_S2_THROTTLE_REASON,
                        retry_after_s=context.retry_after_s,
                    )
                )
            return dict(await jobs.start(continuation, tool=tool))
        except Exception:
            continuation.close()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
    except asyncio.CancelledError:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise
    finally:
        signal.cancel()
        await asyncio.gather(signal, return_exceptions=True)


def register_s2_tool(
    mcp: FastMCP,
    jobs: Jobs,
    *,
    jobs_config: JobsConfig | None = None,
    **tool_kwargs: Any,
) -> Callable[[Callable[..., Coroutine[Any, Any, dict[str, Any]]]], Any]:
    """Register a dual-mode tool that defers immediately on S2 throttling.

    Args:
        mcp: Server that exposes the tool.
        jobs: Shared job manager.
        jobs_config: The same settings used to construct ``jobs``. Defaults
            to the standard job settings for direct registrations.
        **tool_kwargs: FastMCP tool metadata.

    Returns:
        Decorator preserving the tool's signature and description.
    """
    config = jobs_config or JobsConfig()

    def decorator(fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]]) -> Any:
        tool_name = tool_kwargs.get("name") or fn.__name__

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return await _run_s2_body(
                fn(*args, **kwargs), jobs=jobs, config=config, tool=tool_name
            )

        return mcp.tool(task=TaskConfig(mode="optional"), **tool_kwargs)(wrapper)

    return decorator
