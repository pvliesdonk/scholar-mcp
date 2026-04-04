"""Search and retrieval MCP tools."""

from __future__ import annotations

import json
import logging
from typing import Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._s2_client import FIELD_SETS
from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)


def register_search_tools(mcp: FastMCP) -> None:
    """Register search and retrieval tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool()
    async def search_papers(
        query: str,
        fields: Literal["compact", "standard", "full"] = "compact",
        limit: int = 10,
        offset: int = 0,
        year_start: int | None = None,
        year_end: int | None = None,
        fields_of_study: list[str] | None = None,
        venue: str | None = None,
        min_citations: int | None = None,
        sort: Literal["relevance", "citations", "year"] = "relevance",
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Search Semantic Scholar for papers matching a query.

        Args:
            query: Keyword or semantic search query.
            fields: Field set preset — compact, standard, or full.
            limit: Maximum results to return (max 100).
            offset: Pagination offset.
            year_start: Earliest publication year (inclusive).
            year_end: Latest publication year (inclusive).
            fields_of_study: Filter by fields, e.g. ["Computer Science"].
            venue: Filter by venue name.
            min_citations: Minimum citation count.
            sort: Sort order — relevance, citations, or year.

        Returns:
            JSON string with ``data`` (list of papers) and ``total``.
        """
        year: str | None = None
        if year_start is not None and year_end is not None:
            year = f"{year_start}-{year_end}"
        elif year_start is not None:
            year = f"{year_start}-"
        elif year_end is not None:
            year = f"-{year_end}"

        s2_sort = {
            "relevance": None,
            "citations": "citationCount:desc",
            "year": "publicationDate:desc",
        }.get(sort)
        fos = ",".join(fields_of_study) if fields_of_study else None

        try:
            result = await bundle.s2.search_papers(
                query,
                fields=FIELD_SETS[fields],
                limit=limit,
                offset=offset,
                year=year,
                fieldsOfStudy=fos,
                venue=venue,
                minCitationCount=min_citations,
                sort=s2_sort,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return json.dumps({"error": "not_found", "identifier": query})
            return json.dumps(
                {
                    "error": "upstream_error",
                    "status": exc.response.status_code,
                    "detail": exc.response.text[:200],
                }
            )
        return json.dumps(result)

    @mcp.tool()
    async def get_paper(
        identifier: str,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Fetch full metadata for a single paper.

        Args:
            identifier: Paper identifier — DOI, S2 paper ID, arXiv ID
                (prefix with ``ARXIV:``), ACM ID (``ACM:``), or PubMed ID
                (``PMID:``).

        Returns:
            JSON string with full paper metadata, or
            ``{"error": "not_found", "identifier": "..."}`` if not found.
        """
        cached_id = await bundle.cache.get_alias(identifier) or identifier
        data = await bundle.cache.get_paper(cached_id)
        if data:
            logger.debug("cache_hit identifier=%s", identifier)
            return json.dumps(data)

        try:
            data = await bundle.s2.get_paper(identifier)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return json.dumps({"error": "not_found", "identifier": identifier})
            return json.dumps(
                {
                    "error": "upstream_error",
                    "status": exc.response.status_code,
                    "detail": exc.response.text[:200],
                }
            )

        paper_id = data.get("paperId", "")
        if paper_id:
            await bundle.cache.set_paper(paper_id, data)
            if identifier != paper_id:
                await bundle.cache.set_alias(identifier, paper_id)

        return json.dumps(data)

    @mcp.tool()
    async def get_author(
        identifier: str,
        limit: int = 20,
        offset: int = 0,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Fetch author profile and publications, or search by name.

        If *identifier* looks like a numeric S2 author ID, fetches the author
        directly. Otherwise performs a name search and returns up to 5 candidates
        for disambiguation.

        Args:
            identifier: S2 author ID (numeric string) or free-text author name.
            limit: Publications per page (only used for direct ID lookup).
            offset: Publication page offset (only used for direct ID lookup).

        Returns:
            JSON with author data and paginated ``papers`` list, or
            ``{"candidates": [...]}`` for name searches.
        """
        is_id = identifier.isdigit()

        if is_id:
            cached = await bundle.cache.get_author(identifier)
            if cached:
                return json.dumps(cached)
            try:
                data = await bundle.s2.get_author(identifier, limit=limit, offset=offset)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    return json.dumps({"error": "not_found", "identifier": identifier})
                return json.dumps(
                    {"error": "upstream_error", "status": exc.response.status_code}
                )
            if offset == 0:
                await bundle.cache.set_author(identifier, data)
            return json.dumps(data)

        # Name search — return candidates for disambiguation
        try:
            candidates = await bundle.s2.search_authors(identifier, limit=5)
        except httpx.HTTPStatusError as exc:
            return json.dumps(
                {"error": "upstream_error", "status": exc.response.status_code}
            )
        return json.dumps({"candidates": candidates})
