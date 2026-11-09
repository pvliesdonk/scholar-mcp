"""PDF download and conversion MCP tools."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import socket
import uuid
from contextlib import aclosing
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx
from fastmcp import Context, FastMCP
from fastmcp.dependencies import CurrentContext, Depends
from fastmcp.exceptions import ToolError
from fastmcp_pvl_core import register_long_running_tool

from ._access_links import build_access_links, parse_access_link_templates
from ._docling_client import DoclingClient
from ._paper_cache import resolve_paper
from ._pdf_url_resolver import ResolvedPdf, iter_alternative_pdfs
from ._s2_client import s2_error_payload
from ._s2_jobs import register_s2_tool
from ._server_deps import get_service
from ._text_window import DEFAULT_MAX_TEXT_CHARS, page_text
from ._url_guard import BlockedDestinationError, get_public
from .domain import Service

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fastmcp_pvl_core import Jobs, JobsConfig

    from ._record_types import PaperRecord

logger = logging.getLogger(__name__)
_PDF_HEADER = b"%PDF-"
_ACCESS_LINKS_NOTE = (
    "This server could not fetch the PDF. access_links lead to the paper "
    "where the user's own licence access may apply: offer them to the user, "
    "or open one yourself if you can browse the web from the user's network."
)


def _pdf_cache_identity(file_stat: os.stat_result) -> tuple[int, int, int, int, int]:
    """Return fields that change when a cache file is replaced or rewritten."""
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


def _cached_pdf_is_valid(path: Path) -> bool:
    """Accept a cache hit only when its file begins with the PDF header."""
    try:
        with path.open("rb") as cached_pdf:
            opened = os.fstat(cached_pdf.fileno())
            has_header = cached_pdf.read(len(_PDF_HEADER)) == _PDF_HEADER
        current = path.stat()
    except FileNotFoundError:
        return False

    return _pdf_cache_identity(opened) == _pdf_cache_identity(current) and has_header


def _pdf_identity(path: Path) -> tuple[int, int, int, int, int] | None:
    """Return *path*'s cache identity, or ``None`` when it does not exist."""
    try:
        return _pdf_cache_identity(path.stat())
    except FileNotFoundError:
        return None


async def _cache_markdown(
    md_path: Path,
    markdown: str,
    pdf_path: Path,
    identity: tuple[int, int, int, int, int] | None,
) -> None:
    """Cache *markdown* unless *pdf_path* changed while it was converted.

    ``create_upload_link(replace=true)`` deletes a paper's PDF and Markdown
    (#546). A conversion already running would otherwise write the old
    document's text afterwards, and it would be served for the right PDF.

    Args:
        md_path: Where the Markdown is cached.
        markdown: The converted text.
        pdf_path: The PDF it was converted from.
        identity: ``_pdf_identity(pdf_path)`` taken before the PDF was read.
    """
    if await asyncio.to_thread(_pdf_identity, pdf_path) != identity:
        logger.info("md_cache_skipped reason=pdf_changed path=%s", pdf_path)
        return
    await asyncio.to_thread(md_path.write_text, markdown, encoding="utf-8")


def _write_pdf_cache(path: Path, content: bytes) -> None:
    """Publish a verified download atomically so readers never see partial bytes."""
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_bytes(content)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _with_access_links(
    service: Service, paper: PaperRecord, payload: dict[str, Any]
) -> dict[str, Any]:
    """Add the operator's access links to a no-PDF payload, when any apply.

    Args:
        service: Domain service, for the configured link templates.
        paper: The paper whose PDF could not be fetched.
        payload: The error payload to extend.

    Returns:
        ``payload``, with ``access_links`` and a ``note`` when at least one
        configured template could be filled for this paper.
    """
    templates = parse_access_link_templates(service.config.access_links)
    links = build_access_links(paper, templates)
    if links:
        payload["access_links"] = links
        payload["note"] = _ACCESS_LINKS_NOTE
    return payload


