"""PDF download and conversion MCP tools."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import register_long_running_tool

from ._docling_client import DoclingClient
from ._pdf_url_resolver import ResolvedPdf, resolve_alternative_pdf
from ._s2_client import s2_error_payload
from ._server_deps import ServiceBundle, get_bundle

if TYPE_CHECKING:
    from fastmcp_pvl_core import Jobs

    from ._record_types import PaperRecord

logger = logging.getLogger(__name__)

_PDF_FIELDS = "paperId,openAccessPdf,externalIds,title"


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


async def _ensure_paper_pdf(
    bundle: ServiceBundle, paper: PaperRecord, identifier: str
) -> tuple[Path, str] | dict[str, Any]:
    """Resolve a paper's PDF URL and make sure the file is on disk.

    Shared by ``fetch_paper_pdf`` and ``fetch_and_convert``, which resolve and
    download identically and differ only in what they do afterwards.

    Args:
        bundle: Service bundle, for the cache directory and contact email.
        paper: The resolved Semantic Scholar paper record.
        identifier: The caller's identifier, used to name the file when the
            record carries no ``paperId``.

    Returns:
        ``(path, source)`` once the PDF is on disk, or an error mapping when
        no open-access URL resolved or the download failed.
    """
    oa = paper.get("openAccessPdf") or {}
    url: str | None = oa.get("url")
    source = "s2_oa"
    if not url:
        alt: ResolvedPdf | None = await resolve_alternative_pdf(
            paper, contact_email=bundle.config.contact_email
        )
        if alt:
            url, source = alt.url, alt.source
    if not url:
        return {
            "error": "no_oa_pdf",
            "paper_id": paper.get("paperId"),
            "title": paper.get("title"),
        }

    pid = paper.get("paperId", identifier.replace("/", "_"))
    pdf_dir = bundle.config.cache_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    path = pdf_dir / f"{pid}.pdf"
    if path.exists():
        logger.info("pdf_already_exists path=%s", path)
        return path, source

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            r = await client.get(url, follow_redirects=True)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            return {
                "error": "download_failed",
                "detail": str(exc),
                "pdf_source": source,
            }
    await asyncio.to_thread(path.write_bytes, r.content)
    logger.info(
        "pdf_downloaded path=%s bytes=%d source=%s", path, len(r.content), source
    )
    return path, source


async def fetch_paper_pdf(
    identifier: str,
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Download the PDF of a paper.

    Tries the Semantic Scholar open-access URL first. When that is
    unavailable, automatically checks alternative sources: ArXiv
    (from externalIds), PubMed Central, and Unpaywall (by DOI,
    requires ``SCHOLAR_MCP_CONTACT_EMAIL``).

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
        paper = await bundle.s2.get_paper(identifier, fields=_PDF_FIELDS)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"error": "not_found", "identifier": identifier}
        return s2_error_payload(exc)

    fetched = await _ensure_paper_pdf(bundle, paper, identifier)
    if isinstance(fetched, dict):
        return fetched
    path, source = fetched
    return {"path": str(path), "source": source}


async def convert_pdf_to_markdown(
    file_path: str,
    use_vlm: bool = False,
    bundle: ServiceBundle = Depends(get_bundle),
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

    Args:
        file_path: Absolute path to the local PDF file.
        use_vlm: Use VLM enrichment for formulas and figures.
            Falls back to standard conversion if VLM is not configured
            and reports the reason in ``vlm_skip_reason``.

    Returns:
        ``{"markdown": "...", "path": "...", "vlm_used": bool}``.
    """
    docling = bundle.docling
    if docling is None:
        return {"error": "docling_not_configured"}

    path = Path(file_path)
    if not path.exists():
        return {"error": "file_not_found", "path": file_path}

    # VLM and standard conversions use separate cache files.
    md_dir = bundle.config.cache_dir / "md"
    vlm_suffix = "_vlm" if use_vlm and docling.vlm_available else ""
    md_path = md_dir / f"{path.stem}{vlm_suffix}.md"
    if md_path.exists():
        cached = await asyncio.to_thread(md_path.read_text, encoding="utf-8")
        return {
            "markdown": cached,
            "path": str(md_path),
            "vlm_used": bool(vlm_suffix),
            **_vlm_extras(docling, use_vlm),
        }

    pdf_bytes = await asyncio.to_thread(path.read_bytes)
    try:
        markdown = await docling.convert(pdf_bytes, path.name, use_vlm=use_vlm)
    except Exception as exc:
        logger.exception("docling_convert_failed path=%s", file_path)
        return {"error": "docling_error", "detail": str(exc)}

    md_dir.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(md_path.write_text, markdown, encoding="utf-8")
    return {
        "markdown": markdown,
        "path": str(md_path),
        "vlm_used": use_vlm and docling.vlm_available,
        **_vlm_extras(docling, use_vlm),
    }


