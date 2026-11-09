"""Upload links for PDFs the server could not fetch itself (#546).

On a licensed network the user, or an agent working for them, can download a
paper the server cannot reach. This module lets that PDF travel to the server
over a one-time HTTP upload link, outside the conversation, after which the
existing conversion tools serve its Markdown. See
``docs/design/access-links.md``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

import httpx
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from fastmcp_pvl_core import (
    TransferReadResult,
    TransferSinkError,
    add_transfer_workflow,
)

from ._paper_cache import resolve_paper
from ._s2_client import s2_error_payload
from ._s2_jobs import register_s2_tool
from ._server_deps import get_service
from ._tools_pdf import (
    _PDF_HEADER,
    _cached_pdf_is_valid,
    _paper_pdf_stem,
    _write_pdf_cache,
)
from .domain import Service
from .tools import jobs_for

if TYPE_CHECKING:
    from pathlib import Path

    from fastmcp import FastMCP
    from fastmcp_pvl_core import TransferLinks

UPLOAD_TOOL = "create_upload_link"
# The reference page the tool is listed on (scripts/gen_reference.py).
_GROUP = "group:full-text"

logger = logging.getLogger(__name__)


class PdfUploadSink:
    """Store an uploaded PDF in the PDF cache under the stem its link names.

    The handle is the file stem fixed when the link was minted: a paper's
    cache stem, or a server-chosen name for an anonymous upload. The bytes
    must be a PDF, and a valid PDF already at the target is never replaced;
    a correction goes through ``create_upload_link(replace=true)``, which
    clears the cache before minting.

    Args:
        pdf_dir: The cache's ``pdfs`` directory.
    """

    def __init__(self, pdf_dir: Path) -> None:
        self._pdf_dir = pdf_dir

    def _target(self, handle: str) -> Path:
        """Map a handle to its file, refusing anything that is not a bare stem."""
        if not handle or "/" in handle or "\\" in handle or ".." in handle:
            raise TransferSinkError(400, "upload handle is not a file stem")
        return self._pdf_dir / f"{handle}.pdf"

    async def write(self, handle: str, body: bytes) -> dict[str, Any]:
        """Store *body* as the PDF for *handle*.

        Args:
            handle: The file stem the link was minted for.
            body: The uploaded bytes.

        Returns:
            ``{"pdf_path": ..., "bytes": ...}`` for the stored file.

        Raises:
            TransferSinkError: 400 for a handle that is not a bare stem, 415
                when the body is not a PDF, 409 when a valid PDF is already
                stored there. pvl-core releases the link on each, so the
                right file can still be sent.
        """
        target = self._target(handle)
        if not body.startswith(_PDF_HEADER):
            logger.info("pdf_upload_rejected reason=not_pdf handle=%s", handle)
            raise TransferSinkError(415, "upload is not a PDF")
        if await asyncio.to_thread(_cached_pdf_is_valid, target):
            logger.info("pdf_upload_rejected reason=exists handle=%s", handle)
            raise TransferSinkError(409, "a PDF is already stored for this link")
        await asyncio.to_thread(self._pdf_dir.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(_write_pdf_cache, target, body)
        logger.info("pdf_upload_stored path=%s bytes=%d", target, len(body))
        return {"pdf_path": str(target), "bytes": len(body)}

    async def read(self, handle: str) -> TransferReadResult:
        """Refuse every download: this server mints upload links only.

        Raises:
            TransferSinkError: Always, with status 404.
        """
        logger.info("pdf_upload_download_refused handle=%s", handle)
        raise TransferSinkError(404, "this server serves no downloads")


def _drop_cached(cache_dir: Path, stem: str) -> None:
    """Delete a stem's cached PDF and both of its Markdown conversions."""
    (cache_dir / "pdfs" / f"{stem}.pdf").unlink(missing_ok=True)
    for name in (f"{stem}.md", f"{stem}_vlm.md"):
        (cache_dir / "md" / name).unlink(missing_ok=True)


async def _paper_stem(service: Service, identifier: str) -> str | dict[str, Any]:
    """Resolve *identifier* to its cache stem, or an upstream-error payload."""
    try:
        paper = await resolve_paper(service.cache, service.s2.get_paper, identifier)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ToolError(
                f"No paper found for identifier '{identifier}'. Check it with "
                "get_paper, or call create_upload_link without an identifier "
                "to convert the PDF on its own.",
                log_level=logging.INFO,
            ) from None
        return s2_error_payload(exc)
    return _paper_pdf_stem(paper, identifier)


