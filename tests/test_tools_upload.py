"""Tests for PDF upload links (#546): the sink and the create_upload_link tool."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp_pvl_core import TransferSinkError

from scholar_mcp._tools_upload import UPLOAD_TOOL, PdfUploadSink
from scholar_mcp.server import make_server

S2_BASE = "https://api.semanticscholar.org/graph/v1"
_HTTP_ENV = {
    "SCHOLAR_MCP_BASE_URL": "https://mcp.test",
    "SCHOLAR_MCP_READ_ONLY": "false",
    "SCHOLAR_MCP_DOCLING_URL": "http://docling.test",
}

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


# ---------------------------------------------------------------------------
# create_upload_link: wiring
# ---------------------------------------------------------------------------


def _build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, transport: str, env: dict[str, str]
) -> FastMCP:
    """Build a server synchronously, outside any event loop."""
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp_path / "cache"))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return make_server(transport=transport, configure_logging=False)


@pytest.fixture
def http_server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FastMCP:
    """An HTTP server with a public URL, write tools on and docling configured."""
    return _build(monkeypatch, tmp_path, "http", _HTTP_ENV)


@pytest.fixture
def pdf_dir(tmp_path: Path) -> Path:
    path = tmp_path / "cache" / "pdfs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _visible(mcp: FastMCP) -> bool:
    return asyncio.run(mcp.get_tool(UPLOAD_TOOL)) is not None


def test_tool_absent_on_stdio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert not _visible(_build(monkeypatch, tmp_path, "stdio", _HTTP_ENV))


def test_tool_absent_without_base_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    env = {k: v for k, v in _HTTP_ENV.items() if k != "SCHOLAR_MCP_BASE_URL"}
    monkeypatch.delenv("SCHOLAR_MCP_BASE_URL", raising=False)
    with caplog.at_level(logging.INFO):
        mcp = _build(monkeypatch, tmp_path, "http", env)
    assert not _visible(mcp)
    assert "pdf_upload_disabled" in caplog.text


def test_tool_hidden_read_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env = {**_HTTP_ENV, "SCHOLAR_MCP_READ_ONLY": "true"}
    assert not _visible(_build(monkeypatch, tmp_path, "http", env))


def test_tool_visible_on_http_with_base_url(http_server: FastMCP) -> None:
    assert _visible(http_server)


# ---------------------------------------------------------------------------
# create_upload_link: behaviour
# ---------------------------------------------------------------------------


def _mock_paper(router: respx.MockRouter, record: dict[str, Any]) -> None:
    router.get(url__regex=rf"{S2_BASE}/paper/.*").mock(
        return_value=httpx.Response(200, json=record)
    )


async def _call(mcp: FastMCP, args: dict[str, Any]) -> dict[str, Any]:
    async with Client(mcp) as client:
        result = await client.call_tool(UPLOAD_TOOL, args)
    return json.loads(result.content[0].text)


async def _call_error(mcp: FastMCP, args: dict[str, Any]) -> str:
    async with Client(mcp) as client:
        result = await client.call_tool(UPLOAD_TOOL, args, raise_on_error=False)
    assert result.is_error, result
    return result.content[0].text


async def _put(mcp: FastMCP, url: str, body: bytes) -> int:
    transport = httpx.ASGITransport(app=mcp.http_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://mcp.test") as c:
        response = await c.put(urlparse(url).path, content=body)
    return response.status_code


async def test_link_for_paper(http_server: FastMCP, pdf_dir: Path) -> None:
    with respx.mock(assert_all_called=False) as router:
        _mock_paper(router, {"paperId": "p9", "openAccessPdf": None})
        data = await _call(http_server, {"identifier": "p9"})
    assert data["url"].startswith("https://mcp.test/transfer/")
    assert data["paper_id"] == "p9"
    assert data["expires_in_s"] > 0
    assert await _put(http_server, data["url"], b"%PDF-1.7 up") == 200
    assert (pdf_dir / "p9.pdf").read_bytes() == b"%PDF-1.7 up"


async def test_upload_of_non_pdf_answers_415(http_server: FastMCP) -> None:
    data = await _call(http_server, {})
    assert await _put(http_server, data["url"], b"<html>login</html>") == 415


async def test_link_refused_when_cached(http_server: FastMCP, pdf_dir: Path) -> None:
    (pdf_dir / "p9.pdf").write_bytes(b"%PDF-1.7 cached")
    with respx.mock(assert_all_called=False) as router:
        _mock_paper(router, {"paperId": "p9"})
        message = await _call_error(http_server, {"identifier": "p9"})
    assert "fetch_and_convert" in message
    assert "replace" in message


async def test_link_allowed_when_cached_file_is_not_a_pdf(
    http_server: FastMCP, pdf_dir: Path
) -> None:
    (pdf_dir / "p9.pdf").write_bytes(b"truncated")
    with respx.mock(assert_all_called=False) as router:
        _mock_paper(router, {"paperId": "p9"})
        data = await _call(http_server, {"identifier": "p9"})
    assert await _put(http_server, data["url"], b"%PDF-1.7 good") == 200


async def test_replace_drops_pdf_and_markdown(
    http_server: FastMCP, pdf_dir: Path
) -> None:
    md_dir = pdf_dir.parent / "md"
    md_dir.mkdir()
    cached = [pdf_dir / "p9.pdf", md_dir / "p9.md", md_dir / "p9_vlm.md"]
    cached[0].write_bytes(b"%PDF-1.7 wrong paper")
    cached[1].write_text("# Wrong")
    cached[2].write_text("# Wrong")
    with respx.mock(assert_all_called=False) as router:
        _mock_paper(router, {"paperId": "p9"})
        data = await _call(http_server, {"identifier": "p9", "replace": True})
    assert data["url"]
    assert not any(path.exists() for path in cached)


async def test_replace_when_nothing_cached(http_server: FastMCP) -> None:
    with respx.mock(assert_all_called=False) as router:
        _mock_paper(router, {"paperId": "p9"})
        data = await _call(http_server, {"identifier": "p9", "replace": True})
    assert data["paper_id"] == "p9"


async def test_replace_without_identifier_refused(http_server: FastMCP) -> None:
    message = await _call_error(http_server, {"replace": True})
    assert "identifier" in message


async def test_anonymous_link_returns_pdf_path(
    http_server: FastMCP, pdf_dir: Path
) -> None:
    data = await _call(http_server, {})
    pdf_path = Path(data["pdf_path"])
    assert pdf_path.parent == pdf_dir
    assert pdf_path.stem.startswith("upload-")
    assert "paper_id" not in data
    assert await _put(http_server, data["url"], b"%PDF-1.7 anon") == 200
    assert pdf_path.read_bytes() == b"%PDF-1.7 anon"


async def test_unknown_paper_refused(http_server: FastMCP) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(url__regex=rf"{S2_BASE}/paper/.*").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        message = await _call_error(http_server, {"identifier": "nope"})
    assert "nope" in message


@pytest.fixture
def http_server_no_docling(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FastMCP:
    """An HTTP server with uploads wired but no docling to convert them."""
    env = {k: v for k, v in _HTTP_ENV.items() if k != "SCHOLAR_MCP_DOCLING_URL"}
    monkeypatch.delenv("SCHOLAR_MCP_DOCLING_URL", raising=False)
    return _build(monkeypatch, tmp_path, "http", env)


async def test_docling_unconfigured_refused(http_server_no_docling: FastMCP) -> None:
    message = await _call_error(http_server_no_docling, {})
    assert "convert" in message.lower()


async def test_doi_without_paper_id_uses_shared_stem(
    http_server: FastMCP, pdf_dir: Path
) -> None:
    with respx.mock(assert_all_called=False) as router:
        _mock_paper(router, {"title": "No paper id"})
        data = await _call(http_server, {"identifier": "10.1/x"})
    assert await _put(http_server, data["url"], b"%PDF-1.7 doi") == 200
    assert (pdf_dir / "10.1_x.pdf").exists()


# ---------------------------------------------------------------------------
# fetch_and_convert points at the upload tool
# ---------------------------------------------------------------------------


async def _fetch_without_pdf(mcp: FastMCP) -> dict[str, Any]:
    with respx.mock(assert_all_called=False) as router:
        _mock_paper(router, {"paperId": "p9", "openAccessPdf": None, "externalIds": {}})
        async with Client(mcp) as client:
            result = await client.call_tool("fetch_and_convert", {"identifier": "p9"})
    return json.loads(result.content[0].text)


async def test_no_pdf_payload_mentions_upload_on_http(http_server: FastMCP) -> None:
    data = await _fetch_without_pdf(http_server)
    assert data["error"] == "no_oa_pdf"
    assert UPLOAD_TOOL in data["upload"]


@pytest.fixture
def stdio_server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FastMCP:
    """A stdio server with write tools on: no upload route, so no tool."""
    return _build(monkeypatch, tmp_path, "stdio", _HTTP_ENV)


async def test_no_pdf_payload_silent_on_stdio(stdio_server: FastMCP) -> None:
    data = await _fetch_without_pdf(stdio_server)
    assert data["error"] == "no_oa_pdf"
    assert "upload" not in data


async def test_fetch_and_convert_schema_has_no_ctx(http_server: FastMCP) -> None:
    async with Client(http_server) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    assert "ctx" not in tools["fetch_and_convert"].input_schema["properties"]


async def test_non_positive_ttl_refused(http_server: FastMCP) -> None:
    message = await _call_error(http_server, {"ttl_s": 0})
    assert "ttl_s" in message


async def test_upstream_error_returns_payload(http_server: FastMCP) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(url__regex=rf"{S2_BASE}/paper/.*").mock(
            return_value=httpx.Response(400, json={"error": "bad request"})
        )
        data = await _call(http_server, {"identifier": "p9"})
    assert data["error"] == "upstream_error"
    assert data["status"] == 400


def test_jobs_for_requires_register_tools() -> None:
    from scholar_mcp.tools import jobs_for

    with pytest.raises(RuntimeError, match="register_tools"):
        jobs_for(FastMCP("bare"))


async def test_no_pdf_payload_silent_without_docling(
    http_server_no_docling: FastMCP,
) -> None:
    # create_upload_link refuses without docling, so naming it is a dead end.
    data = await _fetch_without_pdf(http_server_no_docling)
    assert data["error"] == "no_oa_pdf"
    assert "upload" not in data
