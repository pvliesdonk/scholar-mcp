"""Recommendations MCP tool."""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import Jobs, register_long_running_tool

from ._s2_client import FIELD_SETS, s2_error_payload
from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)


def register_recommendation_tools(mcp: FastMCP, jobs: Jobs) -> None:
    """Register recommendation tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared Jobs service. A tool that can outrun a request is
            registered against it, so a call past the soft deadline is
            promoted to a background job instead of holding the request.
    """

    @register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def recommend_papers(
        positive_ids: list[str],
        negative_ids: list[str] | None = None,
        limit: int = 10,
        fields: Literal["compact", "standard", "full"] = "standard",
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> dict[str, Any]:
        """Recommend papers based on positive (and optionally negative) examples.

        Args:
            positive_ids: 1-5 S2 paper IDs to use as positive examples.
            negative_ids: Optional S2 paper IDs to steer away from.
            limit: Number of recommendations to return.
            fields: Field set preset for returned records.

        Returns:
            ``{"recommendations": [...]}``, or a structured error mapping.
        """
        if not positive_ids:
            return {
                "error": "validation_error",
                "detail": "positive_ids must contain at least 1 ID",
            }

        async def _execute() -> dict[str, Any]:
            try:
                result = await bundle.s2.recommend(
                    positive_ids[:5],
                    negative_ids=negative_ids,
                    limit=limit,
                    fields=FIELD_SETS[fields],
                )
            except httpx.HTTPStatusError as exc:
                return s2_error_payload(exc)
            return {"recommendations": result}

        return await _execute()
