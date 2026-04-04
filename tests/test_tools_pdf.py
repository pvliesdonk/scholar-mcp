"""Tests for fetch_paper_pdf, convert_pdf_to_markdown, fetch_and_convert."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._docling_client import DoclingClient
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_pdf import register_pdf_tools
from scholar_mcp._tools_tasks import register_task_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"
DOCLING_BASE = "http://docling:5001"


@pytest.fixture
def bundle_with_docling(bundle: ServiceBundle, tmp_path: Path) -> ServiceBundle:
    docling_http = httpx.AsyncClient(base_url=DOCLING_BASE, timeout=30.0)
    docling = DoclingClient(
        http_client=docling_http,
        vlm_api_url=None,
        vlm_api_key=None,
        vlm_model="gpt-4o",
    )
    bundle.docling = docling
    return bundle


@pytest.fixture
def mcp_no_docling(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_pdf_tools(app)
    register_task_tools(app)
    return app


@pytest.fixture
def mcp_with_docling(bundle_with_docling: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle_with_docling}

    app = FastMCP("test", lifespan=lifespan)
    register_pdf_tools(app)
    register_task_tools(app)
    return app


async def _poll_task(client: Client, task_id: str, max_attempts: int = 40) -> dict:
    """Poll a queued task until it completes or fails."""
    for _ in range(max_attempts):
        result = await client.call_tool("get_task_result", {"task_id": task_id})
        data = json.loads(result.content[0].text)
        if data["status"] in ("completed", "failed"):
            return data
        await asyncio.sleep(0.05)
    raise TimeoutError(f"task {task_id} did not complete")


@pytest.mark.respx(base_url=S2_BASE)
async def test_fetch_paper_pdf_queued(
    respx_mock: respx.MockRouter, mcp_no_docling: FastMCP
) -> None:
    """fetch_paper_pdf always returns queued response."""
    respx_mock.get("/paper/p1").mock(
        return_value=httpx.Response(
            200, json={"paperId": "p1", "openAccessPdf": None}
        )
    )
    async with Client(mcp_no_docling) as client:
        result = await client.call_tool("fetch_paper_pdf", {"identifier": "p1"})
        queued = json.loads(result.content[0].text)
        assert queued["queued"] is True
        assert queued["tool"] == "fetch_paper_pdf"
        task_data = await _poll_task(client, queued["task_id"])
    assert task_data["status"] == "completed"
    inner = json.loads(task_data["result"])
    assert inner["error"] == "no_oa_pdf"


async def test_convert_no_docling(mcp_no_docling: FastMCP, tmp_path: Path) -> None:
    """convert_pdf_to_markdown returns error immediately when docling not configured."""
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF fake")
    async with Client(mcp_no_docling) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
    data = json.loads(result.content[0].text)
    assert data["error"] == "docling_not_configured"


async def test_convert_standard(
    bundle_with_docling: ServiceBundle, tmp_path: Path
) -> None:
    """convert_pdf_to_markdown queues conversion; result available via polling."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        return_value="# Paper\n\nText."
    )

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle_with_docling}

    app = FastMCP("test", lifespan=lifespan)
    register_pdf_tools(app)
    register_task_tools(app)

    async with Client(app) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
        queued = json.loads(result.content[0].text)
        assert queued["queued"] is True
        task_data = await _poll_task(client, queued["task_id"])
    assert task_data["status"] == "completed"
    inner = json.loads(task_data["result"])
    assert "# Paper" in inner["markdown"]
    assert inner["vlm_used"] is False


async def test_convert_cached_markdown(
    mcp_with_docling: FastMCP, bundle_with_docling: ServiceBundle, tmp_path: Path
) -> None:
    """convert_pdf_to_markdown returns immediately when markdown cached."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    md_dir = bundle_with_docling.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / "paper.md"
    md_path.write_text("# Cached\n\nCached text.", encoding="utf-8")

    async with Client(mcp_with_docling) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
    data = json.loads(result.content[0].text)
    assert "queued" not in data
    assert "# Cached" in data["markdown"]