def register_upload_tool(mcp: FastMCP, links: TransferLinks) -> None:
    """Register ``create_upload_link`` on *mcp*, minting through *links*.

    Called from ``make_server``'s wiring only on an HTTP transport with a
    public base URL, after :func:`scholar_mcp.tools.register_tools`, whose
    ``Jobs`` the tool shares.

    Args:
        mcp: The server to register on.
        links: The minter :func:`fastmcp_pvl_core.build_transfer_links`
            returned for this server.
    """
    jobs, jobs_config = jobs_for(mcp)

    async def create_upload_link(
        identifier: str | None = None,
        replace: bool = False,
        ttl_s: float | None = None,
        service: Service = Depends(get_service),
    ) -> dict[str, Any]:
        """Create a one-time link for uploading a PDF this server cannot fetch.

        Use it when this server could not fetch a paper's PDF and the user
        can download it through their own library. Send the file as the body
        of an HTTP PUT to the returned ``url``, outside the conversation.
        Never read it into the conversation. With an identifier, call
        fetch_and_convert with the same identifier once the upload is done.
        Without one, call convert_pdf_to_markdown with the returned pdf_path.
        If a converted paper turns out to be the wrong document, call this
        tool again with replace=true: the stored PDF and its conversion are
        removed at once.

        Args:
            identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.) the PDF
                belongs to. Omit it for a document that is not a known paper.
            replace: Remove this paper's stored PDF and Markdown before
                creating the link. Needs an identifier.
            ttl_s: Link lifetime in seconds. Omit it for the server default.

        Returns:
            ``url`` and ``expires_in_s``, plus ``paper_id`` with an
            identifier or ``pdf_path`` without one.
        """
        if service.docling is None:
            raise ToolError(
                "This server cannot convert PDFs, so an upload could not be "
                "read. Tell the user PDF conversion is not available here.",
                log_level=logging.INFO,
            )
        if ttl_s is not None and not ttl_s > 0:
            raise ToolError(
                f"ttl_s must be greater than 0, got {ttl_s}; omit it to use "
                "the server's default link lifetime.",
                log_level=logging.INFO,
            )
        cache_dir = service.config.cache_dir
        if identifier is None:
            if replace:
                raise ToolError(
                    "replace=true needs the identifier of the paper whose "
                    "stored PDF is wrong; pass identifier.",
                    log_level=logging.INFO,
                )
            stem = f"upload-{uuid.uuid4().hex}"
            link = await links.mint_upload(stem, ttl_s)
            logger.info("pdf_upload_link_minted stem=%s", stem)
            return {**link, "pdf_path": str(cache_dir / "pdfs" / f"{stem}.pdf")}

        resolved = await _paper_stem(service, identifier)
        if isinstance(resolved, dict):
            return resolved
        stem = resolved
        if replace:
            await asyncio.to_thread(_drop_cached, cache_dir, stem)
            logger.info("pdf_upload_replace paper_id=%s", stem)
        elif await asyncio.to_thread(
            _cached_pdf_is_valid, cache_dir / "pdfs" / f"{stem}.pdf"
        ):
            raise ToolError(
                f"A PDF for '{identifier}' is already stored. Call "
                "fetch_and_convert with this identifier to read it, or call "
                "create_upload_link with replace=true if it is the wrong "
                "document.",
                log_level=logging.INFO,
            )
        link = await links.mint_upload(stem, ttl_s)
        logger.info("pdf_upload_link_minted stem=%s", stem)
        return {**link, "paper_id": stem}

    register_s2_tool(
        mcp,
        jobs,
        jobs_config=jobs_config,
        name=UPLOAD_TOOL,
        tags={_GROUP, "write"},
        annotations={
            "title": "Create PDF Upload Link",
            "readOnlyHint": False,
            # replace=true deletes stored files.
            "destructiveHint": True,
            "openWorldHint": True,
        },
    )(create_upload_link)
    add_transfer_workflow(mcp, upload_tool=UPLOAD_TOOL)
