"""PDF download and conversion MCP tools."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)


def register_pdf_tools(mcp: FastMCP) -> None:
    """Register PDF tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool(tags={"write"})
    async def fetch_paper_pdf(
        identifier: str,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Download the open-access PDF of a paper.

        Only works for papers with an open-access PDF URL in Semantic Scholar.
        Skips download if the file already exists locally.

        Args:
            identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).

        Returns:
            JSON ``{"path": "..."}`` on success, or a structured error dict.
        """
        try:
            paper = await bundle.s2.get_paper(
                identifier, fields="paperId,openAccessPdf,title"
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return json.dumps({"error": "not_found", "identifier": identifier})
            return json.dumps(
                {"error": "upstream_error", "status": exc.response.status_code}
            )

        oa_pdf = paper.get("openAccessPdf") or {}
        url = oa_pdf.get("url")
        if not url:
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
            return json.dumps({"path": str(pdf_path)})

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                r = await client.get(url, follow_redirects=True)
                r.raise_for_status()
            except httpx.HTTPError as exc:
                return json.dumps({"error": "download_failed", "detail": str(exc)})

        pdf_path.write_bytes(r.content)
        logger.info("pdf_downloaded path=%s bytes=%d", pdf_path, len(r.content))
        return json.dumps({"path": str(pdf_path)})

    @mcp.tool()
    async def convert_pdf_to_markdown(
        file_path: str,
        use_vlm: bool = False,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Convert a local PDF to Markdown using docling-serve.

        Works on any local PDF, including manually placed paywalled papers.
        Requires ``SCHOLAR_MCP_DOCLING_URL`` to be configured.

        Args:
            file_path: Absolute path to the local PDF file.
            use_vlm: Use VLM enrichment for formulas and figures (requires
                ``SCHOLAR_MCP_VLM_API_URL`` and ``SCHOLAR_MCP_VLM_API_KEY``).
                Falls back to standard path if VLM is not configured.

        Returns:
            JSON ``{"markdown": "...", "path": "...", "vlm_used": bool}``.
        """
        if bundle.docling is None:
            return json.dumps({"error": "docling_not_configured"})

        path = Path(file_path)
        if not path.exists():
            return json.dumps({"error": "file_not_found", "path": file_path})

        pdf_bytes = path.read_bytes()
        vlm_used = use_vlm and bundle.docling.vlm_available

        try:
            markdown = await bundle.docling.convert(
                pdf_bytes, path.name, use_vlm=use_vlm
            )
        except Exception as exc:
            logger.exception("docling_convert_failed path=%s", file_path)
            return json.dumps({"error": "docling_error", "detail": str(exc)})

        md_dir = bundle.config.cache_dir / "md"
        md_dir.mkdir(parents=True, exist_ok=True)
        md_path = md_dir / f"{path.stem}.md"
        md_path.write_text(markdown, encoding="utf-8")

        return json.dumps(
            {"markdown": markdown, "path": str(md_path), "vlm_used": vlm_used}
        )

    @mcp.tool()
    async def fetch_and_convert(
        identifier: str,
        use_vlm: bool = False,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Resolve a paper, download its OA PDF, and convert to Markdown.

        Each stage fails gracefully: metadata is always returned if the paper
        resolves, even if PDF download or conversion fails.

        Args:
            identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).
            use_vlm: Use VLM enrichment for formula/figure extraction.

        Returns:
            JSON with ``metadata`` and ``markdown`` on full success,
            or ``metadata`` plus an ``error`` key if a stage fails.
        """
        try:
            paper = await bundle.s2.get_paper(identifier)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return json.dumps({"error": "not_found", "identifier": identifier})
            return json.dumps(
                {"error": "upstream_error", "status": exc.response.status_code}
            )

        oa_pdf = paper.get("openAccessPdf") or {}
        url = oa_pdf.get("url")
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
                    pdf_path.write_bytes(r.content)
                except httpx.HTTPError as exc:
                    return json.dumps(
                        {
                            "metadata": paper,
                            "error": "download_failed",
                            "detail": str(exc),
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
            markdown = await bundle.docling.convert(
                pdf_path.read_bytes(), pdf_path.name, use_vlm=use_vlm
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

        md_dir = bundle.config.cache_dir / "md"
        md_dir.mkdir(parents=True, exist_ok=True)
        md_path = md_dir / f"{paper_id}.md"
        md_path.write_text(markdown, encoding="utf-8")

        return json.dumps(
            {
                "metadata": paper,
                "markdown": markdown,
                "pdf_path": str(pdf_path),
                "md_path": str(md_path),
                "vlm_used": use_vlm and bundle.docling.vlm_available,
            }
        )
