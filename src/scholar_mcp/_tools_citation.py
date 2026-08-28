"""Citation generation MCP tool."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import register_long_running_tool

from ._citation_formatter import format_bibtex, format_csl_json, format_ris
from ._s2_client import FIELD_SETS, s2_error_payload
from ._server_deps import ServiceBundle, get_bundle

if TYPE_CHECKING:
    from fastmcp_pvl_core import Jobs

    from ._record_types import PaperRecord

logger = logging.getLogger(__name__)

_FORMATTERS = {
    "bibtex": format_bibtex,
    "csl-json": format_csl_json,
    "ris": format_ris,
}


async def generate_citations(
    paper_ids: list[str],
    citation_format: Literal["bibtex", "csl-json", "ris"] = "bibtex",
    enrich: bool = True,
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Generate formatted citations for one or more papers.

    Resolves papers via Semantic Scholar, optionally enriches with
    OpenAlex metadata, and formats as BibTeX, CSL-JSON, or RIS.

    Enrichment fans out per paper, so a large batch can take a while; such a
    call answers with a job handle to poll using ``get_job_result`` instead
    of the citations themselves.

    Args:
        paper_ids: List of paper identifiers (S2 IDs, DOIs, arXiv IDs,
            etc.). Maximum 100.
        citation_format: Output format — bibtex, csl-json, or ris.
        enrich: If True, attempt OpenAlex enrichment for missing venue
            data when a DOI is available.
        bundle: Injected service bundle.

    Returns:
        ``{"format": ..., "output": ...}`` where ``output`` is the formatted
        text, with unresolved identifiers included as comments in the
        formatter's own style. An error mapping on failure.

        The key is ``output`` rather than ``citations`` because the CSL-JSON
        formatter emits its own ``citations`` key, which would collide.
    """
    if not paper_ids:
        return {"error": "paper_ids must not be empty"}

    if len(paper_ids) > 100:
        return {"error": "paper_ids must contain at most 100 identifiers"}

    try:
        # batch_resolve does not pre-screen the cache (consistent
        # with the batch_resolve tool in _tools_utility.py).
        s2_results = await bundle.s2.batch_resolve(paper_ids, fields=FIELD_SETS["full"])
    except httpx.HTTPStatusError as exc:
        return s2_error_payload(exc)

    papers: list[PaperRecord] = []
    errors: list[dict[str, Any]] = []

    for raw_id, s2_data in zip(paper_ids, s2_results, strict=True):
        if s2_data is not None:
            papers.append(s2_data)
        else:
            errors.append({"identifier": raw_id, "reason": "not found"})

    if enrich:
        await bundle.enrichment.enrich(papers, bundle, tags=frozenset({"papers"}))

    if not papers:
        return {
            "error": "no_papers_resolved",
            "failed": [e["identifier"] for e in errors],
        }

    formatter = _FORMATTERS[citation_format]
    return {"format": citation_format, "output": formatter(papers, errors)}


def register_citation_tools(mcp: FastMCP, jobs: Jobs) -> None:
    """Register citation generation tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared jobs mechanics; enrichment over a large batch can
            outrun the soft deadline and is then promoted.
    """
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Generate Citations",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(generate_citations)