def _vlm_extras(docling: DoclingClient, use_vlm: bool) -> dict[str, Any]:
    """Return the ``vlm_skip_reason`` key when docling reports one.

    Spread into a result dict so the key is present only when there is a
    reason, which is the shape callers already expect.

    Args:
        docling: The configured docling client.
        use_vlm: Whether the caller asked for VLM enrichment.

    Returns:
        A single-key mapping, or an empty one when there is nothing to report.
    """
    reason = docling.vlm_skip_reason(use_vlm)
    return {"vlm_skip_reason": reason} if reason else {}


async def _pdf_candidates(
    service: Service, paper: PaperRecord, http_client: httpx.AsyncClient
) -> AsyncGenerator[ResolvedPdf, None]:
    """Yield a paper's PDF URLs in trial order, each URL once.

    The Semantic Scholar open-access URL comes first, then the alternative
    sources. Alternatives are resolved lazily, so a working first URL costs
    no Unpaywall lookup.

    Args:
        service: Domain service, for the Unpaywall contact email.
        paper: The resolved Semantic Scholar paper record.
        http_client: Client shared with the downloads, for Unpaywall.

    Yields:
        Each distinct candidate URL with its source.
    """
    seen: set[str] = set()
    oa_url: str | None = (paper.get("openAccessPdf") or {}).get("url")
    if oa_url:
        seen.add(oa_url)
        yield ResolvedPdf(url=oa_url, source="s2_oa")
    async for alt in iter_alternative_pdfs(
        paper, contact_email=service.config.contact_email, http_client=http_client
    ):
        if alt.url not in seen:
            seen.add(alt.url)
            yield alt


async def _get(
    client: httpx.AsyncClient, url: str, *, allow_private: bool
) -> httpx.Response:
    """GET ``url``, following redirects, through the public-destination guard.

    Args:
        client: The HTTP client to download with.
        url: The URL to fetch.
        allow_private: The operator's ``pdf_fetch_allow_private`` setting;
            when true, any destination is fetched without the check.

    Returns:
        The final response, whatever its status.

    Raises:
        BlockedDestinationError: The URL or a redirect hop resolves to a
            non-public address.
        httpx.HTTPError: The request failed.
        socket.gaierror: A host does not resolve.
    """
    if allow_private:
        return await client.get(url, follow_redirects=True)
    return await get_public(client, url)


async def _download_pdf(
    client: httpx.AsyncClient, candidate: ResolvedPdf, *, allow_private: bool
) -> bytes | dict[str, Any]:
    """Download one candidate and check that it is a PDF.

    Candidate URLs come from upstream metadata, so a candidate that resolves
    to a non-public address is refused like a caller-chosen URL (#573), and
    the next candidate is tried.

    Args:
        client: The HTTP client to download with.
        candidate: The URL to fetch and the source it came from.
        allow_private: The operator's ``pdf_fetch_allow_private`` setting.

    Returns:
        The PDF bytes, or an attempt record naming the source, the URL and
        why it yielded no PDF (``download_failed`` or ``not_pdf``).
    """
    attempt: dict[str, Any] = {"source": candidate.source, "url": candidate.url}
    try:
        r = await _get(client, candidate.url, allow_private=allow_private)
        r.raise_for_status()
    except BlockedDestinationError as exc:
        logger.info(
            "pdf_candidate_blocked source=%s url=%s target=%s address=%s",
            candidate.source,
            candidate.url,
            exc.url,
            exc.address,
        )
        return {
            **attempt,
            "error": "download_failed",
            "detail": (
                f"Refused: '{exc.url}' does not point to a public internet "
                "address, and this server downloads only from public hosts."
            ),
        }
    except (httpx.HTTPError, socket.gaierror) as exc:
        return {**attempt, "error": "download_failed", "detail": str(exc)}
    if not r.content.startswith(_PDF_HEADER):
        return {
            **attempt,
            "error": "not_pdf",
            "detail": "Downloaded content does not begin with the PDF header %PDF-.",
        }
    return r.content


