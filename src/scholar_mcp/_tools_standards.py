"""Standards search, lookup, and identifier resolution MCP tools."""

from __future__ import annotations

import json
import logging

from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._server_deps import ServiceBundle, get_bundle
from ._standards_client import _resolve_identifier_local

logger = logging.getLogger(__name__)


def register_standards_tools(mcp: FastMCP) -> None:
    """Register standards tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
    )
    async def resolve_standard_identifier(
        raw: str,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Normalise a messy standard citation string to its canonical form.

        Tries local regex first (fast, no network). Falls back to querying
        source APIs when local patterns don't match. Returns all candidates
        when the input is ambiguous.

        Examples:
            resolve_standard_identifier("rfc9000")
            resolve_standard_identifier("nist 800-53")
            resolve_standard_identifier("WCAG2.1")

        Args:
            raw: Raw citation string as it appears in a paper reference.

        Returns:
            JSON with ``canonical``, ``body``, and ``record`` when unambiguous;
            ``{"ambiguous": true, "candidates": [...]}`` when multiple matches;
            ``{"canonical": null, "body": null, "record": null}`` when unresolvable.
        """
        raw = raw.strip()

        # 1. Check alias cache first
        cached_canonical = await bundle.cache.get_standard_alias(raw)
        if cached_canonical is not None:
            cached_record = await bundle.cache.get_standard(cached_canonical)
            if cached_record is not None:
                return json.dumps(
                    {
                        "canonical": cached_canonical,
                        "body": cached_record.get("body"),
                        "record": cached_record,
                    }
                )

        # 2. Try local regex
        resolved = _resolve_identifier_local(raw)
        if resolved is not None:
            canonical, body = resolved
            record = await bundle.standards.get(canonical)
            if record is not None:
                await bundle.cache.set_standard_alias(raw, canonical)
                await bundle.cache.set_standard(canonical, record)  # type: ignore[arg-type]
                return json.dumps(
                    {"canonical": canonical, "body": body, "record": record}
                )
            return json.dumps({"canonical": canonical, "body": body, "record": None})

        # 3. API fallback — search all sources
        candidates = await bundle.standards.resolve(raw)
        if not candidates:
            return json.dumps({"canonical": None, "body": None, "record": None})
        if len(candidates) == 1:
            record = candidates[0]
            canonical = record.get("identifier", "")
            body = record.get("body", "")
            await bundle.cache.set_standard_alias(raw, canonical)
            await bundle.cache.set_standard(canonical, record)  # type: ignore[arg-type]
            return json.dumps({"canonical": canonical, "body": body, "record": record})

        return json.dumps({"ambiguous": True, "candidates": candidates})

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def search_standards(
        query: str,
        body: str | None = None,
        limit: int = 10,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Search technical standards by identifier, title, or free text.

        Searches NIST, IETF, W3C, and ETSI. Use ``body`` to restrict to one
        source body.

        Examples:
            search_standards("TLS 1.3")
            search_standards("800-53", body="NIST")
            search_standards("accessibility", body="W3C", limit=5)
            search_standards("IoT security", body="ETSI")

        Args:
            query: Identifier, title, or free text.
            body: Optional filter — "NIST", "IETF", "W3C", or "ETSI".
            limit: Maximum results (max 50).

        Returns:
            JSON list of StandardRecord dicts.
        """
        limit = max(1, min(limit, 50))
        cache_key = f"q={query}:body={body}:limit={limit}"

        cached = await bundle.cache.get_standards_search(cache_key)
        if cached is not None:
            logger.debug("standards_search_cache_hit key=%s", cache_key[:80])
            return json.dumps(cached)

        results = await bundle.standards.search(query, body=body, limit=limit)
        await bundle.cache.set_standards_search(cache_key, results)  # type: ignore[arg-type]
        return json.dumps(results)

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def get_standard(
        identifier: str,
        fetch_full_text: bool = False,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Retrieve a standard by identifier (canonical or fuzzy).

        Resolves fuzzy inputs (e.g. "rfc9000", "nist 800-53") to their
        canonical form before fetching. With ``fetch_full_text=True`` and
        docling configured, downloads and converts the full text.

        Examples:
            get_standard("RFC 9000")
            get_standard("NIST SP 800-53 Rev. 5")
            get_standard("rfc9000")
            get_standard("WCAG 2.1", fetch_full_text=True)

        Args:
            identifier: Canonical or fuzzy standard identifier.
            fetch_full_text: If True and docling is configured, download and
                convert the full text PDF/HTML via docling.

        Returns:
            JSON StandardRecord, or ``{"error": "not_found"}`` if unresolvable.
        """
        identifier = identifier.strip()

        # 1. Resolve identifier to canonical form
        resolved = _resolve_identifier_local(identifier)
        canonical = resolved[0] if resolved else identifier

        # 2. Check cache
        cached = await bundle.cache.get_standard(canonical)
        if cached is not None:
            logger.debug("standard_cache_hit identifier=%s", canonical)
            if fetch_full_text:
                return await _handle_full_text(cached, bundle)
            return json.dumps(cached)

        # 3. Fetch from source
        record = await bundle.standards.get(canonical)
        if record is None:
            return json.dumps({"error": "not_found", "identifier": identifier})

        # 4. Cache result
        await bundle.cache.set_standard(canonical, record)  # type: ignore[arg-type]
        if resolved:
            await bundle.cache.set_standard_alias(identifier, canonical)

        if fetch_full_text:
            return await _handle_full_text(record, bundle)  # type: ignore[arg-type]
        return json.dumps(record)


async def _handle_full_text(
    record: dict,  # type: ignore[type-arg]
    bundle: ServiceBundle,
) -> str:
    """Download and convert full text via docling if available.

    If docling is not configured, no full_text_url is present, or the
    download fails, returns the record as-is so the caller can use
    full_text_url to fetch manually.

    Args:
        record: StandardRecord dict.
        bundle: Service bundle with optional docling client and task queue.

    Returns:
        JSON StandardRecord, possibly with ``full_text`` field populated,
        or ``{"queued": true, "task_id": "..."}`` if conversion was queued.
    """
    from ._rate_limiter import RateLimitedError

    if not record.get("full_text_available") or not record.get("full_text_url"):
        return json.dumps(record)

    if bundle.docling is None:
        logger.debug(
            "full_text_requested_but_docling_not_configured id=%s",
            record.get("identifier"),
        )
        return json.dumps(record)

    url: str = record["full_text_url"]
    filename = url.rsplit("/", 1)[-1] or "standard.pdf"

    async def _convert() -> str:
        resp = await bundle.standards._http.get(url, follow_redirects=True)
        resp.raise_for_status()
        markdown = await bundle.docling.convert(resp.content, filename)  # type: ignore[union-attr]
        enriched = {**record, "full_text": markdown}
        return json.dumps(enriched)

    try:
        return await _convert()
    except RateLimitedError:
        task_id = bundle.tasks.submit(_convert(), tool="get_standard")
        return json.dumps(
            {"queued": True, "task_id": task_id, "tool": "get_standard"}
        )
    except Exception as exc:
        logger.warning(
            "full_text_conversion_failed id=%s err=%s", record.get("identifier"), exc
        )
        return json.dumps(record)