async def fetch_and_convert(
    identifier: str,
    use_vlm: bool = False,
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Resolve a paper, download its PDF, and convert to Markdown.

    Tries the Semantic Scholar open-access URL first, then alternative
    sources (ArXiv, PubMed Central, Unpaywall). Each stage fails
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

    Args:
        identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).
        use_vlm: Use VLM enrichment for formula/figure extraction.
            Falls back to standard conversion if VLM is not configured
            and reports the reason in ``vlm_skip_reason``.

    Returns:
        ``metadata`` and ``markdown`` on full success, or ``metadata``
        plus an ``error`` key if a stage fails.
    """
    try:
        paper = await bundle.s2.get_paper(identifier)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"error": "not_found", "identifier": identifier}
        return s2_error_payload(exc)

    fetched = await _ensure_paper_pdf(bundle, paper, identifier)
    if isinstance(fetched, dict):
        return {"metadata": paper, **fetched}
    pdf_path, pdf_source = fetched

    docling = bundle.docling
    if docling is None:
        return {
            "metadata": paper,
            "pdf_path": str(pdf_path),
            "error": "docling_not_configured",
        }

    vlm_used = use_vlm and docling.vlm_available
    md_dir = bundle.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    # The PDF is named for the paper id, so its stem is that id.
    md_path = md_dir / f"{pdf_path.stem}{'_vlm' if vlm_used else ''}.md"

    if md_path.exists():
        markdown = await asyncio.to_thread(md_path.read_text, encoding="utf-8")
        logger.debug("md_cache_hit path=%s", md_path)
    else:
        try:
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
        await asyncio.to_thread(md_path.write_text, markdown, encoding="utf-8")

    return {
        "metadata": paper,
        "markdown": markdown,
        "pdf_path": str(pdf_path),
        "md_path": str(md_path),
        "pdf_source": pdf_source,
        "vlm_used": vlm_used,
        **_vlm_extras(docling, use_vlm),
    }


async def fetch_pdf_by_url(
    url: str,
    filename: str | None = None,
    use_vlm: bool = False,
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Download a PDF from a URL and optionally convert to Markdown.

    Use this when you have found an alternative PDF link (e.g. from an
    author's homepage, a preprint server, or an institutional repository)
    that is not listed in Semantic Scholar's openAccessPdf field.

    The PDF is saved locally and, if docling-serve is configured,
    converted to Markdown automatically — which typically takes 1-5
    minutes and is returned as a background job handle. An already
    downloaded and converted URL answers immediately.

    Args:
        url: Direct URL to a PDF file.
        filename: Optional filename stem for caching (e.g.
            ``"smith2024_attention"``). Derived from the URL if omitted.
        use_vlm: Use VLM enrichment for formulas and figures.

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

    pdf_dir = bundle.config.cache_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"{stem}.pdf"

    if not pdf_path.exists():
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                r = await client.get(url, follow_redirects=True)
                r.raise_for_status()
            except httpx.HTTPError as exc:
                return {"error": "download_failed", "detail": str(exc)}
        await asyncio.to_thread(pdf_path.write_bytes, r.content)
        logger.info("pdf_by_url_downloaded path=%s bytes=%d", pdf_path, len(r.content))
    else:
        logger.info("pdf_by_url_cached path=%s", pdf_path)

    docling = bundle.docling
    if docling is None:
        return {"pdf_path": str(pdf_path)}

    vlm_suffix = "_vlm" if use_vlm and docling.vlm_available else ""
    md_dir = bundle.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / f"{stem}{vlm_suffix}.md"

    if md_path.exists():
        markdown = await asyncio.to_thread(md_path.read_text, encoding="utf-8")
    else:
        try:
            pdf_bytes = await asyncio.to_thread(pdf_path.read_bytes)
            markdown = await docling.convert(pdf_bytes, pdf_path.name, use_vlm=use_vlm)
        except Exception as exc:
            logger.exception("docling_convert_failed path=%s", pdf_path)
            return {
                "pdf_path": str(pdf_path),
                "error": "conversion_failed",
                "detail": str(exc),
            }
        await asyncio.to_thread(md_path.write_text, markdown, encoding="utf-8")

    return {
        "pdf_path": str(pdf_path),
        "markdown": markdown,
        "md_path": str(md_path),
        "vlm_used": bool(vlm_suffix),
        **_vlm_extras(docling, use_vlm),
    }


def register_pdf_tools(mcp: FastMCP, jobs: Jobs) -> None:
    """Register the PDF tools on *mcp*.

    Each tool is a module-level coroutine registered through
    :func:`register_long_running_tool`, so a call that finishes within
    ``SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S`` returns its result inline and a
    slower one is promoted to a background job the caller polls with
    ``get_job_result``.  A cache hit therefore answers directly; only real
    downloads and conversions promote.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared jobs mechanics for this server.
    """
    register_long_running_tool(
        mcp,
        jobs,
        tags={"write"},
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
        tags={"write"},
        annotations={
            "title": "Convert PDF to Markdown",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(convert_pdf_to_markdown)
    register_long_running_tool(
        mcp,
        jobs,
        tags={"write"},
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
        tags={"write"},
        annotations={
            "title": "Fetch PDF by URL",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(fetch_pdf_by_url)
