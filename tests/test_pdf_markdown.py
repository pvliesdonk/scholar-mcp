"""Tests for the shared PDF download / Markdown-conversion helpers.

These moved out of `_tools_pdf` when three tools across two modules turned out
to be running the same download-convert-cache sequence (#298). Testing them
directly is cheaper than reaching them through a tool, and it pins the two
contracts their callers rely on: `download_to` reports a transport failure
rather than raising, and `markdown_fields` reports a conversion failure the
same way, so a caller can still return the PDF it does have.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from scholar_mcp._pdf_markdown import download_to, markdown_fields
from scholar_mcp._server_deps import ServiceBundle


@respx.mock
async def test_download_to_writes_the_file(tmp_path: Path) -> None:
    """A successful fetch lands the bytes on disk and reports no error."""
    respx.get("https://example.com/a.pdf").mock(
        return_value=httpx.Response(200, content=b"%PDF ok")
    )
    target = tmp_path / "a.pdf"

    assert await download_to(target, "https://example.com/a.pdf") is None
    assert target.read_bytes() == b"%PDF ok"


@respx.mock
async def test_download_to_reports_transport_failure(tmp_path: Path) -> None:
    """A failed fetch returns the error message and leaves no partial file."""
    respx.get("https://example.com/gone.pdf").mock(return_value=httpx.Response(404))
    target = tmp_path / "gone.pdf"

    error = await download_to(target, "https://example.com/gone.pdf")

    assert error is not None
    assert not target.exists()


async def test_download_to_skips_an_existing_file(tmp_path: Path) -> None:
    """An already-downloaded file is left alone — and no request is made."""
    target = tmp_path / "cached.pdf"
    target.write_bytes(b"%PDF cached")

    # No respx mock is active, so any HTTP call would raise.
    assert await download_to(target, "https://example.com/cached.pdf") is None
    assert target.read_bytes() == b"%PDF cached"


async def test_markdown_fields_converts_and_caches(
    bundle_with_docling: ServiceBundle, tmp_path: Path
) -> None:
    """Conversion writes the Markdown cache and describes the result."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        return_value="# Title"
    )

    fields, error = await markdown_fields(
        bundle_with_docling, pdf, "paper", use_vlm=False
    )

    assert error is None
    assert fields is not None
    assert fields["markdown"] == "# Title"
    assert fields["vlm_used"] is False
    assert Path(fields["md_path"]).read_text(encoding="utf-8") == "# Title"


async def test_markdown_fields_reuses_the_cache(
    bundle_with_docling: ServiceBundle, tmp_path: Path
) -> None:
    """With `reuse_cached`, an existing conversion is read, not redone."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    md_dir = bundle_with_docling.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    (md_dir / "paper.md").write_text("# Cached", encoding="utf-8")
    convert = AsyncMock(return_value="# Fresh")
    bundle_with_docling.docling.convert = convert  # type: ignore[union-attr]

    fields, error = await markdown_fields(
        bundle_with_docling, pdf, "paper", use_vlm=False, reuse_cached=True
    )

    assert error is None
    assert fields is not None
    assert fields["markdown"] == "# Cached"
    convert.assert_not_called()


async def test_markdown_fields_reports_conversion_failure(
    bundle_with_docling: ServiceBundle, tmp_path: Path
) -> None:
    """A docling failure comes back as an error, not an exception."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        side_effect=RuntimeError("docling down")
    )

    fields, error = await markdown_fields(
        bundle_with_docling, pdf, "paper", use_vlm=False
    )

    assert fields is None
    assert error == "docling down"


async def test_markdown_fields_reports_a_vlm_skip_reason(
    bundle_with_docling: ServiceBundle, tmp_path: Path
) -> None:
    """Requesting VLM without it configured is reported, not silently ignored."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        return_value="# Title"
    )

    fields, _ = await markdown_fields(bundle_with_docling, pdf, "paper", use_vlm=True)

    assert fields is not None
    assert fields["vlm_used"] is False
    assert fields["vlm_skip_reason"] == "vlm_api_url_not_configured"


@pytest.mark.parametrize("filename", [None, "smith 2024/attention"])
def test_url_cache_stem_is_filesystem_safe(filename: str | None) -> None:
    """Derived stems never carry separators or spaces."""
    from scholar_mcp._tools_pdf import _url_cache_stem

    stem = _url_cache_stem("https://example.com/a b/paper.pdf", filename)

    assert "/" not in stem
    assert " " not in stem
