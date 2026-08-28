"""Utility MCP tools: batch_resolve and enrich_paper."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import register_long_running_tool

from ._cache import normalize_isbn
from ._chapter_parser import hint_to_dict, parse_chapter_hint
from ._epo_client import EPO_REPORTED_ERRORS, epo_error_payload, with_epo_retry
from ._openlibrary_client import normalize_book
from ._patent_numbers import is_patent_number, normalize
from ._s2_client import FIELD_SETS, log_s2_error, s2_error_payload
from ._server_deps import ServiceBundle, get_bundle

if TYPE_CHECKING:
    from fastmcp_pvl_core import Jobs

    from ._record_types import PaperRecord

logger = logging.getLogger(__name__)


def _attach_chapter_info(result: dict[str, Any], raw: str) -> None:
    """Attach chapter_info to *result* when parsed hints exist.

    The enrichment pipeline resolves the parent book separately; this
    function only records heuristic hints extracted from the raw
    identifier string (chapter number, page range, parent title, ISBN).

    Args:
        result: Mutable paper result dict to enrich in-place.
        raw: Raw identifier string potentially containing chapter hints.
    """
    hint = parse_chapter_hint(raw)
    if not hint.has_chapter_info:
        return
    result["chapter_info"] = hint_to_dict(hint)


@dataclass
class _Groups:
    """Identifiers sorted by which upstream can resolve them.

    Each list of indices records where its entries sat in the caller's
    original list, so results can be merged back in order after the three
    groups resolve concurrently.

    Attributes:
        paper_indices: Positions of paper identifiers.
        paper_ids: The paper identifiers themselves.
        patent_indices: Positions of patent numbers.
        patent_raws: The patent numbers themselves.
        isbn_indices: Positions of ISBNs.
        isbn_raws: The ISBNs, with the ``ISBN:`` prefix stripped.
        doi_map: Original index to raw DOI, for the OpenAlex fallback.
    """

    paper_indices: list[int] = field(default_factory=list)
    paper_ids: list[str] = field(default_factory=list)
    patent_indices: list[int] = field(default_factory=list)
    patent_raws: list[str] = field(default_factory=list)
    isbn_indices: list[int] = field(default_factory=list)
    isbn_raws: list[str] = field(default_factory=list)
    doi_map: dict[int, str] = field(default_factory=dict)


def _classify(identifiers: list[str]) -> _Groups:
    """Sort identifiers into the three groups that resolve independently.

    Args:
        identifiers: The caller's raw identifier list.

    Returns:
        The populated :class:`_Groups`.
    """
    groups = _Groups()
    for i, raw in enumerate(identifiers):
        if raw.startswith("ISBN:"):
            groups.isbn_indices.append(i)
            groups.isbn_raws.append(raw[5:])
        elif is_patent_number(raw):
            groups.patent_indices.append(i)
            groups.patent_raws.append(raw)
        else:
            groups.paper_indices.append(i)
            groups.paper_ids.append(raw)
            if raw.startswith("DOI:"):
                groups.doi_map[i] = raw[4:]
    return groups


async def _resolve_paper(
    idx: int,
    raw: str,
    s2_data: PaperRecord | None,
    doi_map: dict[int, str],
    bundle: ServiceBundle,
) -> tuple[int, dict[str, Any]]:
    """Build the result entry for one paper identifier.

    Args:
        idx: Position in the caller's original list.
        raw: The raw identifier.
        s2_data: What the S2 batch endpoint returned, or None.
        doi_map: Index to DOI, for the OpenAlex fallback.
        bundle: Injected service bundle.

    Returns:
        ``(idx, entry)`` so the caller can restore the original order.
    """
    if s2_data is not None:
        paper_result: dict[str, Any] = {"identifier": raw, "paper": s2_data}
        _attach_chapter_info(paper_result, raw)
        return idx, paper_result
    if idx in doi_map:
        oa = await bundle.openalex.get_by_doi(doi_map[idx])
        if oa:
            paper_result = {"identifier": raw, "paper": oa, "source": "openalex"}
            _attach_chapter_info(paper_result, raw)
            return idx, paper_result
    return idx, {"identifier": raw, "error": "not_found"}


async def _resolve_patent(
    idx: int, raw: str, bundle: ServiceBundle
) -> tuple[int, dict[str, Any]]:
    """Build the result entry for one patent number.

    Unlike the single-patent tools, a reportable EPO state degrades just this
    entry rather than failing the whole batch: the caller asked about many
    identifiers independently, and the entry can say exactly what happened.

    Args:
        idx: Position in the caller's original list.
        raw: The raw patent number.
        bundle: Injected service bundle.

    Returns:
        ``(idx, entry)`` so the caller can restore the original order.
    """
    epo = bundle.epo
    if epo is None:
        return idx, {
            "identifier": raw,
            "error": "epo_not_configured",
            "source_type": "patent",
        }
    try:
        doc = normalize(raw)
        biblio = await with_epo_retry(lambda: epo.get_biblio(doc))
    except ValueError:
        return idx, {
            "identifier": raw,
            "error": "invalid_patent_number",
            "source_type": "patent",
        }
    except EPO_REPORTED_ERRORS as exc:
        return idx, {
            "identifier": raw,
            "source_type": "patent",
            **epo_error_payload(exc),
        }
    except Exception:
        logger.warning("batch_patent_resolve_failed id=%s", raw)
        return idx, {
            "identifier": raw,
            "error": "resolve_failed",
            "source_type": "patent",
        }
    if not biblio.get("title") and not biblio.get("applicants"):
        return idx, {
            "identifier": raw,
            "error": "not_found",
            "source_type": "patent",
        }
    return idx, {"identifier": raw, "patent": biblio, "source_type": "patent"}


async def _resolve_isbn(
    idx: int, raw_isbn: str, bundle: ServiceBundle
) -> tuple[int, dict[str, Any]]:
    """Build the result entry for one ISBN.

    Args:
        idx: Position in the caller's original list.
        raw_isbn: The ISBN with its ``ISBN:`` prefix already stripped.
        bundle: Injected service bundle.

    Returns:
        ``(idx, entry)`` so the caller can restore the original order.
    """
    identifier = f"ISBN:{raw_isbn}"
    isbn = normalize_isbn(raw_isbn)
    cached = await bundle.cache.get_book_by_isbn(isbn)
    if cached is not None:
        return idx, {"identifier": identifier, "book": cached, "source_type": "book"}
    edition = await bundle.openlibrary.get_by_isbn(isbn)
    if edition is None:
        return idx, {
            "identifier": identifier,
            "error": "not_found",
            "source_type": "book",
        }
    book = normalize_book(edition, source="edition")
    await bundle.cache.set_book_by_isbn(isbn, book)
    return idx, {"identifier": identifier, "book": book, "source_type": "book"}


async def batch_resolve(
    identifiers: list[str],
    fields: Literal["compact", "standard", "full"] = "standard",
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Resolve a list of paper, patent, or book identifiers to full records.

    Uses the S2 batch endpoint for paper IDs/DOIs, with OpenAlex fallback.
    Patent numbers (e.g. EP1234567A1) are auto-detected and resolved via
    the EPO OPS API when configured. ISBNs (prefixed ``ISBN:``) are
    resolved via Open Library.

    Identifiers fan out across three upstreams, so a large batch runs long
    and is then handed back as a job handle to poll with ``get_job_result``
    rather than the records themselves.

    Args:
        identifiers: List of S2 IDs, DOIs (prefixed ``DOI:``), plain DOIs,
            patent numbers (e.g. ``EP1234567A1``, ``US11234567B2``),
            or ISBNs (prefixed ``ISBN:``, e.g. ``ISBN:9780201633610``).
        fields: Field set preset (applies to paper results only).
        bundle: Injected service bundle.

    Returns:
        ``{"results": [...]}`` in the caller's original order. Paper entries
        have a ``paper`` key, patent entries a ``patent`` key and
        ``source_type: "patent"``, book entries a ``book`` key and
        ``source_type: "book"``. Unresolved entries have an ``error`` key.
    """
    groups = _classify(identifiers)

    s2_results: list[PaperRecord | None] = []
    if groups.paper_ids:
        try:
            s2_results = await bundle.s2.batch_resolve(
                groups.paper_ids, fields=FIELD_SETS[fields]
            )
        except httpx.HTTPStatusError as exc:
            return s2_error_payload(exc)

    resolved = await asyncio.gather(
        *(
            _resolve_paper(
                groups.paper_indices[j],
                groups.paper_ids[j],
                data,
                groups.doi_map,
                bundle,
            )
            for j, data in enumerate(s2_results)
        ),
        *(
            _resolve_patent(groups.patent_indices[j], raw, bundle)
            for j, raw in enumerate(groups.patent_raws)
        ),
        *(
            _resolve_isbn(groups.isbn_indices[j], raw, bundle)
            for j, raw in enumerate(groups.isbn_raws)
        ),
    )

    result_map: dict[int, dict[str, Any]] = dict(resolved)
    return {"results": [result_map[i] for i in range(len(identifiers))]}


