"""Citation generation MCP tool."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import Jobs, register_long_running_tool

from ._citation_formatter import format_bibtex, format_csl_json, format_ris
from ._s2_client import FIELD_SETS, s2_error_payload
from ._server_deps import ServiceBundle, get_bundle

if TYPE_CHECKING:
    from ._record_types import PaperRecord

logger = logging.getLogger(__name__)

_FORMATTERS = {
    "bibtex": format_bibtex,
    "csl-json": format_csl_json,
    "ris": format_ris,
}


def _render(
    citation_format: str,
    papers: list[PaperRecord],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Render resolved papers in the requested citation format.

    Args:
        citation_format: One of ``bibtex``, ``csl-json``, ``ris``.
        papers: The papers that resolved.
        errors: The identifiers that did not, reported alongside.

    Returns:
        ``{"format": ..., "citations": ..., "errors": [...]}``. CSL-JSON is
        already structured, so its citations are an array rather than text a
        caller would have to parse out of JSON.
    """
    rendered = _FORMATTERS[citation_format](papers, errors)
    if citation_format == "csl-json":
        return {"format": citation_format, **json.loads(rendered)}
    return {"format": citation_format, "citations": rendered, "errors": errors}


def register_citation_tools(mcp: FastMCP, jobs: Jobs) -> None:
    """Register citation generation tools on *mcp*.

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
    async def generate_citations(
        paper_ids: list[str],
        citation_format: Literal["bibtex", "csl-json", "ris"] = "bibtex",
        enrich: bool = True,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> dict[str, Any]:
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
            ``{"format": ..., "citations": ..., "errors": [...]}``. For
            ``bibtex`` and ``ris``, ``citations`` is the rendered text; for
            ``csl-json`` it is an array of CSL-JSON objects.

            If the call outruns the jobs soft deadline it returns a job
            handle instead — poll ``get_job_result`` with its ``job_id``.
        """
        if not paper_ids:
            return {"error": "paper_ids must not be empty"}

        if len(paper_ids) > 100:
            return {"error": "paper_ids must contain at most 100 identifiers"}

        async def _execute() -> dict[str, Any]:
            try:
                # batch_resolve does not pre-screen the cache (consistent
                # with the batch_resolve tool in _tools_utility.py).
                s2_results = await bundle.s2.batch_resolve(
                    paper_ids, fields=FIELD_SETS["full"]
                )
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
                await bundle.enrichment.enrich(
                    papers, bundle, tags=frozenset({"papers"})
                )

            if not papers:
                return {
                    "error": "no_papers_resolved",
                    "failed": [e["identifier"] for e in errors],
                }

            return _render(citation_format, papers, errors)

        return await _execute()
