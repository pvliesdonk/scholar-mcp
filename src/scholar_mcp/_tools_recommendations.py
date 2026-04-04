"""Recommendations MCP tool."""

from __future__ import annotations

import json
import logging
from typing import Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._s2_client import FIELD_SETS
from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)


def register_recommendation_tools(mcp: FastMCP) -> None:
    """Register recommendation tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool()
    async def recommend_papers(
        positive_ids: list[str],
        negative_ids: list[str] | None = None,
        limit: int = 10,
        fields: Literal["compact", "standard", "full"] = "standard",
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Recommend papers based on positive (and optionally negative) examples.

        Args:
            positive_ids: 1–5 S2 paper IDs to use as positive examples.
            negative_ids: Optional S2 paper IDs to steer away from.
            limit: Number of recommendations to return.
            fields: Field set preset for returned records.

        Returns:
            JSON list of recommended paper records, or an error dict.
        """
        if not positive_ids:
            return json.dumps({"error": "validation_error", "detail": "positive_ids must contain at least 1 ID"})
        try:
            result = await bundle.s2.recommend(
                positive_ids[:5],
                negative_ids=negative_ids,
                limit=limit,
                fields=FIELD_SETS[fields],
            )
        except httpx.HTTPStatusError as exc:
            return json.dumps(
                {
                    "error": "upstream_error",
                    "status": exc.response.status_code,
                    "detail": exc.response.text[:200],
                }
            )
        return json.dumps(result)
