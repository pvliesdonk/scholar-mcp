"""Citation generation MCP tool."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import JOB_RETRY_AFTER_S

from ._citation_formatter import format_bibtex, format_csl_json, format_ris
from ._rate_limiter import RateLimitedError
from ._s2_client import FIELD_SETS, format_s2_error
from ._server_deps import ServiceBundle, get_bundle

if TYPE_CHECKING:
    from ._record_types import PaperRecord

logger = logging.getLogger(__name__)

_FORMATTERS = {
    "bibtex": format_bibtex,
    "csl-json": format_csl_json,
    "ris": format_ris,
}


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
    ) -> Any:
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
            Formatted citation string, or a working job handle on rate limiting.
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
                return format_s2_error(exc)

            papers: list[PaperRecord] = []
            errors: list[dict[str, Any]] = []

            for raw_id, s2_data in zip(paper_ids, s2_results, strict=True):
                if s2_data is not None:
                    papers.append(s2_data)
                else:
                    errors.append({"identifier": raw_id, "reason": "not found"})

            if enrich:
                await bundle.enrichment.enrich(
                    papers, bundle, tags=frozenset({"papers"})
                )

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
        except RateLimitedError as exc:
            logger.debug("rate_limited_deferred tool=%s", "generate_citations")
            return await bundle.jobs.defer(
                _execute(retry=True),
                tool="generate_citations",
                reason="Semantic Scholar asked this client to retry later.",
                retry_after_s=exc.retry_after_s or JOB_RETRY_AFTER_S,
            )
