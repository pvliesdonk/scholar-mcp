"""Task polling MCP tools for async operations."""

from __future__ import annotations

import json
import logging

from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)

# Expected duration hints per tool, shown while the task is in progress.
_DURATION_HINTS: dict[str, str] = {
    "fetch_paper_pdf": "PDF download usually completes in 10-30 seconds.",
    "convert_pdf_to_markdown": (
        "PDF conversion typically takes 1-5 minutes depending on page count."
    ),
    "fetch_and_convert": (
        "Full pipeline (download + conversion) typically takes 1-5 minutes."
    ),
    "search_patents": "Patent searches usually complete in 5-15 seconds.",
    "get_patent": "Patent data retrieval usually completes in 5-20 seconds.",
    "get_citing_patents": "Citing patent lookup usually completes in 10-30 seconds.",
}


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

        PDF conversion tasks typically take 1-5 minutes. Keep polling —
        the response includes ``elapsed_seconds`` and a ``hint`` with
        expected duration while the task is in progress.

        Args:
            task_id: The task ID returned by a queued operation.

        Returns:
            JSON with ``status`` (``pending``, ``running``, ``completed``,
            or ``failed``).  When ``completed``, ``result`` contains the
            original tool output.  When ``failed``, ``error`` describes
            the failure.  While in progress, ``elapsed_seconds``, ``tool``,
            and ``hint`` give context on expected wait time.
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
                hint = _DURATION_HINTS.get(task.tool)
                if hint:
                    response["hint"] = hint
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
        """List all active background tasks.

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
