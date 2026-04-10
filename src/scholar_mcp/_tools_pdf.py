"""PDF download and conversion MCP tools."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._pdf_url_resolver import ResolvedPdf, resolve_alternative_pdf
from ._rate_limiter import RateLimitedError
from ._server_deps import ServiceBundle, get_bundle

_PDF_TASK_TTL = 3600.0  # 1 hour for PDF operations

logger = logging.getLogger(__name__)


def register_pdf_tools(mcp: FastMCP) -> None:
    """Register PDF tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool(
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
    ) -> str:
        """Download the PDF of a paper.

        Tries the Semantic Scholar open-access URL first. When that is
        unavailable, automatically checks alternative sources: ArXiv
        (from externalIds), PubMed Central, and Unpaywall (by DOI,
        requires ``SCHOLAR_MCP_CONTACT_EMAIL``).

        Skips download if the file already exists locally.

        Args:
            identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).

        Returns:
            JSON ``{"path": "...", "source": "..."}`` on success, or a
            structured error dict. The ``source`` field indicates where the
            PDF was obtained (``s2_oa``, ``arxiv``, ``pmc``, ``unpaywall``).
        """

        async def _download(
            paper_data: dict,  # type: ignore[type-arg]
            resolved: ResolvedPdf | None = None,
        ) -> str:
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
                return json.dumps(
                    {
                        "error": "no_oa_pdf",
                        "paper_id": paper_data.get("paperId"),
                        "title": paper_data.get("title"),
                    }
                )
            pid = paper_data.get("paperId", identifier.replace("/", "_"))
            dl_dir = bundle.config.cache_dir / "pdfs"
            dl_dir.mkdir(parents=True, exist_ok=True)
            dl_path = dl_dir / f"{pid}.pdf"
            if dl_path.exists():
                return json.dumps({"path": str(dl_path), "source": pdf_source})
            async with httpx.AsyncClient(timeout=120.0) as client:
                try:
                    r = await client.get(dl_url, follow_redirects=True)
                    r.raise_for_status()
                except httpx.HTTPError as dl_exc:
                    return json.dumps(
                        {"error": "download_failed", "detail": str(dl_exc)}
                    )
            await asyncio.to_thread(dl_path.write_bytes, r.content)
            logger.info(
                "pdf_downloaded path=%s bytes=%d source=%s",
                dl_path,
                len(r.content),
                pdf_source,
            )
            return json.dumps({"path": str(dl_path), "source": pdf_source})

        # Resolve metadata to check local cache before queuing
        try:
            paper = await bundle.s2.get_paper(
                identifier,
                fields="paperId,openAccessPdf,externalIds,title",
                retry=False,
            )
        except RateLimitedError:
            # S2 rate-limited; queue entire operation for background
            logger.debug("rate_limited_queued tool=%s", "fetch_paper_pdf")

            async def _execute_full() -> str:
                try:
                    p = await bundle.s2.get_paper(
                        identifier,
                        fields="paperId,openAccessPdf,externalIds,title",
                    )
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        return json.dumps(
                            {"error": "not_found", "identifier": identifier}
                        )
                    return json.dumps(
                        {
                            "error": "upstream_error",
                            "status": exc.response.status_code,
                        }
                    )
                return await _download(p)

            task_id = bundle.tasks.submit(
                _execute_full(), ttl=_PDF_TASK_TTL, tool="fetch_paper_pdf"
            )
            return json.dumps(
                {
                    "queued": True,
                    "task_id": task_id,
                    "tool": "fetch_paper_pdf",
                }
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return json.dumps({"error": "not_found", "identifier": identifier})
            return json.dumps(
                {
                    "error": "upstream_error",
                    "status": exc.response.status_code,
                }
            )

        oa_pdf = paper.get("openAccessPdf") or {}
        url = oa_pdf.get("url")
        alt: ResolvedPdf | None = None
        if not url:
            alt = await resolve_alternative_pdf(
                paper,
                contact_email=bundle.config.contact_email,
            )
            if not alt:
                return json.dumps(
                    {
                        "error": "no_oa_pdf",
                        "paper_id": paper.get("paperId"),
                        "title": paper.get("title"),
                    }
                )

        paper_id = paper.get("paperId", identifier.replace("/", "_"))
        pdf_dir = bundle.config.cache_dir / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"{paper_id}.pdf"

        if pdf_path.exists():
            logger.info("pdf_already_exists path=%s", pdf_path)
            source = alt.source if alt else "s2_oa"
            return json.dumps({"path": str(pdf_path), "source": source})

        # PDF not cached — queue the download, passing resolved alt to
        # avoid a duplicate Unpaywall lookup inside _download.
        task_id = bundle.tasks.submit(
            _download(paper, resolved=alt),
            ttl=_PDF_TASK_TTL,
            tool="fetch_paper_pdf",
        )
        return json.dumps(
            {"queued": True, "task_id": task_id, "tool": "fetch_paper_pdf"}
        )

    @mcp.tool(
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
    ) -> str:
        """Convert a local PDF to Markdown using docling-serve.

        Works on any local PDF, including manually placed paywalled papers.
        Returns an error if the server does not have PDF conversion configured.

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
            JSON ``{"markdown": "...", "path": "...", "vlm_used": bool}``.
        """
        if bundle.docling is None:
            return json.dumps({"error": "docling_not_configured"})

        path = Path(file_path)
        if not path.exists():
            return json.dumps({"error": "file_not_found", "path": file_path})

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
            return json.dumps(result)

        async def _execute() -> str:
            pdf_bytes = await asyncio.to_thread(path.read_bytes)

            try:
                markdown = await bundle.docling.convert(  # type: ignore[union-attr]
                    pdf_bytes, path.name, use_vlm=use_vlm
                )
            except Exception as exc:
                logger.exception("docling_convert_failed path=%s", file_path)
                return json.dumps({"error": "docling_error", "detail": str(exc)})

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
            return json.dumps(result)

        task_id = bundle.tasks.submit(
            _execute(), ttl=_PDF_TASK_TTL, tool="convert_pdf_to_markdown"
        )
        return json.dumps(
            {
                "queued": True,
                "task_id": task_id,
                "tool": "convert_pdf_to_markdown",
            }
        )

    @mcp.tool(
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
    ) -> str:
        """Resolve a paper, download its PDF, and convert to Markdown.

        Tries the Semantic Scholar open-access URL first, then alternative
        sources (ArXiv, PubMed Central, Unpaywall). Each stage fails
        gracefully: metadata is always returned if the paper resolves,
        even if PDF download or conversion fails.

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
            JSON with ``metadata`` and ``markdown`` on full success,
            or ``metadata`` plus an ``error`` key if a stage fails.
        """

        async def _execute() -> str:
            try:
                paper = await bundle.s2.get_paper(identifier)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    return json.dumps({"error": "not_found", "identifier": identifier})
                return json.dumps(
                    {
                        "error": "upstream_error",
                        "status": exc.response.status_code,
                    }
                )

            oa_pdf = paper.get("openAccessPdf") or {}
            url = oa_pdf.get("url")
            pdf_source = "s2_oa"
            if not url:
                alt = await resolve_alternative_pdf(
                    paper,
                    contact_email=bundle.config.contact_email,
                )
                if alt:
                    url = alt.url
                    pdf_source = alt.source
            if not url:
                return json.dumps({"metadata": paper, "error": "no_oa_pdf"})

            paper_id = paper.get("paperId", identifier.replace("/", "_"))
            pdf_dir = bundle.config.cache_dir / "pdfs"
            pdf_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = pdf_dir / f"{paper_id}.pdf"

            if not pdf_path.exists():
                async with httpx.AsyncClient(timeout=120.0) as client:
                    try:
                        r = await client.get(url, follow_redirects=True)
                        r.raise_for_status()
                        await asyncio.to_thread(pdf_path.write_bytes, r.content)
                    except httpx.HTTPError as exc:
                        return json.dumps(
                            {
                                "metadata": paper,
                                "error": "download_failed",
                                "detail": str(exc),
                                "pdf_source": pdf_source,
                            }
                        )

            if bundle.docling is None:
                return json.dumps(
                    {
                        "metadata": paper,
                        "pdf_path": str(pdf_path),
                        "error": "docling_not_configured",
                    }
                )

            try:
                pdf_bytes_for_convert = await asyncio.to_thread(pdf_path.read_bytes)
                markdown = await bundle.docling.convert(
                    pdf_bytes_for_convert, pdf_path.name, use_vlm=use_vlm
                )
            except Exception as exc:
                return json.dumps(
                    {
                        "metadata": paper,
                        "pdf_path": str(pdf_path),
                        "error": "conversion_failed",
                        "detail": str(exc),
                    }
                )

            vlm_used = use_vlm and bundle.docling.vlm_available
            vlm_suffix = "_vlm" if vlm_used else ""
            md_dir = bundle.config.cache_dir / "md"
            md_dir.mkdir(parents=True, exist_ok=True)
            md_path = md_dir / f"{paper_id}{vlm_suffix}.md"
            await asyncio.to_thread(md_path.write_text, markdown, encoding="utf-8")
            result: dict[str, object] = {
                "metadata": paper,
                "markdown": markdown,
                "pdf_path": str(pdf_path),
                "md_path": str(md_path),
                "pdf_source": pdf_source,
                "vlm_used": vlm_used,
            }
            skip_reason = bundle.docling.vlm_skip_reason(use_vlm)
            if skip_reason:
                result["vlm_skip_reason"] = skip_reason
            return json.dumps(result)

        task_id = bundle.tasks.submit(
            _execute(), ttl=_PDF_TASK_TTL, tool="fetch_and_convert"
        )
        return json.dumps(
            {"queued": True, "task_id": task_id, "tool": "fetch_and_convert"}
        )

    @mcp.tool(
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
    ) -> str:
        """Download a PDF from a URL and optionally convert to Markdown.

        Use this when you have found an alternative PDF link (e.g. from an
        author's homepage, a preprint server, or an institutional repository)
        that is not listed in Semantic Scholar's openAccessPdf field.

        The PDF is saved locally and, if docling-serve is configured,
        converted to Markdown automatically.

        Args:
            url: Direct URL to a PDF file.
            filename: Optional filename stem for caching (e.g.
                ``"smith2024_attention"``). Derived from the URL if omitted.
            use_vlm: Use VLM enrichment for formulas and figures.

        Returns:
            JSON with ``pdf_path`` and optionally ``markdown`` / ``md_path``.
        """
        # Intercept authenticated service URLs that need special handling
        from urllib.parse import urlparse as _urlparse

        _parsed = _urlparse(url)
        if _parsed.netloc == "ops.epo.org" or _parsed.netloc.endswith(".ops.epo.org"):
            return json.dumps(
                {
                    "error": "use_fetch_patent_pdf",
                    "detail": (
                        "EPO OPS URLs require authenticated access. "
                        "Use the fetch_patent_pdf tool instead, passing the patent number "
                        "(e.g. fetch_patent_pdf('EP3491801B1'))."
                    ),
                }
            )

        import hashlib
        import re
        from urllib.parse import urlparse

        # Derive a safe filename stem.  When no explicit filename is
        # given, incorporate a short URL hash to avoid collisions when
        # different URLs share the same path component.
        if filename:
            stem = re.sub(r"[^\w\-]", "_", filename)
        else:
            path_part = urlparse(url).path.rsplit("/", 1)[-1]
            base = Path(path_part).stem or "download"
            base = re.sub(r"[^\w\-]", "_", base)
            url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
            stem = f"{base}_{url_hash}"

        pdf_dir = bundle.config.cache_dir / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"{stem}.pdf"

        if pdf_path.exists():
            logger.info("pdf_by_url_cached path=%s", pdf_path)
            # Still convert if docling available and markdown not cached
            if bundle.docling is not None:
                vlm_suffix = "_vlm" if use_vlm and bundle.docling.vlm_available else ""
                md_dir = bundle.config.cache_dir / "md"
                md_path = md_dir / f"{stem}{vlm_suffix}.md"
                if md_path.exists():
                    markdown = await asyncio.to_thread(
                        md_path.read_text, encoding="utf-8"
                    )
                    result: dict[str, object] = {
                        "pdf_path": str(pdf_path),
                        "markdown": markdown,
                        "md_path": str(md_path),
                        "vlm_used": bool(vlm_suffix),
                    }
                    skip_reason = bundle.docling.vlm_skip_reason(use_vlm)
                    if skip_reason:
                        result["vlm_skip_reason"] = skip_reason
                    return json.dumps(result)
            else:
                return json.dumps({"pdf_path": str(pdf_path)})

        async def _execute() -> str:
            # Download
            if not pdf_path.exists():
                async with httpx.AsyncClient(timeout=120.0) as client:
                    try:
                        r = await client.get(url, follow_redirects=True)
                        r.raise_for_status()
                    except httpx.HTTPError as exc:
                        return json.dumps(
                            {"error": "download_failed", "detail": str(exc)}
                        )
                await asyncio.to_thread(pdf_path.write_bytes, r.content)
                logger.info(
                    "pdf_by_url_downloaded path=%s bytes=%d",
                    pdf_path,
                    len(r.content),
                )

            # Convert if docling available
            if bundle.docling is None:
                return json.dumps({"pdf_path": str(pdf_path)})

            vlm_suffix = "_vlm" if use_vlm and bundle.docling.vlm_available else ""
            md_dir = bundle.config.cache_dir / "md"
            md_dir.mkdir(parents=True, exist_ok=True)
            md_path = md_dir / f"{stem}{vlm_suffix}.md"

            if md_path.exists():
                markdown = await asyncio.to_thread(md_path.read_text, encoding="utf-8")
            else:
                try:
                    pdf_bytes = await asyncio.to_thread(pdf_path.read_bytes)
                    markdown = await bundle.docling.convert(
                        pdf_bytes, pdf_path.name, use_vlm=use_vlm
                    )
                except Exception as exc:
                    logger.exception("docling_convert_failed path=%s", pdf_path)
                    return json.dumps(
                        {
                            "pdf_path": str(pdf_path),
                            "error": "conversion_failed",
                            "detail": str(exc),
                        }
                    )
                await asyncio.to_thread(md_path.write_text, markdown, encoding="utf-8")

            vlm_used = use_vlm and bundle.docling.vlm_available
            result: dict[str, object] = {
                "pdf_path": str(pdf_path),
                "markdown": markdown,
                "md_path": str(md_path),
                "vlm_used": vlm_used,
            }
            skip_reason = bundle.docling.vlm_skip_reason(use_vlm)
            if skip_reason:
                result["vlm_skip_reason"] = skip_reason
            return json.dumps(result)

        task_id = bundle.tasks.submit(
            _execute(), ttl=_PDF_TASK_TTL, tool="fetch_pdf_by_url"
        )
        return json.dumps(
            {"queued": True, "task_id": task_id, "tool": "fetch_pdf_by_url"}
        )
