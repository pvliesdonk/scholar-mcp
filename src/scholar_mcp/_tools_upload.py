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
from typing import TYPE_CHECKING, Any

from fastmcp_pvl_core import TransferReadResult, TransferSinkError

from ._tools_pdf import _PDF_HEADER, _cached_pdf_is_valid, _write_pdf_cache

if TYPE_CHECKING:
    from pathlib import Path

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