def _paper_pdf_stem(paper: PaperRecord, identifier: str) -> str:
    """Return the file stem a paper's PDF is cached under.

    Args:
        paper: The resolved Semantic Scholar paper record.
        identifier: The caller's identifier, used when the record carries
            no ``paperId``.

    Returns:
        The ``paperId``, or the identifier with ``/`` replaced by ``_``.
    """
    return paper.get("paperId", identifier.replace("/", "_"))


async def _ensure_paper_pdf(
    service: Service, paper: PaperRecord, identifier: str
) -> tuple[Path, str] | dict[str, Any]:
    """Resolve a paper's PDF URL and make sure the file is on disk.

    Shared by ``fetch_paper_pdf`` and ``fetch_and_convert``, which resolve and
    download identically and differ only in what they do afterwards. Tries
    the Semantic Scholar open-access URL, then each alternative source, and
    stops at the first response that is a PDF.

    Args:
        service: Domain service, for the cache directory and contact email.
        paper: The resolved Semantic Scholar paper record.
        identifier: The caller's identifier, used to name the file when the
            record carries no ``paperId``.

    Returns:
        ``(path, source)`` once the PDF is on disk, or an error mapping when
        no URL resolved or no candidate yielded a PDF. A PDF already in the
        cache reports source ``"cache"``; it is checked before any source is
        resolved, so a closed-access paper whose PDF was uploaded (#546) is
        found too. A failure after one or more downloads reports the last
        source tried in ``error`` and ``pdf_source``, and every source in
        ``attempts``.
    """
    pdf_dir = service.config.cache_dir / "pdfs"
    path = pdf_dir / f"{_paper_pdf_stem(paper, identifier)}.pdf"
    if await asyncio.to_thread(_cached_pdf_is_valid, path):
        logger.info("pdf_already_exists path=%s", path)
        return path, "cache"
    attempts: list[dict[str, Any]] = []
    async with (
        httpx.AsyncClient(timeout=120.0) as client,
        aclosing(_pdf_candidates(service, paper, client)) as candidates,
    ):
        async for candidate in candidates:
            outcome = await _download_pdf(
                client,
                candidate,
                allow_private=service.config.pdf_fetch_allow_private,
            )
            if isinstance(outcome, bytes):
                pdf_dir.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(_write_pdf_cache, path, outcome)
                logger.info(
                    "pdf_downloaded path=%s bytes=%d source=%s attempts=%d",
                    path,
                    len(outcome),
                    candidate.source,
                    len(attempts) + 1,
                )
                return path, candidate.source
            attempts.append(outcome)
    return _with_access_links(service, paper, _no_pdf_payload(paper, attempts))


