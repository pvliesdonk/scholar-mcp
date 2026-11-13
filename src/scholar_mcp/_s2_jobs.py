"""Job registration for tool bodies that can wait on Semantic Scholar."""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import TYPE_CHECKING, Any, cast

from fastmcp.exceptions import ToolError
from fastmcp.utilities.tasks import TaskConfig
from fastmcp_pvl_core import JobLimitExceededError, JobsConfig, tool_boundary
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

# Share of the job record's TTL a throttled body may spend retrying, so its
# answer is recorded before the record expires.
_RETRY_SHARE_OF_TTL = 5 / 6


def _retry_window_s(config: JobsConfig) -> float:
    """Return how long a throttled S2 body keeps retrying, in seconds."""
    return config.result_ttl_s * _RETRY_SHARE_OF_TTL


def throttle_reason(config: JobsConfig) -> str:
    """Return the deferral text a caller reads when S2 throttles a tool.

    It tells the caller that the work goes on, how long it may take, that
    every client of this server shares one Semantic Scholar budget, and that
    an unfinished job is no answer, not an empty one.

    Args:
        config: The job settings, which bound the retry window.

    Returns:
        The client-visible reason for the deferral.
    """
    minutes = max(1, round(_retry_window_s(config) / 60))
    bound = "1 minute" if minutes == 1 else f"{minutes} minutes"
    return (
        "Semantic Scholar is throttling requests; the work continues in this "
        "job. Keep polling get_job_result: under throttling the result can "
        f"take up to about {bound}. Every client of this server "
        "shares one Semantic Scholar rate budget, so parallel calls slow each "
        "other down rather than finish sooner. Until the job completes, its "
        "outcome is unknown, not empty."
    )


def _job_cap_error(tool: str) -> ToolError:
    """Return the error a caller reads when it is at its background-job cap.

    The body could not get a job record, so it was stopped. Job records count
    toward the cap until they expire, so the caller's only way out is to wait.
    Mirrors the error pvl-core's ``register_long_running_tool`` raises for the
    same cap (#617).

    Args:
        tool: The registered tool name.

    Returns:
        An INFO-level ``ToolError``: the caller acts on it, not an operator.
    """
    return ToolError(
        f"{tool} could not finish in the foreground, because Semantic Scholar "
        "is throttling requests or the call ran past its time limit, and this "
        "caller already has the maximum number of background jobs, so it was "
        "stopped. Retry it later, once older jobs have expired.",
        log_level=logging.INFO,
    )


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
    context = S2RetryContext(deadline=loop.time() + _retry_window_s(config))
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
            # pvl-core types both verbs `Any`: inside a native task they return
            # the work's own result. That path returned above, so here they
            # always return the JobHandle mapping (pvl-core#324).
            if signal in done:
                handle = await jobs.defer(
                    continuation,
                    tool=tool,
                    reason=throttle_reason(config),
                    retry_after_s=context.retry_after_s,
                )
            else:
                handle = await jobs.start(continuation, tool=tool)
            return cast("dict[str, Any]", handle)
        except Exception as exc:
            continuation.close()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            if isinstance(exc, JobLimitExceededError):
                raise _job_cap_error(tool) from None
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

        return mcp.tool(task=TaskConfig(mode="optional"), **tool_kwargs)(
            tool_boundary(wrapper)
        )

    return decorator
