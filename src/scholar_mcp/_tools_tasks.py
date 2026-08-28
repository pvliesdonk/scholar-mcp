"""Task polling MCP tools for async operations."""

from __future__ import annotations

import json
import logging

from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)


def register_task_tools(mcp: FastMCP) -> None:
    """Register task polling tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
    )
    async def get_task_result(
        task_id: str,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Poll for the result of a background task.

        When a tool returns ``{"queued": true, "task_id": "..."}`` it means
        the operation was submitted for background processing.  Call this
        tool with the ``task_id`` to check whether it has completed.

        Keep polling — the response includes ``elapsed_seconds`` while the
        task is in progress.

        This tool polls the tools that have not yet moved to the jobs
        framework. Tools that answer with a ``job_id`` and
        ``"poll_with": "get_job_result"`` are polled with that tool
        instead; the handle always names the one to use.

        Args:
            task_id: The task ID returned by a queued operation.

        Returns:
            JSON with ``status`` (``pending``, ``running``, ``completed``,
            or ``failed``).  When ``completed``, ``result`` contains the
            original tool output.  When ``failed``, ``error`` describes
            the failure.  While in progress, ``elapsed_seconds`` and
            ``tool`` give context on how long it has been running.
        """
        task = bundle.tasks.get(task_id)
        if task is None:
            return json.dumps({"error": "task_not_found", "task_id": task_id})
        response: dict[str, object] = {
            "task_id": task.task_id,
            "status": task.status,
        }
        if task.status == "completed":
            response["result"] = task.result
        elif task.status == "failed":
            error = task.error or ""
            if "daily quota" in error:
                response["error"] = (
                    "The service has reached its daily quota. Try again tomorrow."
                )
                response["retryable"] = False
            elif "EPO rate limited" in error:
                response["error"] = (
                    "The service was busy and could not complete the request. "
                    "Try calling the tool again in about 60 seconds."
                )
                response["retryable"] = True
            else:
                response["error"] = error
        else:
            # Task still in progress — give the client context
            response["elapsed_seconds"] = task.elapsed_seconds
            if task.tool:
                response["tool"] = task.tool
        return json.dumps(response)

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
    )
    async def list_tasks(
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """List active tasks on the legacy queue.

        This does not cover background *jobs*. Tools that answer with a
        ``job_id`` are polled with ``get_job_result``, and their work never
        appears here, so an absent operation is not a lost one.

        Returns:
            JSON list of ``{"task_id": ..., "status": ...}`` dicts.
        """
        tasks = bundle.tasks.list_active()
        return json.dumps(
            [
                {
                    "task_id": t.task_id,
                    "status": t.status,
                    "tool": t.tool,
                    "elapsed_seconds": t.elapsed_seconds,
                }
                for t in tasks
            ]
        )
