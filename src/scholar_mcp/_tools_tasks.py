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

        Args:
            task_id: The task ID returned by a queued operation.

        Returns:
            JSON with ``status`` (``pending``, ``running``, ``completed``,
            or ``failed``).  When ``completed``, ``result`` contains the
            original tool output.  When ``failed``, ``error`` describes
            the failure.
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
            response["error"] = task.error
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
            [{"task_id": t.task_id, "status": t.status} for t in tasks]
        )