def _no_pdf_payload(
    paper: PaperRecord, attempts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build the error mapping for a paper whose PDF could not be obtained.

    Args:
        paper: The resolved Semantic Scholar paper record.
        attempts: One record per candidate tried, in order; empty when no
            candidate URL was known.

    Returns:
        ``no_oa_pdf`` when nothing was tried; otherwise the last attempt's
        ``error``, ``detail`` and ``pdf_source``, plus every attempt.
    """
    if not attempts:
        return {
            "error": "no_oa_pdf",
            "paper_id": paper.get("paperId"),
            "title": paper.get("title"),
        }
    last = attempts[-1]
    return {
        "error": last["error"],
        "detail": last["detail"],
        "pdf_source": last["source"],
        "attempts": attempts,
    }


async def fetch_paper_pdf(
    identifier: str,
    service: Service = Depends(get_service),
) -> dict[str, Any]:
    """Download the PDF of a paper.

    Tries the Semantic Scholar open-access URL first. When that is
    missing, fails or serves something other than a PDF, it tries
    alternative sources, one after another: ArXiv (from ``externalIds``), PubMed
    Central, and Unpaywall (by DOI, requires ``SCHOLAR_MCP_CONTACT_EMAIL``).
    A failure lists every source tried under ``attempts``.

    Skips download if the file already exists locally, which answers
    immediately; a fresh download usually takes 10-30 seconds and may
    be returned as a background job handle instead.

    Args:
        identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).

    Returns:
        ``{"path": "...", "source": "..."}`` on success, or a
        structured error dict. The ``source`` field indicates where the
        PDF was obtained (``s2_oa``, ``arxiv``, ``pmc``, ``unpaywall``).
    """
    try:
        paper = await resolve_paper(service.cache, service.s2.get_paper, identifier)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"error": "not_found", "identifier": identifier}
        return s2_error_payload(exc)

    fetched = await _ensure_paper_pdf(service, paper, identifier)
    if isinstance(fetched, dict):
        return fetched
    path, source = fetched
    return {"path": str(path), "source": source}


async def convert_pdf_to_markdown(
    file_path: str,
    use_vlm: bool = False,
    text_offset: int = 0,
    max_chars: int | None = DEFAULT_MAX_TEXT_CHARS,
    service: Service = Depends(get_service),
) -> dict[str, Any]:
    """Convert a local PDF to Markdown using docling-serve.

    Works on any local PDF, including manually placed paywalled papers.
    Returns an error if the server does not have PDF conversion configured.

    Conversion typically takes 1-5 minutes depending on page count, so
    expect a background job handle rather than an inline result; a
    previously converted file is served from cache immediately.

    Tip: start with ``use_vlm=false`` (the default). Standard conversion
    handles most papers well. Only retry with ``use_vlm=true`` when the
    result has garbled formulas or missing figure descriptions.

    VLM and standard results are cached separately (``<stem>.md`` vs
    ``<stem>_vlm.md``), so switching modes never overwrites a previous
    conversion. When VLM is requested but not configured, the response
    includes a ``vlm_skip_reason`` field explaining why.

    Markdown is returned in pages of at most 20,000 characters. When
    ``next_offset`` is present, call this tool again with that value as
    ``text_offset``; the cached conversion makes later pages inexpensive.
    Set ``max_chars`` to null only when the client can accept the complete
    document in one response.

    Args:
        file_path: Absolute path to the local PDF file.
        use_vlm: Use VLM enrichment for formulas and figures.
            Falls back to standard conversion if VLM is not configured
            and reports the reason in ``vlm_skip_reason``.
        text_offset: Character offset at which the Markdown page starts.
        max_chars: Maximum Markdown characters to return, capped at 20,000.
            Pass ``null`` for the complete text.

    Returns:
        ``{"markdown": "...", "path": "...", "vlm_used": bool}``.
    """
    docling = service.docling
    if docling is None:
        return {"error": "docling_not_configured"}

    path = Path(file_path)
    if not path.exists():
        return {"error": "file_not_found", "path": file_path}

    # VLM and standard conversions use separate cache files.
    md_dir = service.config.cache_dir / "md"
    vlm_suffix = "_vlm" if use_vlm and docling.vlm_available else ""
    md_path = md_dir / f"{path.stem}{vlm_suffix}.md"
    if md_path.exists():
        cached = await asyncio.to_thread(md_path.read_text, encoding="utf-8")
        return page_text(
            {
                "markdown": cached,
                "path": str(md_path),
                "vlm_used": bool(vlm_suffix),
                **_vlm_extras(docling, use_vlm),
            },
            "markdown",
            text_offset=text_offset,
            max_chars=max_chars,
        )

    identity = await asyncio.to_thread(_pdf_identity, path)
    pdf_bytes = await asyncio.to_thread(path.read_bytes)
    try:
        markdown = await docling.convert(pdf_bytes, path.name, use_vlm=use_vlm)
    except Exception as exc:
        logger.exception("docling_convert_failed path=%s", file_path)
        return {"error": "docling_error", "detail": str(exc)}

    md_dir.mkdir(parents=True, exist_ok=True)
    await _cache_markdown(md_path, markdown, path, identity)
    return page_text(
        {
            "markdown": markdown,
            "path": str(md_path),
            "vlm_used": use_vlm and docling.vlm_available,
            **_vlm_extras(docling, use_vlm),
        },
        "markdown",
        text_offset=text_offset,
        max_chars=max_chars,
    )


async def _upload_hint(
    ctx: Context, service: Service, identifier: str
) -> dict[str, str]:
    """Point a failed fetch at create_upload_link, when this server offers it.

    The tool is registered only on an HTTP deployment with a public URL, and
    an operator can hide it; ``get_tool`` returns ``None`` for a hidden tool,
    so the hint never names a tool the model cannot call.
    """
    from ._tools_upload import UPLOAD_TOOL  # imports this module

    # The tool refuses without docling, so naming it then is a dead end.
    if service.docling is None or await ctx.fastmcp.get_tool(UPLOAD_TOOL) is None:
        return {}
    return {
        "upload": (
            f"If the user can download this PDF, call {UPLOAD_TOOL} with "
            f"identifier '{identifier}', send the file to the returned url, "
            "then call fetch_and_convert again."
        )
    }


async def fetch_and_convert(
    identifier: str,
    use_vlm: bool = False,
    text_offset: int = 0,
    max_chars: int | None = DEFAULT_MAX_TEXT_CHARS,
    service: Service = Depends(get_service),
    ctx: Context = CurrentContext(),
) -> dict[str, Any]:
    """Resolve a paper, download its PDF, and convert to Markdown.

    Tries the Semantic Scholar open-access URL first, then alternative
    sources (ArXiv, PubMed Central, Unpaywall) until one serves a PDF;
    a failure lists every source tried under ``attempts``. Each stage fails
    gracefully: metadata is always returned if the paper resolves,
    even if PDF download or conversion fails.

    The full pipeline typically takes 1-5 minutes, so expect a
    background job handle rather than an inline result.

    Tip: start with ``use_vlm=false`` (the default). Standard conversion
    handles most papers well. Only retry with ``use_vlm=true`` when the
    result has garbled formulas or missing figure descriptions.

    VLM and standard results are cached separately (``<id>.md`` vs
    ``<id>_vlm.md``), so switching modes never overwrites a previous
    conversion. When VLM is requested but not configured, the response
    includes a ``vlm_skip_reason`` field explaining why.

    Markdown is returned in pages of at most 20,000 characters. When
    ``next_offset`` is present, call this tool again with that value as
    ``text_offset``; the cached conversion makes later pages inexpensive.
    Set ``max_chars`` to null only when the client can accept the complete
    document in one response.

    Args:
        identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).
        use_vlm: Use VLM enrichment for formula/figure extraction.
            Falls back to standard conversion if VLM is not configured
            and reports the reason in ``vlm_skip_reason``.
        text_offset: Character offset at which the Markdown page starts.
        max_chars: Maximum Markdown characters to return, capped at 20,000.
            Pass ``null`` for the complete text.

    Returns:
        ``metadata`` and ``markdown`` on full success, or ``metadata``
        plus an ``error`` key if a stage fails.
    """
    try:
        paper = await resolve_paper(service.cache, service.s2.get_paper, identifier)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"error": "not_found", "identifier": identifier}
        return s2_error_payload(exc)

    fetched = await _ensure_paper_pdf(service, paper, identifier)
    if isinstance(fetched, dict):
        return {
            "metadata": paper,
            **fetched,
            **await _upload_hint(ctx, service, identifier),
        }
    pdf_path, pdf_source = fetched

    docling = service.docling
    if docling is None:
        return {
            "metadata": paper,
            "pdf_path": str(pdf_path),
            "error": "docling_not_configured",
        }

    vlm_used = use_vlm and docling.vlm_available
    md_dir = service.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    # The PDF is named for the paper id, so its stem is that id.
    md_path = md_dir / f"{pdf_path.stem}{'_vlm' if vlm_used else ''}.md"

    if md_path.exists():
        markdown = await asyncio.to_thread(md_path.read_text, encoding="utf-8")
        logger.debug("md_cache_hit path=%s", md_path)
    else:
        try:
            identity = await asyncio.to_thread(_pdf_identity, pdf_path)
            pdf_bytes_for_convert = await asyncio.to_thread(pdf_path.read_bytes)
            markdown = await docling.convert(
                pdf_bytes_for_convert, pdf_path.name, use_vlm=use_vlm
            )
        except Exception as exc:
            logger.exception("docling_convert_failed path=%s", pdf_path)
            return {
                "metadata": paper,
                "pdf_path": str(pdf_path),
                "error": "conversion_failed",
                "detail": str(exc),
            }
        await _cache_markdown(md_path, markdown, pdf_path, identity)

    return page_text(
        {
            "metadata": paper,
            "markdown": markdown,
            "pdf_path": str(pdf_path),
            "md_path": str(md_path),
            "pdf_source": pdf_source,
            "vlm_used": vlm_used,
            **_vlm_extras(docling, use_vlm),
        },
        "markdown",
        text_offset=text_offset,
        max_chars=max_chars,
    )


async def _get_caller_url(url: str, *, allow_private: bool) -> httpx.Response:
    """Download a caller-chosen URL, refusing non-public destinations.

    Args:
        url: The URL the caller passed to ``fetch_pdf_by_url``.
        allow_private: The operator's ``pdf_fetch_allow_private`` setting;
            when true, any destination is fetched, as before #514.

    Returns:
        The final response, with a success status.

    Raises:
        ToolError: The URL or a redirect hop resolves to a non-public
            address (outcome 2: the caller must pass another URL).
        httpx.HTTPError: The download failed or returned an error status.
        socket.gaierror: A host does not resolve.
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            r = await _get(client, url, allow_private=allow_private)
        except BlockedDestinationError as exc:
            logger.info(
                "pdf_by_url_blocked url=%s target=%s address=%s",
                url,
                exc.url,
                exc.address,
            )
            hop = "" if exc.url == url else f" redirects to '{exc.url}', which"
            raise ToolError(
                f"url '{url}'{hop} does not point to a public internet "
                "address, and this server downloads only from public "
                "hosts. Pass fetch_pdf_by_url a publicly reachable url "
                "for the PDF instead.",
                log_level=logging.INFO,
            ) from None
        r.raise_for_status()
    return r


