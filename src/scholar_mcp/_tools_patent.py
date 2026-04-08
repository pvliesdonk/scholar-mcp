"""Patent search and retrieval MCP tools."""

from __future__ import annotations

import asyncio as _asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._epo_client import EpoClient, EpoRateLimitedError
from ._patent_numbers import DocdbNumber, normalize
from ._protocols import CacheProtocol
from ._rate_limiter import RateLimitedError
from ._s2_client import FIELD_SETS, S2Client
from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)

# Mapping from date_type parameter to EPO CQL field name.
_DATE_FIELDS: dict[str, str] = {
    "publication": "pd",
    "filing": "ad",
    "priority": "prd",
}


def _cql_escape(s: str) -> str:
    """Escape special characters for EPO CQL double-quoted strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _build_cql(
    query: str | None = None,
    *,
    cpc_classification: str | None = None,
    applicant: str | None = None,
    inventor: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    date_type: str = "publication",
    jurisdiction: str | None = None,
) -> str:
    """Build an EPO CQL query string from individual filter parameters.

    Translates tool parameters into Contextual Query Language (CQL) clauses
    joined with ``AND``.  When *query* is provided it is mapped to a
    title+abstract search (``ta=`` field); omitting it allows searching purely
    by structured filters (inventor, applicant, CPC, date, jurisdiction).

    Args:
        query: Free-text search string — mapped to ``ta="query"``.  Optional;
            when omitted the search relies entirely on the filter parameters.
        cpc_classification: CPC classification code, e.g. ``"H01M10/00"``.
        applicant: Applicant name, mapped to ``pa=``.
        inventor: Inventor name, mapped to ``in=``.
        date_from: Lower bound date string, e.g. ``"2020-01-01"`` or
            ``"20200101"``.
        date_to: Upper bound date string, e.g. ``"2023-12-31"`` or
            ``"20231231"``.
        date_type: Which date field to constrain — ``"publication"`` (``pd``),
            ``"filing"`` (``ad``), or ``"priority"`` (``prd``).
        jurisdiction: Two-letter patent authority code, e.g. ``"EP"`` or
            ``"WO"``.

    Returns:
        A CQL expression string ready for the EPO OPS search endpoint.

    Raises:
        ValueError: When no search criteria are provided at all.
    """
    parts: list[str] = []
    if query is not None:
        parts.append(f'ta="{_cql_escape(query)}"')

    if cpc_classification is not None:
        parts.append(f'cpc="{_cql_escape(cpc_classification)}"')

    if applicant is not None:
        parts.append(f'pa="{_cql_escape(applicant)}"')

    if inventor is not None:
        parts.append(f'in="{_cql_escape(inventor)}"')

    if date_from is not None or date_to is not None:
        field = _DATE_FIELDS.get(date_type, "pd")
        # Normalise YYYY-MM-DD → YYYYMMDD
        d_from = date_from.replace("-", "") if date_from else None
        d_to = date_to.replace("-", "") if date_to else None
        if d_from and not d_from.isdigit():
            raise ValueError(f"Invalid date_from: {date_from!r}")
        if d_to and not d_to.isdigit():
            raise ValueError(f"Invalid date_to: {date_to!r}")
        if d_from is not None and d_to is not None:
            parts.append(f'{field} within "{d_from},{d_to}"')
        elif d_from is not None:
            parts.append(f"{field} >= {d_from}")
        else:
            parts.append(f"{field} <= {d_to}")

    if jurisdiction is not None:
        parts.append(f'pn="{_cql_escape(jurisdiction)}"')

    if not parts:
        raise ValueError(
            "At least one search criterion is required: query, inventor, applicant, "
            "cpc_classification, jurisdiction, or a date range."
        )

    return " AND ".join(parts)


def register_patent_tools(mcp: FastMCP) -> None:
    """Register patent search and retrieval tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool(
        tags={"patent"},
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def search_patents(
        query: str | None = None,
        cpc_classification: str | None = None,
        applicant: str | None = None,
        inventor: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        date_type: Literal["publication", "filing", "priority"] = "publication",
        jurisdiction: str | None = None,
        limit: int = 10,
        offset: int = 0,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Search for patents in the European Patent Office database.

        Covers European patents and global patents via INPADOC (100+ patent
        offices). At least one parameter must be provided. For keyword search,
        ``query`` searches titles and abstracts. To find all patents by an
        inventor or applicant, omit ``query`` and use only the structured
        filters. For academic paper search, use search_papers instead.

        Args:
            query: Keyword search — searches patent titles and abstracts.
                Optional; omit when searching purely by inventor, applicant,
                CPC code, or date.
            cpc_classification: CPC classification code to filter by,
                e.g. ``"H01M10/00"`` for lithium-ion batteries.
            applicant: Applicant (assignee) name to filter by.
            inventor: Inventor name to filter by.
            date_from: Earliest date (``YYYY-MM-DD``).
            date_to: Latest date (``YYYY-MM-DD``).
            date_type: Date field to apply range to — ``"publication"``,
                ``"filing"``, or ``"priority"``.
            jurisdiction: Restrict to a single patent authority, e.g.
                ``"EP"``, ``"WO"``, or ``"US"``.
            limit: Maximum results to return (default 10).
            offset: Pagination offset (0-based).
            bundle: Injected service bundle.

        Returns:
            JSON string with ``total_count`` and ``references`` list, or an
            error dict if the EPO client is not configured or the API fails.
            If the EPO service is busy, the request is automatically retried
            once and ``{"queued": true, "task_id": "..."}`` is returned. Use
            ``get_task_result`` to retrieve the result. If the retry also
            fails, ``get_task_result`` returns ``status: failed`` — call this
            tool again after about 60 seconds. Do not attempt to manage or
            reason about EPO throttle states directly.
        """
        if bundle.epo is None:
            return json.dumps(
                {
                    "error": "epo_not_configured",
                    "detail": (
                        "EPO OPS credentials are not set. "
                        "Configure SCHOLAR_MCP_EPO_CONSUMER_KEY and "
                        "SCHOLAR_MCP_EPO_CONSUMER_SECRET."
                    ),
                }
            )

        try:
            cql = _build_cql(
                query,
                cpc_classification=cpc_classification,
                applicant=applicant,
                inventor=inventor,
                date_from=date_from,
                date_to=date_to,
                date_type=date_type,
                jurisdiction=jurisdiction,
            )
        except ValueError as exc:
            return json.dumps({"error": "invalid_query", "detail": str(exc)})
        range_begin = offset + 1  # EPO OPS uses 1-based ranges
        range_end = offset + limit
        cache_key = f"{cql}|{range_begin}-{range_end}"

        # Check cache first
        cached = await bundle.cache.get_patent_search(cache_key)
        if cached is not None:
            logger.debug("patent_search_cache_hit cql=%s", cql)
            return json.dumps(cached)

        async def _execute(*, retry: bool = True) -> str:
            # Note: retry flag is accepted for task queue compatibility but
            # EPO client does not yet have a retry-aware path (unlike S2).
            # The queued re-attempt still defers work away from the request.
            result = await bundle.epo.search(  # type: ignore[union-attr]
                cql,
                range_begin=range_begin,
                range_end=range_end,
            )
            await bundle.cache.set_patent_search(cache_key, result)
            return json.dumps(result)

        try:
            return await _execute(retry=False)
        except (RateLimitedError, EpoRateLimitedError):
            task_id = bundle.tasks.submit(_execute(retry=True), tool="search_patents")
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "search_patents"}
            )

    @mcp.tool(
        tags={"patent"},
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def get_patent(
        patent_number: str,
        sections: (
            list[
                Literal[
                    "biblio", "claims", "description", "family", "legal", "citations"
                ]
            ]
            | None
        ) = None,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Get detailed information about a single patent.

        Accepts patent numbers in any format (EP, WO, US, etc.). By default
        returns bibliographic data only -- use the sections parameter to
        request additional detail (claims, description, family members, legal
        status, cited references). When sections includes 'citations',
        non-patent literature references are resolved to Semantic Scholar
        papers on a best-effort basis; unresolved references are returned as
        raw citation strings.

        Args:
            patent_number: Patent number in any common format, e.g.
                ``"EP1234567A1"``, ``"WO2024/123456"``, or ``"US11,234,567B2"``.
            sections: Sections to include in the response. Defaults to
                ``["biblio"]``. Available sections: biblio, claims,
                description, family, legal, citations.  When citations
                is included, NPL references are resolved via Semantic
                Scholar on a best-effort basis.
            bundle: Injected service bundle.

        Returns:
            JSON string with ``patent_number`` (normalised DOCDB format) and
            the requested section data, or an error dict on failure.
            If the EPO service is busy, the request is automatically retried
            once and ``{"queued": true, "task_id": "..."}`` is returned. Use
            ``get_task_result`` to retrieve the result. If the retry also
            fails, ``get_task_result`` returns ``status: failed`` — call this
            tool again after about 60 seconds. Do not attempt to manage or
            reason about EPO throttle states directly.
        """
        if bundle.epo is None:
            return json.dumps(
                {
                    "error": "epo_not_configured",
                    "detail": (
                        "EPO OPS credentials are not set. "
                        "Configure SCHOLAR_MCP_EPO_CONSUMER_KEY and "
                        "SCHOLAR_MCP_EPO_CONSUMER_SECRET."
                    ),
                }
            )

        try:
            doc = normalize(patent_number)
        except ValueError as exc:
            return json.dumps(
                {
                    "error": "invalid_patent_number",
                    "detail": str(exc),
                }
            )

        effective_sections = (
            list(dict.fromkeys(sections)) if sections is not None else ["biblio"]
        )

        async def _execute(*, retry: bool = True) -> str:
            # Note: retry flag accepted for task queue compatibility;
            # EPO client does not yet have a retry-aware path.
            return await _fetch_patent_sections(
                doc=doc,
                sections=effective_sections,
                epo=bundle.epo,  # type: ignore[arg-type]
                cache=bundle.cache,
                s2=bundle.s2,
            )

        try:
            return await _execute(retry=False)
        except (RateLimitedError, EpoRateLimitedError):
            task_id = bundle.tasks.submit(_execute(retry=True), tool="get_patent")
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "get_patent"}
            )

    @mcp.tool(
        tags={"patent"},
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def get_citing_patents(
        paper_id: str,
        limit: int = 10,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Find patents that cite a given academic paper.

        Coverage is incomplete -- relies on EPO OPS citation search which
        does not capture all patent-to-paper citations. Best results with
        DOIs of well-known, highly-cited papers. Returns confirmed matches
        only, not an exhaustive list.

        Args:
            paper_id: Paper identifier (DOI preferred, also accepts
                title keywords).
            limit: Maximum number of citing patents to return
                (default 10, max 25).
            bundle: Injected service bundle.

        Returns:
            JSON string with ``paper_id``, ``patents`` list (each with
            biblio data and ``match_source``), ``total_count``, and a
            ``note`` about coverage limitations.
            If the EPO service is busy, the request is automatically retried
            once and ``{"queued": true, "task_id": "..."}`` is returned. Use
            ``get_task_result`` to retrieve the result. If the retry also
            fails, ``get_task_result`` returns ``status: failed`` — call this
            tool again after about 60 seconds. Do not attempt to manage or
            reason about EPO throttle states directly.
        """
        if bundle.epo is None:
            return json.dumps(
                {
                    "error": "epo_not_configured",
                    "detail": (
                        "EPO OPS credentials are not set. "
                        "Configure SCHOLAR_MCP_EPO_CONSUMER_KEY and "
                        "SCHOLAR_MCP_EPO_CONSUMER_SECRET."
                    ),
                }
            )

        effective_limit = min(limit, 25)

        async def _execute(*, retry: bool = True) -> str:
            # Note: retry flag for task queue compatibility.
            return await _get_citing_patents(
                paper_id=paper_id,
                epo=bundle.epo,  # type: ignore[arg-type]
                limit=effective_limit,
            )

        try:
            return await _execute(retry=False)
        except (RateLimitedError, EpoRateLimitedError):
            task_id = bundle.tasks.submit(
                _execute(retry=True), tool="get_citing_patents"
            )
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "get_citing_patents"}
            )


# All available patent sections.
_AVAILABLE_SECTIONS = {
    "biblio",
    "claims",
    "description",
    "family",
    "legal",
    "citations",
}


async def _fetch_patent_sections(
    *,
    doc: DocdbNumber,
    sections: Sequence[str],
    epo: EpoClient,
    cache: CacheProtocol,
    s2: S2Client | None = None,
) -> str:
    """Fetch requested sections for a patent, with caching.

    Cache lookups run concurrently via ``asyncio.gather``.  Actual EPO
    API calls are serialised by the ``asyncio.Lock`` inside ``EpoClient``,
    so no additional concurrency limiting is needed here.  When the
    ``citations`` section is requested, non-patent literature (NPL)
    references are resolved against Semantic Scholar on a best-effort
    basis if an S2 client is provided.

    Args:
        doc: Normalised DOCDB patent number.
        sections: List of section names to include.
        epo: EPO client instance.
        cache: Cache instance with patent get/set methods.
        s2: Optional S2 client for NPL resolution.

    Returns:
        JSON string with patent_number and requested section data.
    """
    patent_id = doc.docdb
    result: dict[str, Any] = {"patent_number": patent_id}

    async def _fetch_biblio() -> None:
        cached = await cache.get_patent(patent_id)
        if cached is not None:
            result["biblio"] = cached
            return
        biblio = await epo.get_biblio(doc)
        if not biblio.get("title") and not biblio.get("applicants"):
            result["_not_found"] = True
            return
        await cache.set_patent(patent_id, biblio)
        result["biblio"] = biblio

    async def _fetch_claims() -> None:
        cached = await cache.get_patent_claims(patent_id)
        if cached is not None:
            result["claims"] = cached
            return
        claims = await epo.get_claims(doc)
        await cache.set_patent_claims(patent_id, claims)
        result["claims"] = claims

    async def _fetch_description() -> None:
        cached = await cache.get_patent_description(patent_id)
        if cached is not None:
            result["description"] = cached
            return
        desc = await epo.get_description(doc)
        await cache.set_patent_description(patent_id, desc)
        result["description"] = desc

    async def _fetch_family() -> None:
        cached = await cache.get_patent_family(patent_id)
        if cached is not None:
            result["family"] = cached
            return
        family = await epo.get_family(doc)
        await cache.set_patent_family(patent_id, family)
        result["family"] = family

    async def _fetch_legal() -> None:
        cached = await cache.get_patent_legal(patent_id)
        if cached is not None:
            result["legal"] = cached
            return
        legal = await epo.get_legal(doc)
        await cache.set_patent_legal(patent_id, legal)
        result["legal"] = legal

    async def _fetch_citations() -> None:
        cached = await cache.get_patent_citations(patent_id)
        if cached is not None:
            citations = cached
        else:
            citations = await epo.get_citations(doc)
            await cache.set_patent_citations(patent_id, citations)

        patent_refs = citations["patent_refs"]
        npl_refs = citations["npl_refs"]

        # Resolve NPL references against Semantic Scholar.
        # Intentionally re-runs on cache hits: the cache stores raw EPO
        # citation data (patent_refs + unresolved npl_refs) so that S2
        # resolution always reflects the latest paper index state.
        resolved_npl: list[dict[str, Any]] = []
        if s2 is not None and npl_refs:
            # Build batch of DOI identifiers
            doi_indices: list[int] = []
            doi_ids: list[str] = []
            for i, npl in enumerate(npl_refs):
                if npl["doi"]:
                    doi_indices.append(i)
                    doi_ids.append(f"DOI:{npl['doi']}")

            # Batch resolve DOIs via S2
            s2_results: list[dict[str, Any] | None] = [None] * len(doi_ids)
            if doi_ids:
                try:
                    s2_results = await s2.batch_resolve(
                        doi_ids, fields=FIELD_SETS["compact"]
                    )
                except RateLimitedError:
                    raise
                except Exception:
                    logger.warning("npl_resolution_failed patent=%s", patent_id)
                    s2_results = [None] * len(doi_ids)

            # Build resolved NPL list
            s2_map: dict[int, dict[str, Any] | None] = dict(
                zip(doi_indices, s2_results, strict=True)
            )
            for i, npl in enumerate(npl_refs):
                entry: dict[str, Any] = {"raw": npl["raw"]}
                s2_paper = s2_map.get(i)
                if s2_paper is not None:
                    entry["paper"] = s2_paper
                    entry["confidence"] = "high"
                elif npl["doi"]:
                    # Had DOI but resolution failed
                    entry["doi"] = npl["doi"]
                    entry["confidence"] = None
                else:
                    entry["confidence"] = None
                resolved_npl.append(entry)
        else:
            resolved_npl = [{"raw": n["raw"], "confidence": None} for n in npl_refs]

        result["citations"] = {
            "patent_refs": patent_refs,
            "npl_refs": resolved_npl,
        }

    fetcher_map: dict[str, Any] = {
        "biblio": _fetch_biblio,
        "claims": _fetch_claims,
        "description": _fetch_description,
        "family": _fetch_family,
        "legal": _fetch_legal,
        "citations": _fetch_citations,
    }

    fetchers = [fetcher_map[s]() for s in sections if s in fetcher_map]
    # Always probe biblio for not-found detection, even when not requested.
    if "biblio" not in sections:
        fetchers.append(_fetch_biblio())
    await _asyncio.gather(*fetchers)

    # Detect not-found from biblio probe
    if result.pop("_not_found", False):
        return json.dumps(
            {
                "error": "patent_not_found",
                "detail": (
                    f"Patent {patent_id} not found or has no data. "
                    "Check the number format."
                ),
            }
        )

    # Remove biblio if it was only fetched as a probe for not-found detection
    if "biblio" not in sections:
        result.pop("biblio", None)

    return json.dumps(result)


async def _get_citing_patents(
    *,
    paper_id: str,
    epo: EpoClient,
    limit: int = 10,
) -> str:
    """Search EPO OPS for patents citing a paper.

    Uses the ``ct=`` (cited document) CQL field to find patents whose
    cited references mention the given identifier. Fetches biblio for
    each result.

    Args:
        paper_id: Paper identifier (DOI or keywords).
        epo: EPO client instance.
        limit: Max results.

    Returns:
        JSON string with paper_id, patents list, total_count, and note.
    """
    cql = f'ct="{_cql_escape(paper_id)}"'
    try:
        search_result = await epo.search(cql, range_begin=1, range_end=limit)
    except Exception as exc:
        if isinstance(exc, (RateLimitedError, EpoRateLimitedError)):
            raise
        logger.warning("citing_patent_search_failed paper=%s", paper_id)
        return json.dumps(
            {
                "paper_id": paper_id,
                "patents": [],
                "total_count": 0,
                "note": "EPO citation search failed. Try a different identifier format.",
            }
        )

    patents: list[dict[str, Any]] = []
    for ref in search_result.get("references", []):
        doc = DocdbNumber(ref["country"], ref["number"], ref.get("kind", ""))
        try:
            biblio = await epo.get_biblio(doc)
            biblio["match_source"] = "epo_search"
            patents.append(biblio)
        except (RateLimitedError, EpoRateLimitedError):
            raise
        except Exception:
            logger.warning("citing_patent_biblio_failed patent=%s", doc.docdb)

    return json.dumps(
        {
            "paper_id": paper_id,
            "patents": patents,
            "total_count": search_result.get("total_count", 0),
            "note": (
                "Coverage is incomplete. Results come from EPO OPS citation "
                "search and may not capture all patent-to-paper citations."
            ),
        }
    )
