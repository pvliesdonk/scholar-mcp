"""Tests for fetch_paper_pdf, convert_pdf_to_markdown, fetch_and_convert."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._docling_client import DoclingClient
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_pdf import register_pdf_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"
DOCLING_BASE = "http://docling:5001"


@pytest.fixture
def bundle_with_docling(bundle: ServiceBundle, tmp_path: Path) -> ServiceBundle:
    docling_http = httpx.AsyncClient(base_url=DOCLING_BASE, timeout=30.0)
    bundle.docling = DoclingClient(
        http_client=docling_http, vlm_api_url=None, vlm_api_key=None, vlm_model="gpt-4o"
    )
    return bundle


@pytest.fixture
def mcp_no_docling(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_pdf_tools(app)
    return app


@pytest.fixture
def mcp_with_docling(bundle_with_docling: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle_with_docling}

    app = FastMCP("test", lifespan=lifespan)
    register_pdf_tools(app)
    return app


@pytest.mark.respx(base_url=S2_BASE)
async def test_fetch_paper_pdf_no_oa(
    respx_mock: respx.MockRouter, mcp_no_docling: FastMCP
) -> None:
    respx_mock.get("/paper/p1").mock(
        return_value=httpx.Response(200, json={"paperId": "p1", "openAccessPdf": None})
    )
    async with Client(mcp_no_docling) as client:
        result = await client.call_tool("fetch_paper_pdf", {"identifier": "p1"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "no_oa_pdf"


async def test_convert_no_docling(mcp_no_docling: FastMCP, tmp_path: Path) -> None:
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF fake")
    async with Client(mcp_no_docling) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
    data = json.loads(result.content[0].text)
    assert data["error"] == "docling_not_configured"


@pytest.mark.respx(base_url=DOCLING_BASE)
async def test_convert_standard(
    respx_mock: respx.MockRouter, mcp_with_docling: FastMCP, tmp_path: Path
) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    respx_mock.post("/v1/convert/file/async").mock(
        return_value=httpx.Response(200, json={"task_id": "t1"})
    )
    respx_mock.get("/v1/status/poll/t1").mock(
        return_value=httpx.Response(200, json={"task_status": "success"})
    )
    respx_mock.get("/v1/result/t1").mock(
        return_value=httpx.Response(
            200, json={"document": {"md_content": "# Paper\n\nText."}}
        )
    )
    async with Client(mcp_with_docling) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
    data = json.loads(result.content[0].text)
    assert "# Paper" in data["markdown"]
    assert data["vlm_used"] is False
