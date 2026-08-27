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
from fastmcp_pvl_core import Jobs, register_long_running_tool

from ._pdf_markdown import download_to, markdown_fields
from ._pdf_url_resolver import ResolvedPdf, resolve_alternative_pdf
from ._s2_client import s2_error_payload
from ._server_deps import ServiceBundle, get_bundle

if TYPE_CHECKING:
    from ._record_types import PaperRecord

logger = logging.getLogger(__name__)


def register_pdf_tools(mcp: FastMCP, jobs: Jobs) -> None:
    """Register PDF tools on *mcp*.

    Every tool here downloads or converts a PDF, so all four are registered
    dual-mode: a run that finishes inside the jobs soft deadline returns its
    result inline, and one that does not is promoted to a background job the
    caller redeems through ``get_job_result``.

    Each tool has its own registration function — one long body per tool
    rather than one body holding all four.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared Jobs service backing the dual-mode registration.
    """
    _register_fetch_paper_pdf(mcp, jobs)
    _register_convert_pdf_to_markdown(mcp, jobs)
    _register_fetch_and_convert(mcp, jobs)
    _register_fetch_pdf_by_url(mcp, jobs)


async def _fetch_paper_or_error(
    bundle: ServiceBundle, identifier: str, *, fields: str | None = None
) -> tuple[PaperRecord | None, dict[str, Any] | None]:
    """Resolve *identifier* through Semantic Scholar.

    A 429 is retried inside the client rather than deferred: the calls that
    use this are already jobs, so a slow retry is promoted rather than lost.

    Args:
        bundle: Service bundle, for the S2 client.
        identifier: DOI, S2 paper ID, arXiv ID, and so on.
        fields: Comma-separated S2 field names; the client's default if unset.

    Returns:
        The paper record and ``None``, or ``None`` and a structured error.
    """
    try:
        if fields is None:
            paper = await bundle.s2.get_paper(identifier)
        else:
            paper = await bundle.s2.get_paper(identifier, fields=fields)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None, {"error": "not_found", "identifier": identifier}
        return None, s2_error_payload(exc)
    return paper, None


async def _download_paper_pdf(
    bundle: ServiceBundle,
    identifier: str,
    paper_data: PaperRecord,
    resolved: ResolvedPdf | None = None,
) -> dict[str, Any]:
    """Resolve a download URL for *paper_data* and fetch the PDF.

    Args:
        bundle: Service bundle, for the cache directory and contact email.
        identifier: The caller's paper identifier, the fallback filename stem.
        paper_data: Paper metadata carrying ``openAccessPdf`` / ``externalIds``.
        resolved: An already-resolved alternative source, so a caller that has
            already looked one up does not pay for a second Unpaywall call.

    Returns:
        ``{"path": ..., "source": ...}``, or a structured error mapping.
    """
    dl_url: str | None
    if resolved:
        dl_url = resolved.url
        pdf_source = resolved.source
    else:
        oa = paper_data.get("openAccessPdf") or {}
        dl_url = oa.get("url")
        pdf_source = "s2_oa"
        if not dl_url:
            alt = await resolve_alternative_pdf(
                paper_data,
                contact_email=bundle.config.contact_email,
            )
            if alt:
                dl_url = alt.url
                pdf_source = alt.source
    if not dl_url:
        return {
            "error": "no_oa_pdf",
            "paper_id": paper_data.get("paperId"),
            "title": paper_data.get("title"),
        }
    pid = paper_data.get("paperId", identifier.replace("/", "_"))
    dl_dir = bundle.config.cache_dir / "pdfs"
    dl_dir.mkdir(parents=True, exist_ok=True)
    dl_path = dl_dir / f"{pid}.pdf"
    if dl_path.exists():
        return {"path": str(dl_path), "source": pdf_source}
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            r = await client.get(dl_url, follow_redirects=True)
            r.raise_for_status()
        except httpx.HTTPError as dl_exc:
            return {"error": "download_failed", "detail": str(dl_exc)}
    await asyncio.to_thread(dl_path.write_bytes, r.content)
    logger.info(
        "pdf_downloaded path=%s bytes=%d source=%s",
        dl_path,
        len(r.content),
        pdf_source,
    )
    return {"path": str(dl_path), "source": pdf_source}


