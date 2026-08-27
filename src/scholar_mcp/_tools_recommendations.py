"""Recommendations MCP tool."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import JOB_RETRY_AFTER_S

from ._rate_limiter import RateLimitedError
from ._s2_client import FIELD_SETS, format_s2_error
from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)


def register_recommendation_tools(mcp: FastMCP) -> None:
    """Register recommendation tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool(
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
    ) -> Any:
        """Recommend papers based on positive (and optionally negative) examples.

        Args:
            positive_ids: 1-5 S2 paper IDs to use as positive examples.
            negative_ids: Optional S2 paper IDs to steer away from.
            limit: Number of recommendations to return.
            fields: Field set preset for returned records.

        Returns:
            JSON list of recommended paper records, or an error dict.
        """
        if not positive_ids:
            return json.dumps(
                {
                    "error": "validation_error",
                    "detail": "positive_ids must contain at least 1 ID",
                }
            )

        async def _execute(*, retry: bool = True) -> Any:
            try:
                result = await bundle.s2.recommend(
                    positive_ids[:5],
                    negative_ids=negative_ids,
                    limit=limit,
                    fields=FIELD_SETS[fields],
                    retry=retry,
                )
            except httpx.HTTPStatusError as exc:
                return json.loads(format_s2_error(exc))
            return result

        try:
            return json.dumps(await _execute(retry=False))
        except RateLimitedError as exc:
            logger.debug("rate_limited_deferred tool=%s", "recommend_papers")
            return await bundle.jobs.defer(
                _execute(retry=True),
                tool="recommend_papers",
                reason="Semantic Scholar asked this client to retry later.",
                retry_after_s=exc.retry_after_s or JOB_RETRY_AFTER_S,
            )