async def fetch_pdf_by_url(
    url: str,
    filename: str | None = None,
    use_vlm: bool = False,
    text_offset: int = 0,
    max_chars: int | None = DEFAULT_MAX_TEXT_CHARS,
    service: Service = Depends(get_service),
) -> dict[str, Any]:
    """Download a PDF from a URL and optionally convert to Markdown.

    Use this when you have found an alternative PDF link (such as one
    on an author's homepage, a preprint server, or an institutional repository)
    that is not listed in Semantic Scholar's openAccessPdf field.

    The PDF is saved locally and, if docling-serve is configured,
    converted to Markdown automatically. Conversion typically takes 1-5
    minutes and is returned as a background job handle. An already
    downloaded and converted URL answers immediately.

    Markdown is returned in pages of at most 20,000 characters. When
    ``next_offset`` is present, call this tool again with that value as
    ``text_offset``; the cached conversion makes later pages inexpensive.
    Set ``max_chars`` to null only when the client can accept the complete
    document in one response.

    Args:
        url: Direct URL to a PDF file.
        filename: Optional filename stem for caching (such as
            ``"smith2024_attention"``). Derived from the URL if omitted.
        use_vlm: Use VLM enrichment for formulas and figures.
        text_offset: Character offset at which the Markdown page starts.
        max_chars: Maximum Markdown characters to return, capped at 20,000.
            Pass ``null`` for the complete text.

    Returns:
        ``pdf_path`` and optionally ``markdown`` / ``md_path``.
    """
    # Intercept authenticated service URLs that need special handling
    netloc = urlparse(url).netloc
    if netloc == "ops.epo.org" or netloc.endswith(".ops.epo.org"):
        return {
            "error": "use_fetch_patent_pdf",
            "detail": (
                "EPO OPS URLs require authenticated access. "
                "Use the fetch_patent_pdf tool instead, passing the patent number "
                "(e.g. fetch_patent_pdf('EP3491801B1'))."
            ),
        }

    # Derive a safe filename stem.  When no explicit filename is
    # given, incorporate a short URL hash to avoid collisions when
    # different URLs share the same path component.
    if filename:
        stem = re.sub(r"[^\w\-]", "_", filename)
    else:
        path_part = urlparse(url).path.rsplit("/", 1)[-1]
        base = re.sub(r"[^\w\-]", "_", Path(path_part).stem or "download")
        stem = f"{base}_{hashlib.sha256(url.encode()).hexdigest()[:8]}"

    pdf_dir = service.config.cache_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"{stem}.pdf"

    if not await asyncio.to_thread(_cached_pdf_is_valid, pdf_path):
        try:
            r = await _get_caller_url(
                url, allow_private=service.config.pdf_fetch_allow_private
            )
        except (httpx.HTTPError, socket.gaierror) as exc:
            return {"error": "download_failed", "detail": str(exc)}
        if not r.content.startswith(_PDF_HEADER):
            return {
                "error": "not_pdf",
                "detail": "Downloaded content does not begin with the PDF header %PDF-.",
            }
        await asyncio.to_thread(_write_pdf_cache, pdf_path, r.content)
        logger.info("pdf_by_url_downloaded path=%s bytes=%d", pdf_path, len(r.content))
    else:
        logger.info("pdf_by_url_cached path=%s", pdf_path)

    docling = service.docling
    if docling is None:
        return {"pdf_path": str(pdf_path)}

    vlm_suffix = "_vlm" if use_vlm and docling.vlm_available else ""
    md_dir = service.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / f"{stem}{vlm_suffix}.md"

    if md_path.exists():
        markdown = await asyncio.to_thread(md_path.read_text, encoding="utf-8")
    else:
        try:
            identity = await asyncio.to_thread(_pdf_identity, pdf_path)
            pdf_bytes = await asyncio.to_thread(pdf_path.read_bytes)
            markdown = await docling.convert(pdf_bytes, pdf_path.name, use_vlm=use_vlm)
        except Exception as exc:
            logger.exception("docling_convert_failed path=%s", pdf_path)
            return {
                "pdf_path": str(pdf_path),
                "error": "conversion_failed",
                "detail": str(exc),
            }
        await _cache_markdown(md_path, markdown, pdf_path, identity)

    return page_text(
        {
            "pdf_path": str(pdf_path),
            "markdown": markdown,
            "md_path": str(md_path),
            "vlm_used": bool(vlm_suffix),
            **_vlm_extras(docling, use_vlm),
        },
        "markdown",
        text_offset=text_offset,
        max_chars=max_chars,
    )


