"""Standards search, lookup, and identifier resolution MCP tools."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import register_long_running_tool

from ._record_types import StandardRecord
from ._server_deps import ServiceBundle, get_bundle
from ._standards_client import resolve_identifier_local

if TYPE_CHECKING:
    from fastmcp_pvl_core import Jobs

logger = logging.getLogger(__name__)


async def resolve_standard_identifier(
    raw: str,
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Normalise a messy standard citation string to its canonical form.

    Tries local regex first (fast, no network). Falls back to querying
    source APIs when local patterns don't match. Returns all candidates
    when the input is ambiguous.

    A cold catalogue makes this slow: the first call after a fresh install or
    a cleared cache downloads and parses each body's index, which runs well
    past the soft deadline. Such a call returns a job handle to poll with
    ``get_job_result`` rather than the result itself.

    Examples:
        resolve_standard_identifier("rfc9000")
        resolve_standard_identifier("nist 800-53")
        resolve_standard_identifier("WCAG2.1")

    Args:
        raw: Raw citation string as it appears in a paper reference.

    Returns:
        A mapping with ``canonical``, ``body``, and ``record`` when
        unambiguous;
        ``{"ambiguous": true, "candidates": [...]}`` when multiple matches;
        ``{"canonical": null, "body": null, "record": null}`` when unresolvable.
    """
    raw = raw.strip()

    # 1. Check alias cache first
    cached_canonical = await bundle.cache.get_standard_alias(raw)
    if cached_canonical is not None:
        cached_record = await bundle.cache.get_standard(cached_canonical)
        if cached_record is not None:
            return {
                "canonical": cached_canonical,
                "body": cached_record.get("body"),
                "record": cached_record,
            }

    # 2. Try local regex
    resolved = resolve_identifier_local(raw)
    if resolved is not None:
        canonical, body = resolved
        record = await bundle.standards.get(canonical)
        if record is not None:
            await bundle.cache.set_standard_alias(raw, canonical)
            await bundle.cache.set_standard(canonical, record)
            return {"canonical": canonical, "body": body, "record": record}
        return {"canonical": canonical, "body": body, "record": None}

    # 3. API fallback — search all sources
    candidates = await bundle.standards.resolve(raw)
    if not candidates:
        return {"canonical": None, "body": None, "record": None}
    if len(candidates) == 1:
        record = candidates[0]
        canonical = record.get("identifier", "")
        body = record.get("body", "")
        await bundle.cache.set_standard_alias(raw, canonical)
        await bundle.cache.set_standard(canonical, record)
        return {"canonical": canonical, "body": body, "record": record}

    return {"ambiguous": True, "candidates": candidates}


