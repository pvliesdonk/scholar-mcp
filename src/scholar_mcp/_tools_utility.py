"""Utility MCP tools: batch_resolve and enrich_paper."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._epo_client import EpoRateLimitedError
from ._patent_numbers import is_patent_number, normalize
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
        """Resolve a list of paper or patent identifiers to full records.

        Uses the S2 batch endpoint for paper IDs/DOIs, with OpenAlex fallback.
        Patent numbers (e.g. EP1234567A1) are auto-detected and resolved via
        the EPO OPS API when configured.

        Args:
            identifiers: List of S2 IDs, DOIs (prefixed ``DOI:``), plain DOIs,
                or patent numbers (e.g. ``EP1234567A1``, ``US11234567B2``).
            fields: Field set preset (applies to paper results only).

        Returns:
            JSON list of resolved items. Paper results have a ``paper`` key,
            patent results have a ``patent`` key and ``source_type: "patent"``.
            Unresolved items have an ``error`` key.
        """
        # Split identifiers into papers vs patents
        paper_indices: list[int] = []
        paper_ids: list[str] = []
        patent_indices: list[int] = []
        patent_raws: list[str] = []
        doi_map: dict[int, str] = {}  # original index -> raw DOI for OA fallback

        for i, raw in enumerate(identifiers):
            if is_patent_number(raw):
                patent_indices.append(i)
                patent_raws.append(raw)
            else:
                paper_indices.append(i)
                paper_ids.append(raw)
                if raw.startswith("DOI:"):
                    doi_map[i] = raw[4:]

        async def _execute(*, retry: bool = True) -> str:
            # Resolve papers via S2 (existing logic)
            s2_results: list[dict[str, Any] | None] = []
            if paper_ids:
                try:
                    s2_results = await bundle.s2.batch_resolve(
                        paper_ids, fields=FIELD_SETS[fields], retry=retry
                    )
                except httpx.HTTPStatusError as exc:
                    return json.dumps(
                        {
                            "error": "upstream_error",
                            "status": exc.response.status_code,
                        }
                    )

            async def _resolve_paper(
                idx: int, raw: str, s2_data: dict[str, Any] | None
            ) -> tuple[int, dict[str, Any]]:
                if s2_data is not None:
                    return idx, {"identifier": raw, "paper": s2_data}
                if idx in doi_map:
                    oa = await bundle.openalex.get_by_doi(doi_map[idx])
                    if oa:
                        return idx, {
                            "identifier": raw,
                            "paper": oa,
                            "source": "openalex",
                        }
                return idx, {"identifier": raw, "error": "not_found"}

            async def _resolve_patent(idx: int, raw: str) -> tuple[int, dict[str, Any]]:
                if bundle.epo is None:
                    return idx, {
                        "identifier": raw,
                        "error": "epo_not_configured",
                        "source_type": "patent",
                    }
                try:
                    doc = normalize(raw)
                    biblio = await bundle.epo.get_biblio(doc)
                    if not biblio.get("title") and not biblio.get("applicants"):
                        return idx, {
                            "identifier": raw,
                            "error": "not_found",
                            "source_type": "patent",
                        }
                    return idx, {
                        "identifier": raw,
                        "patent": biblio,
                        "source_type": "patent",
                    }
                except ValueError:
                    return idx, {
                        "identifier": raw,
                        "error": "invalid_patent_number",
                        "source_type": "patent",
                    }
                except (RateLimitedError, EpoRateLimitedError):
                    raise
                except Exception:
                    logger.warning("batch_patent_resolve_failed id=%s", raw)
                    return idx, {
                        "identifier": raw,
                        "error": "resolve_failed",
                        "source_type": "patent",
                    }

            # Resolve both groups concurrently
            paper_tasks = [
                _resolve_paper(paper_indices[j], paper_ids[j], s2_data)
                for j, s2_data in enumerate(s2_results)
            ]
            patent_tasks = [
                _resolve_patent(patent_indices[j], patent_raws[j])
                for j in range(len(patent_raws))
            ]

            all_resolved = await asyncio.gather(*paper_tasks, *patent_tasks)

            # Merge back in original order
            result_map: dict[int, dict[str, Any]] = dict(all_resolved)
            ordered = [result_map[i] for i in range(len(identifiers))]
            return json.dumps(ordered)

        try:
            return await _execute(retry=False)
        except (RateLimitedError, EpoRateLimitedError):
            task_id = bundle.tasks.submit(_execute(retry=True), tool="batch_resolve")
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
            task_id = bundle.tasks.submit(_execute(retry=True), tool="enrich_paper")
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "enrich_paper"}
            )