# The reference page these tools are listed on (scripts/gen_reference.py).
_GROUP = "group:full-text"


def register_pdf_tools(
    mcp: FastMCP, jobs: Jobs, jobs_config: JobsConfig | None = None
) -> None:
    """Register the PDF tools on *mcp*.

    Each tool is a module-level coroutine registered through the jobs layer.
    A call that finishes within
    ``SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S`` returns its result inline and a
    slower one is promoted to a background job the caller polls with
    ``get_job_result``.  A cache hit therefore answers directly; only real
    downloads and conversions promote.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared jobs mechanics for this server.
    """
    register_s2_tool(
        mcp,
        jobs,
        jobs_config=jobs_config,
        tags={_GROUP, "write"},
        annotations={
            "title": "Fetch Paper PDF",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(fetch_paper_pdf)
    register_long_running_tool(
        mcp,
        jobs,
        tags={_GROUP, "write"},
        annotations={
            "title": "Convert PDF to Markdown",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(convert_pdf_to_markdown)
    register_s2_tool(
        mcp,
        jobs,
        jobs_config=jobs_config,
        tags={_GROUP, "write"},
        annotations={
            "title": "Fetch and Convert Paper",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(fetch_and_convert)
    register_long_running_tool(
        mcp,
        jobs,
        tags={_GROUP, "write"},
        annotations={
            "title": "Fetch PDF by URL",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(fetch_pdf_by_url)
