"""Citation generation MCP tool."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._citation_formatter import format_bibtex, format_csl_json, format_ris
from ._patent_numbers import is_patent_number
from ._s2_client import FIELD_SETS, s2_error_payload
from ._s2_jobs import register_s2_tool
from ._server_deps import get_service
from ._tools_utility import _resolve_patent
from .domain import Service

if TYPE_CHECKING:
    from fastmcp_pvl_core import Jobs, JobsConfig

    from ._citation_formatter import CitationRecord
    from ._record_types import PaperRecord

logger = logging.getLogger(__name__)

_FORMATTERS = {
    "bibtex": format_bibtex,
    "csl-json": format_csl_json,
    "ris": format_ris,
}


# A Semantic Scholar paper id is 40 lower-case hex digits. Some begin with
# what ``is_patent_number`` reads as an office code and a digit (``ca1…``,
# ``de0…``), so they are kept away from EPO. Remove once #699 fixes
# ``is_patent_number`` itself.
_S2_PAPER_ID = re.compile(r"^[0-9a-f]{40}$")


def _is_patent_id(raw: str) -> bool:
    """Say whether an identifier is resolved as a patent number.

    Args:
        raw: One entry of ``paper_ids``.

    Returns:
        ``True`` for a patent number, ``False`` for a paper identifier.
    """
    return is_patent_number(raw) and not _S2_PAPER_ID.match(raw.strip())


async def _resolve_papers(
    paper_ids: list[str], enrich: bool, service: Service
) -> list[PaperRecord | None]:
    """Resolve paper identifiers through Semantic Scholar.

    Args:
        paper_ids: Paper identifiers; S2 is not called when this is empty.
        enrich: Whether to enrich the found papers with OpenAlex data, in place.
        service: Injected service.

    Returns:
        One record per identifier, ``None`` where S2 found nothing.

    Raises:
        httpx.HTTPStatusError: When S2 answers with an HTTP error.
    """
    if not paper_ids:
        return []
    # batch_resolve does not pre-screen the cache (consistent
    # with the batch_resolve tool in _tools_utility.py).
    #
    # publicationTypes is requested on top of the preset because entry-type
    # inference is the only consumer; widening FIELD_SETS["full"] would
    # change what get_paper and every fields="full" caller return.
    results: list[PaperRecord | None] = await service.s2.batch_resolve(
        paper_ids, fields=FIELD_SETS["full"] + ",publicationTypes"
    )
    found = [p for p in results if p is not None]
    if enrich and found:
        await service.enrichment.enrich(found, service, tags=frozenset({"papers"}))
    return results


async def _resolve_patents(
    indices: list[int], paper_ids: list[str], service: Service
) -> dict[int, dict[str, Any]]:
    """Resolve patent numbers through EPO, concurrently.

    Args:
        indices: Positions in *paper_ids* that hold patent numbers.
        paper_ids: The caller's identifiers.
        service: Injected service.

    Returns:
        Position to ``batch_resolve``-style entry, holding ``patent`` or
        ``error``.
    """
    resolved = await asyncio.gather(
        *(_resolve_patent(i, paper_ids[i], service) for i in indices)
    )
    return dict(resolved)


def _collect(
    paper_ids: list[str],
    papers: dict[int, PaperRecord | None],
    patents: dict[int, dict[str, Any]],
) -> tuple[list[CitationRecord], list[dict[str, Any]]]:
    """Put the resolved records and the failures back in input order.

    Args:
        paper_ids: The caller's identifiers.
        papers: Position to S2 record, ``None`` where S2 found nothing.
        patents: Position to EPO entry.

    Returns:
        ``(records, errors)``; each error has ``identifier`` and ``reason``.
    """
    records: list[CitationRecord] = []
    errors: list[dict[str, Any]] = []
    for idx, raw in enumerate(paper_ids):
        if idx in patents:
            entry = patents[idx]
            record: CitationRecord | None = entry.get("patent")
            reason = entry.get("error", "not_found")
        else:
            record, reason = papers.get(idx), "not found"
        if record is not None:
            records.append(record)
        else:
            errors.append({"identifier": raw, "reason": reason})
    return records, errors


async def generate_citations(
    paper_ids: list[str],
    citation_format: Literal["bibtex", "csl-json", "ris"] = "bibtex",
    enrich: bool = True,
    service: Service = Depends(get_service),
) -> dict[str, Any]:
    """Generate formatted citations for papers and patents.

    Papers are resolved through Semantic Scholar and can be enriched with
    OpenAlex metadata. Patent numbers such as ``EP1234567A1`` may be mixed
    into ``paper_ids``; they are resolved through EPO and come out as patent
    entries. Entries keep the order of ``paper_ids``. The output is BibTeX,
    CSL-JSON or RIS.

    Enrichment fans out per paper, so a large batch can take a while; such a
    call answers with a job handle to poll using ``get_job_result`` instead
    of the citations themselves.

    Args:
        paper_ids: Paper identifiers (S2 IDs, DOIs, arXiv IDs, etc.) and
            patent numbers (``EP1234567A1``, ``US11234567B2``), in the order
            the citations should appear. Maximum 100.
        citation_format: Output format: ``bibtex``, ``csl-json`` or ``ris``.
        enrich: If True, attempt OpenAlex enrichment for missing venue
            data when a DOI is available.
        service: Injected service.

    Returns:
        ``{"format": ..., "output": ...}`` where ``output`` is the formatted
        text: papers as ``@article``-style entries and patents as biblatex
        ``@patent``, CSL ``patent`` or RIS ``PAT`` entries. Unresolved
        identifiers are included as comments in the comment style of the
        chosen format, each with its reason: ``not found`` for a paper, or
        the EPO outcome for a patent (``not_found``, ``epo_not_configured``,
        ``rate_limited``, ``epo_unavailable``, ``invalid_patent_number``,
        ``resolve_failed``).

        When nothing resolves, ``{"error": "no_papers_resolved", "failed":
        [...], "errors": [{"identifier": ..., "reason": ...}, ...]}``. Other
        failures return an error mapping.

        The key is ``output`` rather than ``citations`` because the CSL-JSON
        formatter emits its own ``citations`` key, which would collide.
    """
    if not paper_ids:
        return {"error": "paper_ids must not be empty"}

    if len(paper_ids) > 100:
        return {"error": "paper_ids must contain at most 100 identifiers"}

    patent_indices = [i for i, raw in enumerate(paper_ids) if _is_patent_id(raw)]
    patent_set = set(patent_indices)
    paper_indices = [i for i in range(len(paper_ids)) if i not in patent_set]

    try:
        s2_results = await _resolve_papers(
            [paper_ids[i] for i in paper_indices], enrich, service
        )
    except httpx.HTTPStatusError as exc:
        return s2_error_payload(exc)

    papers = dict(zip(paper_indices, s2_results, strict=True))
    patents = await _resolve_patents(patent_indices, paper_ids, service)
    records, errors = _collect(paper_ids, papers, patents)

    if not records:
        return {
            "error": "no_papers_resolved",
            "failed": [e["identifier"] for e in errors],
            "errors": errors,
        }

    formatter = _FORMATTERS[citation_format]
    return {"format": citation_format, "output": formatter(records, errors)}


# The reference page these tools are listed on (scripts/gen_reference.py).
_GROUP = "group:citations"


def register_citation_tools(
    mcp: FastMCP, jobs: Jobs, jobs_config: JobsConfig | None = None
) -> None:
    """Register citation generation tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared jobs mechanics; enrichment over a large batch can
            outrun the soft deadline and is then promoted.
    """
    register_s2_tool(
        mcp,
        jobs,
        jobs_config=jobs_config,
        tags={_GROUP},
        annotations={
            "title": "Generate Citations",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(generate_citations)
