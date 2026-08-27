"""Shared PDF download and Markdown-conversion machinery.

Three tools across two modules download a PDF and hand it to docling — the
paper pipeline, the URL pipeline, and the patent pipeline — so the conversion,
its cache, and the fields describing the result live here rather than being
written out once per tool.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from pathlib import Path

    from ._server_deps import ServiceBundle

logger = logging.getLogger(__name__)


async def download_to(path: Path, url: str) -> str | None:
    """Fetch *url* into *path*, unless it is already there.

    Args:
        path: Destination file.
        url: Direct URL to the PDF.

    Returns:
        ``None`` on success, or the transport error's message.
    """
    if path.exists():
        return None
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return str(exc)
    await asyncio.to_thread(path.write_bytes, response.content)
    return None


async def markdown_fields(
    bundle: ServiceBundle,
    pdf_path: Path,
    stem: str,
    *,
    use_vlm: bool,
    reuse_cached: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    """Convert *pdf_path* to Markdown, cache it under *stem*, and describe it.

    The caller checks that docling is configured; this assumes it is.

    Args:
        bundle: Service bundle, for the docling client and cache directory.
        pdf_path: The PDF to convert.
        stem: Filename stem for the cached Markdown.
        use_vlm: Request VLM enrichment for formulas and figures.
        reuse_cached: Return an already-converted Markdown file instead of
            reconverting.

    Returns:
        The shared ``markdown`` / ``md_path`` / ``vlm_used`` fields (plus
        ``vlm_skip_reason`` when one applies), and ``None``; or ``None`` and
        the conversion error's message.
    """
    docling = bundle.docling
    if docling is None:  # pragma: no cover - caller checks before calling
        return None, "docling is not configured"
    vlm_used = use_vlm and docling.vlm_available
    md_dir = bundle.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / f"{stem}{'_vlm' if vlm_used else ''}.md"

    if reuse_cached and md_path.exists():
        markdown = await asyncio.to_thread(md_path.read_text, encoding="utf-8")
    else:
        try:
            pdf_bytes = await asyncio.to_thread(pdf_path.read_bytes)
            markdown = await docling.convert(pdf_bytes, pdf_path.name, use_vlm=use_vlm)
        except Exception as exc:
            logger.exception("docling_convert_failed path=%s", pdf_path)
            return None, str(exc)
        await asyncio.to_thread(md_path.write_text, markdown, encoding="utf-8")

    fields: dict[str, Any] = {
        "markdown": markdown,
        "md_path": str(md_path),
        "vlm_used": vlm_used,
    }
    skip_reason = docling.vlm_skip_reason(use_vlm)
    if skip_reason:
        fields["vlm_skip_reason"] = skip_reason
    return fields, None
