"""Standards search, lookup, and identifier resolution MCP tools."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import register_long_running_tool

from ._record_types import StandardRecord
from ._server_deps import get_service
from ._standards_client import StandardsUpstreamError, resolve_identifier_local
from ._text_window import DEFAULT_MAX_TEXT_CHARS, page_text
from .domain import Service


def _upstream_error_payload(
    failures: list[StandardsUpstreamError], identifier: str
) -> dict[str, Any]:
    """Map sources that never answered to a payload distinct from not_found.

    ``not_found`` tells an LLM caller to stop asking about this identifier. A
    request that was refused has to say the opposite, so a 429 is reported as
    ``rate_limited`` with ``retryable``, the shape ``get_book_excerpt`` and the
    EPO tools already emit.

    ``status`` and ``detail`` describe the first failure, which is the only
    one a resolved identifier can produce. The fallback walk can collect
    several, so ``failed_bodies`` names them all and shares its vocabulary
    with ``search_standards``. Today only ETSI raises; #453 is what makes the
    list grow.

    Args:
        failures: The upstream failures gathered for this lookup.
        identifier: The identifier that was being looked up.

    Returns:
        The caller-facing error mapping.
    """
    first = failures[0]
    bodies = [f.body for f in failures]
    if first.status == 429:
        return {
            "error": "rate_limited",
            "identifier": identifier,
            "body": first.body,
            "failed_bodies": bodies,
            "retryable": True,
        }
    return {
        "error": "upstream_error",
        "identifier": identifier,
        "body": first.body,
        "failed_bodies": bodies,
        "status": first.status,
        "detail": first.detail,
    }


def _failure_warning(failures: list[StandardsUpstreamError]) -> str:
    """Name the sources that did not answer, for a partial result.

    Deliberately a ``warning`` rather than an ``error``: a caller
    pattern-matching on ``error`` would throw away the results that did
    arrive.

    Args:
        failures: The failures gathered during the search.

    Returns:
        One sentence naming each source and its status.
    """
    named = ", ".join(f"{f.body} ({f.status or 'no response'})" for f in failures)
    return (
        f"Incomplete: no answer from {named}. Results from the other sources "
        "are unaffected, and the missing ones may still hold matches."
    )


if TYPE_CHECKING:
    from fastmcp_pvl_core import Jobs

logger = logging.getLogger(__name__)


async def resolve_standard_identifier(
    raw: str,
    service: Service = Depends(get_service),
) -> dict[str, Any]:
    """Normalise a messy standard citation string to its canonical form.

    Tries local regex first (fast, no network). Falls back to querying
    source APIs when local patterns don't match. Returns all candidates
    when the input is ambiguous.

    A cold catalogue makes this slow: the first call after a fresh install or
    a cleared cache downloads and parses each body's index, which runs well
    past the soft deadline. Such a call returns a job handle to poll with
    ``get_job_result`` rather than the result itself.

    A ``warning`` beside a null ``record`` means the source never answered, so
    the standard may well exist and the canonical form is still usable. Only a
    null ``record`` with no ``warning`` means the sources looked and found
    nothing.

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
    cached_canonical = await service.cache.get_standard_alias(raw)
    if cached_canonical is not None:
        cached_record = await service.cache.get_standard(cached_canonical)
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
        record, failures = await service.standards.get_with_failures(canonical)
        if record is not None:
            await service.cache.set_standard_alias(raw, canonical)
            await service.cache.set_standard(canonical, record)
            return {"canonical": canonical, "body": body, "record": record}
        if failures:
            # The identifier resolved, but nobody could say whether it exists.
            # A bare null record here reads as "no such standard".
            return {
                "canonical": canonical,
                "body": body,
                "record": None,
                "warning": _failure_warning(failures),
            }
        return {"canonical": canonical, "body": body, "record": None}

    # 3. API fallback — search all sources
    candidates = await service.standards.resolve(raw)
    if not candidates:
        return {"canonical": None, "body": None, "record": None}
    if len(candidates) == 1:
        record = candidates[0]
        canonical = record.get("identifier", "")
        body = record.get("body", "")
        await service.cache.set_standard_alias(raw, canonical)
        await service.cache.set_standard(canonical, record)
        return {"canonical": canonical, "body": body, "record": record}

    return {"ambiguous": True, "candidates": candidates}