def _select_enrichment_fields(
    oa_data: dict[str, Any], fields: list[str]
) -> dict[str, Any]:
    """Pick the requested enrichment fields out of an OpenAlex record.

    Args:
        oa_data: The OpenAlex work record.
        fields: Which enrichment fields the caller asked for.

    Returns:
        A mapping holding only the requested fields.
    """
    result: dict[str, Any] = {}
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
    return result


async def enrich_paper(
    identifier: str,
    fields: list[Literal["affiliations", "funders", "oa_status", "concepts"]],
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Fetch OpenAlex metadata to supplement Semantic Scholar data.

    Resolves the paper's DOI from S2, then queries OpenAlex for the
    requested enrichment fields. Results are cached for 30 days.

    A cached record answers immediately. Should the lookup run long it
    continues in the background and returns a job handle to poll with
    ``get_job_result``.

    Args:
        identifier: S2 paper ID or DOI (prefix ``DOI:``).
        fields: One or more of: affiliations, funders, oa_status, concepts.
        bundle: Injected service bundle.

    Returns:
        A mapping with the requested fields plus ``doi``, or an error mapping.
    """
    if identifier.startswith("DOI:"):
        doi: str | None = identifier[4:]
    else:
        try:
            paper = await bundle.s2.get_paper(identifier, fields="externalIds,paperId")
        except httpx.HTTPStatusError as exc:
            # A rate limit that outlived the client's own retries reaches here
            # too, and reporting it as "not_found" would tell the caller to
            # stop asking about a paper that exists.
            if exc.response.status_code == 429:
                log_s2_error(exc)
                return {
                    "error": "rate_limited",
                    "identifier": identifier,
                    "retryable": True,
                }
            log_s2_error(exc)
            return {"error": "not_found", "identifier": identifier}
        doi = (paper.get("externalIds") or {}).get("DOI")

    if not doi:
        return {"error": "no_doi", "identifier": identifier}

    oa_data = await bundle.cache.get_openalex(doi)
    if oa_data is None:
        oa_data = await bundle.openalex.get_by_doi(doi)
        if oa_data is None:
            return {"error": "not_found_in_openalex", "doi": doi}
        await bundle.cache.set_openalex(doi, oa_data)

    return {"doi": doi, **_select_enrichment_fields(oa_data, list(fields))}


def register_utility_tools(mcp: FastMCP, jobs: Jobs) -> None:
    """Register utility tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared jobs mechanics. Both tools fan out across upstreams, so
            either can outrun the soft deadline and be promoted.
    """
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Batch Resolve Identifiers",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(batch_resolve)
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Enrich Paper",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(enrich_paper)
