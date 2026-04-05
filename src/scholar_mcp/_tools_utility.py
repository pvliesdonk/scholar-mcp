"""Utility MCP tools: batch_resolve and enrich_paper."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._rate_limiter import RateLimitedError
from ._s2_client import FIELD_SETS
from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)


def register_utility_tools(mcp: FastMCP) -> None:
    """Register utility tools on *mcp*.

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
    async def batch_resolve(
        identifiers: list[str],
        fields: Literal["compact", "standard", "full"] = "standard",
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Resolve a list of paper identifiers to full records.

        Uses the S2 batch endpoint for IDs/DOIs. Falls back to OpenAlex by DOI
        for papers that S2 cannot resolve.

        Args:
            identifiers: List of S2 IDs, DOIs (prefixed ``DOI:``), or plain DOIs.
            fields: Field set preset.

        Returns:
            JSON list of ``{"identifier": ..., "paper": {...}}`` for resolved,
            ``{"identifier": ..., "error": "not_found"}`` for unresolved,
            ``{"identifier": ..., "paper": {...}, "source": "openalex"}`` for
            OpenAlex fallbacks.
        """
        batch_ids: list[str] = []
        doi_map: dict[int, str] = {}  # index -> raw DOI for OA fallback

        for i, raw in enumerate(identifiers):
            batch_ids.append(raw)
            if raw.startswith("DOI:"):
                doi_map[i] = raw[4:]

        async def _execute(*, retry: bool = True) -> str:
            try:
                s2_results = await bundle.s2.batch_resolve(
                    batch_ids, fields=FIELD_SETS[fields], retry=retry
                )
            except httpx.HTTPStatusError as exc:
                return json.dumps(
                    {"error": "upstream_error", "status": exc.response.status_code}
                )

            async def _resolve_one(
                i: int, raw: str, s2_data: dict[str, Any] | None
            ) -> dict[str, Any]:
                if s2_data is not None:
                    return {"identifier": raw, "paper": s2_data}
                if i in doi_map:
                    oa = await bundle.openalex.get_by_doi(doi_map[i])
                    if oa:
                        return {
                            "identifier": raw,
                            "paper": oa,
                            "source": "openalex",
                        }
                return {"identifier": raw, "error": "not_found"}

            results = await asyncio.gather(
                *[
                    _resolve_one(i, raw, s2_data)
                    for i, (raw, s2_data) in enumerate(
                        zip(identifiers, s2_results, strict=True)
                    )
                ]
            )
            return json.dumps(list(results))

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(
                _execute(retry=True), tool="batch_resolve"
            )
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "batch_resolve"}
            )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def enrich_paper(
        identifier: str,
        fields: list[Literal["affiliations", "funders", "oa_status", "concepts"]],
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Fetch OpenAlex metadata to supplement Semantic Scholar data.

        Resolves the paper's DOI from S2, then queries OpenAlex for the
        requested enrichment fields. Results are cached for 30 days.

        Args:
            identifier: S2 paper ID or DOI (prefix ``DOI:``).
            fields: One or more of: affiliations, funders, oa_status, concepts.

        Returns:
            JSON dict with requested fields plus ``doi``, or an error dict.
        """

        async def _execute(*, retry: bool = True) -> str:
            doi: str | None = None
            if identifier.startswith("DOI:"):
                doi = identifier[4:]
            else:
                try:
                    paper = await bundle.s2.get_paper(
                        identifier, fields="externalIds,paperId", retry=retry
                    )
                    doi = (paper.get("externalIds") or {}).get("DOI")
                except httpx.HTTPStatusError:
                    return json.dumps({"error": "not_found", "identifier": identifier})

            if not doi:
                return json.dumps({"error": "no_doi", "identifier": identifier})

            cached = await bundle.cache.get_openalex(doi)
            oa_data = cached
            if oa_data is None:
                oa_data = await bundle.openalex.get_by_doi(doi)
                if oa_data is None:
                    return json.dumps({"error": "not_found_in_openalex", "doi": doi})
                await bundle.cache.set_openalex(doi, oa_data)

            result: dict[str, Any] = {"doi": doi}

            if "affiliations" in fields:
                result["affiliations"] = [
                    inst["display_name"]
                    for authorship in oa_data.get("authorships", [])
                    for inst in authorship.get("institutions", [])
                ]

            if "funders" in fields:
                result["funders"] = [
                    g.get("funder_display_name") for g in oa_data.get("grants", [])
                ]

            if "oa_status" in fields:
                oa_info = oa_data.get("open_access", {})
                result["oa_status"] = oa_info.get("oa_status")
                result["is_oa"] = oa_info.get("is_oa")

            if "concepts" in fields:
                result["concepts"] = [
                    {"name": c.get("display_name"), "score": c.get("score")}
                    for c in oa_data.get("concepts", [])
                ]

            return json.dumps(result)

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(
                _execute(retry=True), tool="enrich_paper"
            )
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "enrich_paper"}
            )