async def search_standards(
    query: str,
    body: str | None = None,
    limit: int = 10,
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Search technical standards by identifier, title, or free text.

    Searches NIST, IETF, W3C, and ETSI. Use ``body`` to restrict to one
    source body.

    A cold catalogue makes this slow: the first call after a fresh install or
    a cleared cache downloads and parses each body's index, which runs well
    past the soft deadline. Such a call returns a job handle to poll with
    ``get_job_result`` rather than the result itself.

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
        ``{"results": [...]}`` — the matching StandardRecords.
    """
    limit = max(1, min(limit, 50))
    cache_key = hashlib.sha256(f"{query}:{body}:{limit}".encode()).hexdigest()

    cached = await bundle.cache.get_standards_search(cache_key)
    if cached is not None:
        logger.debug("standards_search_cache_hit key=%s", cache_key[:16])
        return {"results": cached}

    results = await bundle.standards.search(query, body=body, limit=limit)
    await bundle.cache.set_standards_search(cache_key, results)
    return {"results": results}


async def get_standard(
    identifier: str,
    fetch_full_text: bool = False,
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Retrieve a standard by identifier (canonical or fuzzy).

    Resolves fuzzy inputs (e.g. "rfc9000", "nist 800-53") to their
    canonical form before fetching. With ``fetch_full_text=True`` and
    docling configured, downloads and converts the full text.

    With ``fetch_full_text=True`` the docling conversion takes minutes, so
    such a call returns a job handle to poll with ``get_job_result`` rather
    than the record itself. Without it, and on a cache hit, the record comes
    back directly.

    A conversion that fails still returns the record, with the reason in
    ``full_text_error``; ``full_text_url`` is there to fetch by hand. No
    ``full_text`` and no ``full_text_error`` means none was on offer, or
    docling is not configured — neither is worth retrying.

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
        The StandardRecord, or ``{"error": "not_found"}`` if unresolvable.
        With ``fetch_full_text=True``, either ``full_text`` or
        ``full_text_error`` is present.
    """
    identifier = identifier.strip()

    # 1. Resolve identifier to canonical form (alias cache → regex → passthrough)
    cached_canonical = await bundle.cache.get_standard_alias(identifier)
    if cached_canonical is not None:
        canonical = cached_canonical
    else:
        resolved = resolve_identifier_local(identifier)
        canonical = resolved[0] if resolved else identifier

    # 2. Check cache
    cached = await bundle.cache.get_standard(canonical)
    if cached is not None:
        logger.debug("standard_cache_hit identifier=%s", canonical)
        if fetch_full_text:
            return await _handle_full_text(cached, bundle)
        return dict(cached)

    # 3. Fetch from source
    record = await bundle.standards.get(canonical)
    if record is None:
        return {"error": "not_found", "identifier": identifier}

    # 4. Cache result
    await bundle.cache.set_standard(canonical, record)
    if cached_canonical is None:
        await bundle.cache.set_standard_alias(identifier, canonical)

    if fetch_full_text:
        return await _handle_full_text(record, bundle)
    return dict(record)


async def get_sync_status(
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Report the last sync run for each standards body.

    One row per body. ``started_at`` / ``finished_at`` are Unix
    timestamps (seconds). ``errors`` is a list of non-fatal error
    strings from the most recent run (empty on success).

    Returns:
        ``{"runs": [{body, upstream_ref, added, updated,
        unchanged, withdrawn, errors, started_at, finished_at}, ...]}``.
        Empty ``runs`` list when no sync has been run yet.
    """
    runs = await bundle.cache.list_sync_runs()
    return {"runs": runs}


def register_standards_tools(mcp: FastMCP, jobs: Jobs) -> None:
    """Register standards tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared jobs mechanics, used by three of the four tools here.
            ``get_standard`` with ``fetch_full_text=True`` runs a docling
            conversion that takes minutes; ``search_standards`` and
            ``resolve_standard_identifier`` reach each body's catalogue,
            which on a cold cache is downloaded and parsed in full. Only
            ``get_sync_status`` is a plain cache read.
    """
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Resolve Standard Identifier",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
    )(resolve_standard_identifier)
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Search Standards",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(search_standards)
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Get Standard",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(get_standard)
    mcp.tool(
        annotations={
            "title": "Get Sync Status",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
    )(get_sync_status)


async def _handle_full_text(
    record: StandardRecord,
    bundle: ServiceBundle,
) -> dict[str, Any]:
    """Download and convert full text via docling if available.

    If docling is not configured, no full_text_url is present, full_text is
    already populated, or the download fails, returns the record as-is so the
    caller can use full_text_url to fetch manually.

    Args:
        record: StandardRecord dict.
        bundle: Service bundle with an optional docling client.

    Returns:
        The StandardRecord, with ``full_text`` populated when the conversion
        succeeded. A failure returns the record plus ``full_text_error``
        rather than an error response: ``full_text_url`` is still there for
        the caller to fetch by hand, which is more useful than losing the
        metadata too.
    """
    if (
        not record.get("full_text_available")
        or not record.get("full_text_url")
        or record.get("full_text")
    ):
        return dict(record)

    if bundle.docling is None:
        logger.debug(
            "full_text_requested_but_docling_not_configured id=%s",
            record.get("identifier"),
        )
        return dict(record)

    url: str = record["full_text_url"] or ""
    filename = url.rsplit("/", 1)[-1] or "standard.pdf"

    try:
        content = await bundle.standards.download(url)
        markdown = await bundle.docling.convert(content, filename)
    except Exception as exc:
        logger.warning(
            "full_text_conversion_failed id=%s err=%s", record.get("identifier"), exc
        )
        # Mark the failure. Without it this is indistinguishable from "no
        # full text on offer" and from "docling not configured" -- three
        # different situations returning the same record with no full_text.
        return {**record, "full_text_error": str(exc)}

    enriched: dict[str, Any] = {**record, "full_text": markdown}
    identifier = enriched.get("identifier")
    if identifier:
        try:
            await bundle.cache.set_standard(identifier, enriched)  # type: ignore[arg-type]
        except Exception as exc:
            # The conversion succeeded and the markdown is in hand; a cache
            # write that fails must not throw it away.
            logger.warning("standard_cache_write_failed id=%s err=%s", identifier, exc)
    return enriched