def _register_fetch_paper_pdf(mcp: FastMCP, jobs: Jobs) -> None:
    """Register the ``fetch_paper_pdf`` tool."""

    @register_long_running_tool(
        mcp,
        jobs,
        tags={"write"},
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def fetch_paper_pdf(
        identifier: str,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> dict[str, Any]:
        """Download the PDF of a paper.

        Tries the Semantic Scholar open-access URL first. When that is
        unavailable, automatically checks alternative sources: ArXiv
        (from externalIds), PubMed Central, and Unpaywall (by DOI,
        requires ``SCHOLAR_MCP_CONTACT_EMAIL``).

        Skips download if the file already exists locally. A download
        usually completes in 10-30 seconds.

        Args:
            identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).

        Returns:
            ``{"path": "...", "source": "..."}`` on success, or a structured
            error mapping. The ``source`` field indicates where the PDF was
            obtained (``s2_oa``, ``arxiv``, ``pmc``, ``unpaywall``).

            If the call outruns the jobs soft deadline it returns a job
            handle instead — poll ``get_job_result`` with its ``job_id``.
        """

        # Resolve metadata first so a locally cached PDF short-circuits the
        # download. A 429 here is retried inside the client rather than
        # deferred: this whole call is already a job, so a slow retry is
        # promoted rather than lost.
        paper, paper_error = await _fetch_paper_or_error(
            bundle, identifier, fields="paperId,openAccessPdf,externalIds,title"
        )
        if paper is None:
            return paper_error or {}

        oa_pdf = paper.get("openAccessPdf") or {}
        url = oa_pdf.get("url")
        alt: ResolvedPdf | None = None
        if not url:
            alt = await resolve_alternative_pdf(
                paper,
                contact_email=bundle.config.contact_email,
            )
            if not alt:
                return {
                    "error": "no_oa_pdf",
                    "paper_id": paper.get("paperId"),
                    "title": paper.get("title"),
                }

        paper_id = paper.get("paperId", identifier.replace("/", "_"))
        pdf_dir = bundle.config.cache_dir / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"{paper_id}.pdf"

        if pdf_path.exists():
            logger.info("pdf_already_exists path=%s", pdf_path)
            source = alt.source if alt else "s2_oa"
            return {"path": str(pdf_path), "source": source}

        # PDF not cached — download it, passing the resolved alt so
        # _download_paper_pdf does not repeat the Unpaywall lookup.
        return await _download_paper_pdf(bundle, identifier, paper, resolved=alt)


def _register_convert_pdf_to_markdown(mcp: FastMCP, jobs: Jobs) -> None:
    """Register the ``convert_pdf_to_markdown`` tool."""

    @register_long_running_tool(
        mcp,
        jobs,
        tags={"write"},
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def convert_pdf_to_markdown(
        file_path: str,
        use_vlm: bool = False,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> dict[str, Any]:
        """Convert a local PDF to Markdown using docling-serve.

        Works on any local PDF, including manually placed paywalled papers.
        Returns an error if the server does not have PDF conversion configured.
        Conversion typically takes 1-5 minutes depending on page count.

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
            If the call outruns the jobs soft deadline it returns a job
            handle instead — poll ``get_job_result`` with its ``job_id``.
        """
        if bundle.docling is None:
            return {"error": "docling_not_configured"}

        path = Path(file_path)
        if not path.exists():
            return {"error": "file_not_found", "path": file_path}

        # Return cached markdown if it already exists.
        # VLM and standard conversions use separate cache files.
        md_dir = bundle.config.cache_dir / "md"
        vlm_suffix = "_vlm" if use_vlm and bundle.docling.vlm_available else ""
        md_path = md_dir / f"{path.stem}{vlm_suffix}.md"
        if md_path.exists():
            markdown = await asyncio.to_thread(md_path.read_text, encoding="utf-8")
            result: dict[str, object] = {
                "markdown": markdown,
                "path": str(md_path),
                "vlm_used": bool(vlm_suffix),
            }
            skip_reason = bundle.docling.vlm_skip_reason(use_vlm)
            if skip_reason:
                result["vlm_skip_reason"] = skip_reason
            return result

        async def _execute() -> dict[str, Any]:
            pdf_bytes = await asyncio.to_thread(path.read_bytes)

            try:
                markdown = await bundle.docling.convert(  # type: ignore[union-attr]
                    pdf_bytes, path.name, use_vlm=use_vlm
                )
            except Exception as exc:
                logger.exception("docling_convert_failed path=%s", file_path)
                return {"error": "docling_error", "detail": str(exc)}

            vlm_used = use_vlm and bundle.docling.vlm_available  # type: ignore[union-attr]
            skip_reason = bundle.docling.vlm_skip_reason(use_vlm)  # type: ignore[union-attr]

            md_dir.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(md_path.write_text, markdown, encoding="utf-8")

            result: dict[str, object] = {
                "markdown": markdown,
                "path": str(md_path),
                "vlm_used": vlm_used,
            }
            if skip_reason:
                result["vlm_skip_reason"] = skip_reason
            return result

        return await _execute()


async def _resolve_pdf_source(
    bundle: ServiceBundle, paper: PaperRecord
) -> tuple[str | None, str]:
    """Pick the download URL for *paper*, falling back to alternative sources.

    Args:
        bundle: Service bundle, for the contact email Unpaywall needs.
        paper: Paper metadata carrying ``openAccessPdf`` / ``externalIds``.

    Returns:
        The URL (``None`` when nothing resolves) and the source label.
    """
    oa_pdf = paper.get("openAccessPdf") or {}
    url = oa_pdf.get("url")
    if url:
        return url, "s2_oa"
    alt = await resolve_alternative_pdf(
        paper, contact_email=bundle.config.contact_email
    )
    if alt:
        return alt.url, alt.source
    return None, "s2_oa"


def _register_fetch_and_convert(mcp: FastMCP, jobs: Jobs) -> None:
    """Register the ``fetch_and_convert`` tool."""

    @register_long_running_tool(
        mcp,
        jobs,
        tags={"write"},
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def fetch_and_convert(
        identifier: str,
        use_vlm: bool = False,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> dict[str, Any]:
        """Resolve a paper, download its PDF, and convert to Markdown.

        Tries the Semantic Scholar open-access URL first, then alternative
        sources (ArXiv, PubMed Central, Unpaywall). Each stage fails
        gracefully: metadata is always returned if the paper resolves,
        even if PDF download or conversion fails. The full pipeline
        typically takes 1-5 minutes.

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
            If the call outruns the jobs soft deadline it returns a job
            handle instead — poll ``get_job_result`` with its ``job_id``.
        """

        async def _execute() -> dict[str, Any]:
            paper, paper_error = await _fetch_paper_or_error(bundle, identifier)
            if paper is None:
                return paper_error or {}

            url, pdf_source = await _resolve_pdf_source(bundle, paper)
            if not url:
                return {"metadata": paper, "error": "no_oa_pdf"}

            paper_id = paper.get("paperId", identifier.replace("/", "_"))
            pdf_dir = bundle.config.cache_dir / "pdfs"
            pdf_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = pdf_dir / f"{paper_id}.pdf"

            download_error = await download_to(pdf_path, url)
            if download_error is not None:
                return {
                    "metadata": paper,
                    "error": "download_failed",
                    "detail": download_error,
                    "pdf_source": pdf_source,
                }

            if bundle.docling is None:
                return {
                    "metadata": paper,
                    "pdf_path": str(pdf_path),
                    "error": "docling_not_configured",
                }

            fields, convert_error = await markdown_fields(
                bundle, pdf_path, paper_id, use_vlm=use_vlm
            )
            if fields is None:
                return {
                    "metadata": paper,
                    "pdf_path": str(pdf_path),
                    "error": "conversion_failed",
                    "detail": convert_error,
                }

            return {
                "metadata": paper,
                "pdf_path": str(pdf_path),
                "pdf_source": pdf_source,
                **fields,
            }

        return await _execute()


def _is_epo_ops_url(url: str) -> bool:
    """True when *url* points at EPO OPS, which needs authenticated access.

    Args:
        url: The URL a caller passed to ``fetch_pdf_by_url``.

    Returns:
        Whether ``fetch_patent_pdf`` should handle it instead.
    """
    netloc = urlparse(url).netloc
    return netloc == "ops.epo.org" or netloc.endswith(".ops.epo.org")


def _url_cache_stem(url: str, filename: str | None) -> str:
    """Derive a filesystem-safe cache stem for *url*.

    Without an explicit *filename*, a short hash of the URL is appended so two
    different URLs sharing a path component do not collide.

    Args:
        url: The PDF's source URL.
        filename: Caller-supplied stem, sanitised and used verbatim when given.

    Returns:
        A stem safe to use as a filename.
    """
    if filename:
        return re.sub(r"[^\w\-]", "_", filename)
    path_part = urlparse(url).path.rsplit("/", 1)[-1]
    base = re.sub(r"[^\w\-]", "_", Path(path_part).stem or "download")
    return f"{base}_{hashlib.sha256(url.encode()).hexdigest()[:8]}"


def _register_fetch_pdf_by_url(mcp: FastMCP, jobs: Jobs) -> None:
    """Register the ``fetch_pdf_by_url`` tool."""

    @register_long_running_tool(
        mcp,
        jobs,
        tags={"write"},
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
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
        converted to Markdown automatically. Download alone usually takes
        10-30 seconds; with conversion, 1-5 minutes.

        Args:
            url: Direct URL to a PDF file.
            filename: Optional filename stem for caching (e.g.
                ``"smith2024_attention"``). Derived from the URL if omitted.
            use_vlm: Use VLM enrichment for formulas and figures.

        Returns:
            ``pdf_path`` and optionally ``markdown`` / ``md_path``.
            If the call outruns the jobs soft deadline it returns a job
            handle instead — poll ``get_job_result`` with its ``job_id``.
        """
        if _is_epo_ops_url(url):
            return {
                "error": "use_fetch_patent_pdf",
                "detail": (
                    "EPO OPS URLs require authenticated access. "
                    "Use the fetch_patent_pdf tool instead, passing the patent number "
                    "(e.g. fetch_patent_pdf('EP3491801B1'))."
                ),
            }

        stem = _url_cache_stem(url, filename)
        pdf_dir = bundle.config.cache_dir / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"{stem}.pdf"

        async def _execute() -> dict[str, Any]:
            if pdf_path.exists():
                logger.info("pdf_by_url_cached path=%s", pdf_path)
            else:
                download_error = await download_to(pdf_path, url)
                if download_error is not None:
                    return {"error": "download_failed", "detail": download_error}
                logger.info("pdf_by_url_downloaded path=%s", pdf_path)

            if bundle.docling is None:
                return {"pdf_path": str(pdf_path)}

            fields, convert_error = await markdown_fields(
                bundle, pdf_path, stem, use_vlm=use_vlm, reuse_cached=True
            )
            if fields is None:
                return {
                    "pdf_path": str(pdf_path),
                    "error": "conversion_failed",
                    "detail": convert_error,
                }
            return {"pdf_path": str(pdf_path), **fields}

        return await _execute()
