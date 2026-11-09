"""Tests for PDF upload links (#546): the sink and the create_upload_link tool."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp_pvl_core import TransferSinkError

from scholar_mcp._tools_upload import PdfUploadSink

# ---------------------------------------------------------------------------
# PdfUploadSink
# ---------------------------------------------------------------------------


async def test_sink_writes_pdf(tmp_path: Path) -> None:
    sink = PdfUploadSink(tmp_path / "pdfs")
    result = await sink.write("p1", b"%PDF-1.7 x")
    target = tmp_path / "pdfs" / "p1.pdf"
    assert target.read_bytes() == b"%PDF-1.7 x"
    assert result["pdf_path"] == str(target)
    assert result["bytes"] == len(b"%PDF-1.7 x")


async def test_sink_rejects_html_login_page(tmp_path: Path) -> None:
    # A paywall's login page saved as ".pdf" is the likeliest wrong upload.
    sink = PdfUploadSink(tmp_path / "pdfs")
    with pytest.raises(TransferSinkError) as excinfo:
        await sink.write("p1", b"<!DOCTYPE html><html>login")
    assert excinfo.value.status_code == 415
    assert not (tmp_path / "pdfs" / "p1.pdf").exists()


async def test_sink_rejects_empty_body(tmp_path: Path) -> None:
    sink = PdfUploadSink(tmp_path / "pdfs")
    with pytest.raises(TransferSinkError) as excinfo:
        await sink.write("p1", b"")
    assert excinfo.value.status_code == 415
    assert not (tmp_path / "pdfs" / "p1.pdf").exists()


async def test_sink_refuses_existing_valid_pdf(tmp_path: Path) -> None:
    # Two links minted before either upload must not let the second
    # overwrite a PDF whose Markdown may already be cached.
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    (pdf_dir / "p1.pdf").write_bytes(b"%PDF-1.7 old")
    sink = PdfUploadSink(pdf_dir)
    with pytest.raises(TransferSinkError) as excinfo:
        await sink.write("p1", b"%PDF-1.7 new")
    assert excinfo.value.status_code == 409
    assert (pdf_dir / "p1.pdf").read_bytes() == b"%PDF-1.7 old"


async def test_sink_overwrites_invalid_cached_file(tmp_path: Path) -> None:
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    (pdf_dir / "p1.pdf").write_bytes(b"garbage")
    sink = PdfUploadSink(pdf_dir)
    await sink.write("p1", b"%PDF-1.7 new")
    assert (pdf_dir / "p1.pdf").read_bytes() == b"%PDF-1.7 new"


async def test_sink_read_is_not_served(tmp_path: Path) -> None:
    sink = PdfUploadSink(tmp_path / "pdfs")
    with pytest.raises(TransferSinkError) as excinfo:
        await sink.read("p1")
    assert excinfo.value.status_code == 404


@pytest.mark.parametrize("handle", ["../x", "a/b", "a\\b", ".."])
async def test_sink_rejects_traversal_handle(tmp_path: Path, handle: str) -> None:
    sink = PdfUploadSink(tmp_path / "pdfs")
    with pytest.raises(TransferSinkError) as excinfo:
        await sink.write(handle, b"%PDF-1.7 x")
    assert excinfo.value.status_code == 400