async def search_standards(
    query: str,
    body: str | None = None,
    limit: int = 10,
    service: Service = Depends(get_service),
) -> dict[str, Any]:
    """Search technical standards by identifier, title, or free text.

    Searches NIST, IETF, W3C, and ETSI. Use ``body`` to restrict to one
    source body.

    A cold catalogue makes this slow: the first call after a fresh install or
    a cleared cache downloads and parses each body's index, which runs well
    past the soft deadline. Such a call returns a job handle to poll with
    ``get_job_result`` rather than the result itself.

    Every answer states its own completeness. ``partial`` is always present,
    and when it is true ``failed_bodies`` names each source that did not
    answer and ``warning`` describes it. A partial answer is deliberately not
    an ``error``: the results that did arrive are usable, and the named bodies
    may still hold matches worth asking for again.

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

    cached = await service.cache.get_standards_search(cache_key)
    if cached is not None:
        logger.debug("standards_search_cache_hit key=%s", cache_key[:16])
        # Only complete answers are cached, so a hit is complete by
        # construction. The keys are still stated: a caller can rely on them
        # being present rather than inferring completeness from their absence.
        return {"results": cached, "partial": False, "failed_bodies": []}

    results, failures = await service.standards.search_with_failures(
        query, body=body, limit=limit
    )
    if not failures:
        await service.cache.set_standards_search(cache_key, results)
        return {"results": results, "partial": False, "failed_bodies": []}

    # A partial result is never cached: stored without its flag, the next call
    # would read it as a complete answer.
    logger.warning(
        "standards_search_partial query=%s bodies=%s",
        query,
        [f.body for f in failures],
    )
    return {
        "results": results,
        "partial": True,
        "failed_bodies": [f.body for f in failures],
        "warning": _failure_warning(failures),
    }


async def get_standard(
    identifier: str,
    fetch_full_text: bool = False,
    text_offset: int = 0,
    max_chars: int | None = DEFAULT_MAX_TEXT_CHARS,
    service: Service = Depends(get_service),
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

    NIST SP and NISTIR publications are catalogued per revision, so an
    identifier with no revision, such as ``NIST SP 800-53``, can come back
    ``not_found`` even though the publication exists. ``search_standards``
    lists the revisions that are published.

    ``not_found`` means the source answered and holds no such standard: stop
    asking about that identifier. A lookup that never got an answer says so
    instead, as ``rate_limited`` (with ``retryable``) or ``upstream_error``
    with the status and what went wrong. Both are worth retrying -- the
    standard may well exist.

    Full text is returned in pages of at most 20,000 characters. When
    ``next_offset`` is present, call this tool again with that value as
    ``text_offset``; the cached conversion makes later pages inexpensive.
    Set ``max_chars`` to null only when the client can accept the complete
    document in one response.

    Examples:
        get_standard("RFC 9000")
        get_standard("NIST SP 800-53 Rev. 5")
        get_standard("rfc9000")
        get_standard("WCAG 2.1", fetch_full_text=True)

    Args:
        identifier: Canonical or fuzzy standard identifier.
        fetch_full_text: If True and docling is configured, download and
            convert the full text PDF/HTML via docling.
        text_offset: Character offset at which the full-text page starts.
        max_chars: Maximum full-text characters to return, capped at 20,000.
            Pass ``null`` for the complete text.

    Returns:
        The StandardRecord, or ``{"error": "not_found"}`` if unresolvable.
        With ``fetch_full_text=True``, either ``full_text`` or
        ``full_text_error`` is present.
    """
    identifier = identifier.strip()

    # 1. Resolve identifier to canonical form (alias cache → regex → passthrough)
    cached_canonical = await service.cache.get_standard_alias(identifier)
    if cached_canonical is not None:
        canonical = cached_canonical
    else:
        resolved = resolve_identifier_local(identifier)
        canonical = resolved[0] if resolved else identifier

    # 2. Check cache
    cached = await service.cache.get_standard(canonical)
    if cached is not None:
        logger.debug("standard_cache_hit identifier=%s", canonical)
        if fetch_full_text:
            result = await _handle_full_text(cached, service)
        else:
            result = dict(cached)
        return page_text(
            result,
            "full_text",
            text_offset=text_offset,
            max_chars=max_chars,
        )

    # 3. Fetch from source
    record, failures = await service.standards.get_with_failures(canonical)
    if record is None:
        # Nothing is cached on this path, so the retry the payload invites is
        # not served a poisoned entry.
        if failures:
            return _upstream_error_payload(failures, identifier)
        return {"error": "not_found", "identifier": identifier}

    # 4. Cache result
    await service.cache.set_standard(canonical, record)
    if cached_canonical is None:
        await service.cache.set_standard_alias(identifier, canonical)

    if fetch_full_text:
        result = await _handle_full_text(record, service)
    else:
        result = dict(record)
    return page_text(
        result,
        "full_text",
        text_offset=text_offset,
        max_chars=max_chars,
    )


async def get_sync_status(
    service: Service = Depends(get_service),
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
    runs = await service.cache.list_sync_runs()
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
    service: Service,
) -> dict[str, Any]:
    """Download and convert full text via docling if available.

    If docling is not configured, no full_text_url is present, full_text is
    already populated, or the download fails, returns the record as-is so the
    caller can use full_text_url to fetch manually.

    Args:
        record: StandardRecord dict.
        service: Domain service with an optional docling client.

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

    if service.docling is None:
        logger.debug(
            "full_text_requested_but_docling_not_configured id=%s",
            record.get("identifier"),
        )
        return dict(record)

    url: str = record["full_text_url"] or ""
    filename = url.rsplit("/", 1)[-1] or "standard.pdf"

    try:
        content = await service.standards.download(url)
        markdown = await service.docling.convert(content, filename)
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
            await service.cache.set_standard(identifier, enriched)  # type: ignore[arg-type]
        except Exception as exc:
            # The conversion succeeded and the markdown is in hand; a cache
            # write that fails must not throw it away.
            logger.warning("standard_cache_write_failed id=%s err=%s", identifier, exc)
    return enriched
