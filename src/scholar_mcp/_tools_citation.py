"""Citation generation MCP tool."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._citation_formatter import format_bibtex, format_csl_json, format_ris
from ._rate_limiter import RateLimitedError
from ._s2_client import FIELD_SETS
from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)

_FORMATTERS = {
    "bibtex": format_bibtex,
    "csl-json": format_csl_json,
    "ris": format_ris,
}


async def _enrich_paper(paper: dict[str, Any], bundle: ServiceBundle) -> None:
    """Enrich paper in-place with OpenAlex venue data if missing.

    Args:
        paper: Paper metadata dict (mutated in-place).
        bundle: Service bundle for API access.
    """
    if paper.get("venue"):
        return
    doi = (paper.get("externalIds") or {}).get("DOI")
    if not doi:
        return
    try:
        cached = await bundle.cache.get_openalex(doi)
        oa_data = (
            cached if cached is not None else await bundle.openalex.get_by_doi(doi)
        )
        if oa_data is None:
            return
        if cached is None:
            await bundle.cache.set_openalex(doi, oa_data)
        loc = oa_data.get("primary_location") or {}
        source = loc.get("source") or {}
        venue = source.get("display_name")
        if venue:
            paper["venue"] = venue
    except Exception:
        logger.debug("openalex_enrich_failed doi=%s", doi, exc_info=True)


def register_citation_tools(mcp: FastMCP) -> None:
    """Register citation generation tools on *mcp*.

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
    async def generate_citations(
        paper_ids: list[str],
        citation_format: Literal["bibtex", "csl-json", "ris"] = "bibtex",
        enrich: bool = True,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Generate formatted citations for one or more papers.

        Resolves papers via Semantic Scholar, optionally enriches with
        OpenAlex metadata, and formats as BibTeX, CSL-JSON, or RIS.

        Args:
            paper_ids: List of paper identifiers (S2 IDs, DOIs, arXiv IDs,
                etc.). Maximum 100.
            citation_format: Output format — bibtex, csl-json, or ris.
            enrich: If True, attempt OpenAlex enrichment for missing venue
                data when a DOI is available.

        Returns:
            Formatted citation string, or a queued task response on rate
            limiting.
        """
        if not paper_ids:
            return json.dumps({"error": "paper_ids must not be empty"})

        if len(paper_ids) > 100:
            return json.dumps(
                {"error": "paper_ids must contain at most 100 identifiers"}
            )

        async def _execute(*, retry: bool = True) -> str:
            try:
                # batch_resolve does not pre-screen the cache (consistent
                # with the batch_resolve tool in _tools_utility.py).
                s2_results = await bundle.s2.batch_resolve(
                    paper_ids, fields=FIELD_SETS["full"], retry=retry
                )
            except httpx.HTTPStatusError as exc:
                return json.dumps(
                    {
                        "error": "upstream_error",
                        "status": exc.response.status_code,
                        "detail": exc.response.text[:200],
                    }
                )

            papers: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []

            for raw_id, s2_data in zip(paper_ids, s2_results, strict=True):
                if s2_data is not None:
                    papers.append(s2_data)
                else:
                    errors.append({"identifier": raw_id, "reason": "not found"})

            if enrich:
                sem = asyncio.Semaphore(10)

                async def _bounded_enrich(p: dict[str, Any]) -> None:
                    async with sem:
                        await _enrich_paper(p, bundle)

                await asyncio.gather(*(_bounded_enrich(p) for p in papers))

            if not papers:
                return json.dumps(
                    {
                        "error": "no_papers_resolved",
                        "failed": [e["identifier"] for e in errors],
                    }
                )

            formatter = _FORMATTERS[citation_format]
            return formatter(papers, errors)

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(
                _execute(retry=True), tool="generate_citations"
            )
            return json.dumps(
                {
                    "queued": True,
                    "task_id": task_id,
                    "tool": "generate_citations",
                }
            )
