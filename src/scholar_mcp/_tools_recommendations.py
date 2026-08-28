"""Recommendations MCP tool."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import register_long_running_tool

from ._s2_client import FIELD_SETS, s2_error_payload
from ._server_deps import ServiceBundle, get_bundle

if TYPE_CHECKING:
    from fastmcp_pvl_core import Jobs

logger = logging.getLogger(__name__)


async def recommend_papers(
    positive_ids: list[str],
    negative_ids: list[str] | None = None,
    limit: int = 10,
    fields: Literal["compact", "standard", "full"] = "standard",
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Recommend papers based on positive (and optionally negative) examples.

    Answers directly in normal use. Should the call run long it continues in
    the background and returns a job handle to poll with ``get_job_result``.

    Args:
        positive_ids: 1-5 S2 paper IDs to use as positive examples.
        negative_ids: Optional S2 paper IDs to steer away from.
        limit: Number of recommendations to return.
        fields: Field set preset for returned records.
        bundle: Injected service bundle.

    Returns:
        ``{"recommendations": [...]}``, or an error mapping.
    """
    if not positive_ids:
        return {
            "error": "validation_error",
            "detail": "positive_ids must contain at least 1 ID",
        }

    try:
        recommendations = await bundle.s2.recommend(
            positive_ids[:5],
            negative_ids=negative_ids,
            limit=limit,
            fields=FIELD_SETS[fields],
        )
    except httpx.HTTPStatusError as exc:
        return s2_error_payload(exc)
    return {"recommendations": recommendations}


def register_recommendation_tools(mcp: FastMCP, jobs: Jobs) -> None:
    """Register recommendation tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared jobs mechanics; a rate-limited call is retried and so
            runs long enough to be promoted rather than failing.
    """
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Recommend Papers",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(recommend_papers)
