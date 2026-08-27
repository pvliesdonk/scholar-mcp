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
from fastmcp_pvl_core import (
    Jobs,
    JobsConfig,
    ServerConfig,
    build_jobs,
    register_job_tools,
)

from scholar_mcp._docling_client import DoclingClient
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_pdf import register_pdf_tools

# ---------------------------------------------------------------------------
# DoclingClient.vlm_skip_reason unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "use_vlm, api_url, api_key, expected",
    [
        (False, None, None, None),
        (True, None, None, "vlm_api_url_not_configured"),
        (True, "https://api.openai.com/v1", None, "vlm_api_key_not_configured"),
        (True, "https://api.openai.com/v1", "sk-test", None),
    ],
    ids=["not_requested", "url_missing", "key_missing", "fully_configured"],
)
def test_vlm_skip_reason(
    use_vlm: bool,
    api_url: str | None,
    api_key: str | None,
    expected: str | None,
) -> None:
    """vlm_skip_reason returns the correct reason or None."""
    client = DoclingClient(
        http_client=httpx.AsyncClient(),
        vlm_api_url=api_url,
        vlm_api_key=api_key,
        vlm_model="gpt-4o",
    )
    assert client.vlm_skip_reason(use_vlm) == expected


S2_BASE = "https://api.semanticscholar.org/graph/v1"
DOCLING_BASE = "http://docling:5001"


@pytest.fixture
def mcp_no_docling(bundle: ServiceBundle, jobs: Jobs) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_pdf_tools(app, jobs)
    return app


@pytest.fixture
def mcp_with_docling(bundle_with_docling: ServiceBundle, jobs: Jobs) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle_with_docling}

    app = FastMCP("test", lifespan=lifespan)
    register_pdf_tools(app, jobs)
    return app


async def _poll_job(client: Client, job_id: str, max_attempts: int = 40) -> dict:
    """Poll a promoted job until it reaches a terminal status."""
    for _ in range(max_attempts):
        result = await client.call_tool("get_job_result", {"job_id": job_id})
        data = json.loads(result.content[0].text)
        if data["status"] in ("completed", "failed", "cancelled"):
            return data
        await asyncio.sleep(0.05)
    raise TimeoutError(f"job {job_id} did not settle")


@pytest.mark.respx(base_url=S2_BASE)
async def test_fetch_paper_pdf_no_oa(
    respx_mock: respx.MockRouter, mcp_no_docling: FastMCP
) -> None:
    """fetch_paper_pdf returns no_oa_pdf directly when paper has no OA URL."""
    respx_mock.get("/paper/p1").mock(
        return_value=httpx.Response(
            200,
            json={
                "paperId": "p1",
                "openAccessPdf": None,
                "externalIds": {},
            },
        )
    )
    async with Client(mcp_no_docling) as client:
        result = await client.call_tool("fetch_paper_pdf", {"identifier": "p1"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "no_oa_pdf"


@pytest.mark.respx(base_url=S2_BASE)
async def test_fetch_paper_pdf_promotes_past_soft_deadline(
    respx_mock: respx.MockRouter, bundle: ServiceBundle, jobs: Jobs
) -> None:
    """A download outrunning the soft deadline returns a pollable job handle."""
    respx_mock.get("/paper/p1").mock(
        return_value=httpx.Response(
            200,
            json={
                "paperId": "p1",
                "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                "title": "Test Paper",
            },
        )
    )

    async def _slow_download(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)
        return httpx.Response(200, content=b"%PDF-1.4 slow")

    respx_mock.get("https://example.com/paper.pdf").mock(side_effect=_slow_download)

    # A deadline far below the download time, so promotion is deterministic
    # rather than a race (the recipe in pvl-core's docs/jobs.md).
    jobs = build_jobs(
        ServerConfig(kv_store_url="memory://"),
        JobsConfig(soft_deadline_s=0.05),
    )

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_pdf_tools(app, jobs)
    register_job_tools(app, jobs)

    async with Client(app) as client:
        result = await client.call_tool("fetch_paper_pdf", {"identifier": "p1"})
        handle = json.loads(result.content[0].text)
        assert handle["status"] == "working"
        assert handle["poll_with"] == "get_job_result"

        settled = await _poll_job(client, handle["job_id"])

    assert settled["status"] == "completed"
    # The result is a native object, not a JSON string inside JSON — the
    # double encoding the bespoke queue's get_task_result had.
    assert isinstance(settled["result"], dict)
    assert Path(settled["result"]["path"]).read_bytes() == b"%PDF-1.4 slow"


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
    bundle_with_docling: ServiceBundle, tmp_path: Path, jobs: Jobs
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
    register_pdf_tools(app, jobs)

    async with Client(app) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
        inner = json.loads(result.content[0].text)
    assert "# Paper" in inner["markdown"]
    assert inner["vlm_used"] is False


@pytest.mark.respx(base_url=S2_BASE)
async def test_fetch_paper_pdf_cache_hit(
    respx_mock: respx.MockRouter, mcp_no_docling: FastMCP, bundle: ServiceBundle
) -> None:
    """fetch_paper_pdf returns cached path directly when PDF exists on disk."""
    respx_mock.get("/paper/p1").mock(
        return_value=httpx.Response(
            200,
            json={
                "paperId": "p1",
                "openAccessPdf": {"url": "https://example.com/p.pdf"},
                "title": "Test",
            },
        )
    )
    pdf_dir = bundle.config.cache_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / "p1.pdf"
    pdf_path.write_bytes(b"%PDF cached")

    async with Client(mcp_no_docling) as client:
        result = await client.call_tool("fetch_paper_pdf", {"identifier": "p1"})
    data = json.loads(result.content[0].text)
    assert "queued" not in data
    assert data["path"] == str(pdf_path)
    assert data["source"] == "s2_oa"


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


async def test_convert_cached_markdown_vlm_not_configured(
    mcp_with_docling: FastMCP, bundle_with_docling: ServiceBundle, tmp_path: Path
) -> None:
    """Cache hit with use_vlm=True but VLM not configured includes vlm_skip_reason."""
    # bundle_with_docling has vlm_api_url=None, so VLM is not available.
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    md_dir = bundle_with_docling.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    # Standard cache path (no _vlm suffix — VLM not available so standard is used)
    md_path = md_dir / "paper.md"
    md_path.write_text("# Cached\n\nCached text.", encoding="utf-8")

    async with Client(mcp_with_docling) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf), "use_vlm": True}
        )
    data = json.loads(result.content[0].text)
    assert "queued" not in data
    assert "# Cached" in data["markdown"]
    assert data["vlm_used"] is False
    assert data["vlm_skip_reason"] == "vlm_api_url_not_configured"


async def test_convert_cached_standard_no_vlm_skip_reason(
    mcp_with_docling: FastMCP, bundle_with_docling: ServiceBundle, tmp_path: Path
) -> None:
    """Cache hit with use_vlm=False (default) does NOT include vlm_skip_reason."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    md_dir = bundle_with_docling.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / "paper.md"
    md_path.write_text("# Standard\n\nText.", encoding="utf-8")

    async with Client(mcp_with_docling) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
    data = json.loads(result.content[0].text)
    assert "queued" not in data
    assert "vlm_skip_reason" not in data


async def test_convert_standard_vlm_not_configured_includes_skip_reason(
    bundle_with_docling: ServiceBundle, tmp_path: Path, jobs: Jobs
) -> None:
    """Non-cached conversion with use_vlm=True but VLM not configured includes vlm_skip_reason."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        return_value="# Paper\n\nText."
    )

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle_with_docling}

    app = FastMCP("test", lifespan=lifespan)
    register_pdf_tools(app, jobs)

    async with Client(app) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf), "use_vlm": True}
        )
        inner = json.loads(result.content[0].text)

    assert inner["vlm_used"] is False
    assert inner["vlm_skip_reason"] == "vlm_api_url_not_configured"


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_paper_pdf_download_succeeds(
    bundle: ServiceBundle, jobs: Jobs
) -> None:
    """fetch_paper_pdf downloads PDF when not cached; background task completes."""
    pdf_url = "https://example.com/paper.pdf"
    paper_json = {
        "paperId": "dl1",
        "openAccessPdf": {"url": pdf_url},
        "title": "Download Test",
    }

    # Mock both S2 metadata call and the external PDF download
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{S2_BASE}/paper/dl1").mock(
            return_value=httpx.Response(200, json=paper_json)
        )
        router.get(pdf_url).mock(
            return_value=httpx.Response(200, content=b"%PDF-1.4 fake content")
        )

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle}

        app = FastMCP("test", lifespan=lifespan)
        register_pdf_tools(app, jobs)

        async with Client(app) as client:
            result = await client.call_tool("fetch_paper_pdf", {"identifier": "dl1"})
            inner = json.loads(result.content[0].text)

    assert "path" in inner
    pdf_path = Path(inner["path"])
    assert pdf_path.exists()
    assert pdf_path.read_bytes() == b"%PDF-1.4 fake content"


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_paper_pdf_rate_limited_then_succeeds(
    bundle: ServiceBundle, jobs: Jobs
) -> None:
    """fetch_paper_pdf queues full operation on 429; background retry succeeds."""
    pdf_url = "https://example.com/rl_paper.pdf"
    paper_json = {
        "paperId": "rl1",
        "openAccessPdf": {"url": pdf_url},
        "title": "Rate Limited Paper",
    }

    call_count = 0

    def s2_side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=paper_json)

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{S2_BASE}/paper/rl1").mock(side_effect=s2_side_effect)
        router.get(pdf_url).mock(
            return_value=httpx.Response(200, content=b"%PDF rate limited ok")
        )

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle}

        app = FastMCP("test", lifespan=lifespan)
        register_pdf_tools(app, jobs)

        async with Client(app) as client:
            result = await client.call_tool("fetch_paper_pdf", {"identifier": "rl1"})
            inner = json.loads(result.content[0].text)

    assert "path" in inner
    pdf_path = Path(inner["path"])
    assert pdf_path.exists()
    assert pdf_path.read_bytes() == b"%PDF rate limited ok"


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_paper_pdf_rate_limited_arxiv_fallback(
    bundle: ServiceBundle, jobs: Jobs
) -> None:
    """Rate-limited path fetches externalIds and uses ArXiv fallback."""
    arxiv_pdf_url = "https://arxiv.org/pdf/2301.55555.pdf"
    paper_json = {
        "paperId": "rl_arx",
        "openAccessPdf": None,
        "externalIds": {"ArXiv": "2301.55555"},
        "title": "Rate Limited ArXiv Paper",
    }

    call_count = 0

    def s2_side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=paper_json)

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{S2_BASE}/paper/rl_arx").mock(side_effect=s2_side_effect)
        router.get(arxiv_pdf_url).mock(
            return_value=httpx.Response(200, content=b"%PDF arxiv rl")
        )

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle}

        app = FastMCP("test", lifespan=lifespan)
        register_pdf_tools(app, jobs)

        async with Client(app) as client:
            result = await client.call_tool("fetch_paper_pdf", {"identifier": "rl_arx"})
            inner = json.loads(result.content[0].text)

    assert inner["source"] == "arxiv"
    assert Path(inner["path"]).exists()


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_and_convert_success(
    bundle_with_docling: ServiceBundle, jobs: Jobs
) -> None:
    """fetch_and_convert full pipeline: S2 resolve, PDF download, docling convert."""
    pdf_url = "https://example.com/fc_paper.pdf"
    paper_json = {
        "paperId": "fc1",
        "openAccessPdf": {"url": pdf_url},
        "title": "Fetch and Convert Test",
    }

    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        return_value="# Converted\n\nMarkdown content."
    )

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{S2_BASE}/paper/fc1").mock(
            return_value=httpx.Response(200, json=paper_json)
        )
        router.get(pdf_url).mock(
            return_value=httpx.Response(200, content=b"%PDF-1.4 fc content")
        )

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle_with_docling}

        app = FastMCP("test", lifespan=lifespan)
        register_pdf_tools(app, jobs)

        async with Client(app) as client:
            result = await client.call_tool("fetch_and_convert", {"identifier": "fc1"})
            inner = json.loads(result.content[0].text)

    assert inner["metadata"]["paperId"] == "fc1"
    assert "# Converted" in inner["markdown"]
    assert inner["pdf_path"].endswith("fc1.pdf")
    assert inner["md_path"].endswith("fc1.md")
    assert inner["vlm_used"] is False
    assert inner["pdf_source"] == "s2_oa"


# ---------------------------------------------------------------------------
# Alternative PDF resolution tests
# ---------------------------------------------------------------------------


@pytest.mark.respx(base_url=S2_BASE)
async def test_fetch_paper_pdf_arxiv_fallback(
    respx_mock: respx.MockRouter, bundle: ServiceBundle, jobs: Jobs
) -> None:
    """fetch_paper_pdf falls back to arXiv when openAccessPdf is null."""
    arxiv_pdf_url = "https://arxiv.org/pdf/2301.12345.pdf"
    paper_json = {
        "paperId": "arx1",
        "openAccessPdf": None,
        "externalIds": {"ArXiv": "2301.12345"},
        "title": "ArXiv Fallback Test",
    }

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{S2_BASE}/paper/arx1").mock(
            return_value=httpx.Response(200, json=paper_json)
        )
        router.get(arxiv_pdf_url).mock(
            return_value=httpx.Response(200, content=b"%PDF arxiv content")
        )

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle}

        app = FastMCP("test", lifespan=lifespan)
        register_pdf_tools(app, jobs)

        async with Client(app) as client:
            result = await client.call_tool("fetch_paper_pdf", {"identifier": "arx1"})
            inner = json.loads(result.content[0].text)

    assert "path" in inner
    assert inner["source"] == "arxiv"
    assert Path(inner["path"]).exists()


@pytest.mark.respx(base_url=S2_BASE)
async def test_fetch_and_convert_arxiv_fallback(
    bundle_with_docling: ServiceBundle, jobs: Jobs
) -> None:
    """fetch_and_convert uses arXiv fallback and reports pdf_source."""
    arxiv_pdf_url = "https://arxiv.org/pdf/2301.99999.pdf"
    paper_json = {
        "paperId": "fca1",
        "openAccessPdf": None,
        "externalIds": {"ArXiv": "2301.99999"},
        "title": "Fetch and Convert ArXiv Test",
    }

    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        return_value="# ArXiv Paper\n\nContent."
    )

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{S2_BASE}/paper/fca1").mock(
            return_value=httpx.Response(200, json=paper_json)
        )
        router.get(arxiv_pdf_url).mock(
            return_value=httpx.Response(200, content=b"%PDF arxiv fc")
        )

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle_with_docling}

        app = FastMCP("test", lifespan=lifespan)
        register_pdf_tools(app, jobs)

        async with Client(app) as client:
            result = await client.call_tool("fetch_and_convert", {"identifier": "fca1"})
            inner = json.loads(result.content[0].text)

    assert inner["pdf_source"] == "arxiv"
    assert "# ArXiv Paper" in inner["markdown"]


# ---------------------------------------------------------------------------
# fetch_pdf_by_url tests
# ---------------------------------------------------------------------------


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_pdf_by_url_download_and_convert(
    bundle_with_docling: ServiceBundle, jobs: Jobs
) -> None:
    """fetch_pdf_by_url downloads a PDF and converts to markdown."""
    pdf_url = "https://example.com/custom/paper.pdf"

    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        return_value="# Custom Paper\n\nFrom URL."
    )

    with respx.mock(assert_all_called=False) as router:
        router.get(pdf_url).mock(
            return_value=httpx.Response(200, content=b"%PDF custom")
        )

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle_with_docling}

        app = FastMCP("test", lifespan=lifespan)
        register_pdf_tools(app, jobs)

        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_pdf_by_url",
                {"url": pdf_url, "filename": "custom_paper"},
            )
            inner = json.loads(result.content[0].text)

    assert inner["pdf_path"].endswith("custom_paper.pdf")
    assert "# Custom Paper" in inner["markdown"]
    assert inner["vlm_used"] is False


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_pdf_by_url_no_docling(bundle: ServiceBundle, jobs: Jobs) -> None:
    """fetch_pdf_by_url without docling returns just the pdf_path."""
    pdf_url = "https://example.com/nodocling.pdf"

    with respx.mock(assert_all_called=False) as router:
        router.get(pdf_url).mock(
            return_value=httpx.Response(200, content=b"%PDF no docling")
        )

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle}

        app = FastMCP("test", lifespan=lifespan)
        register_pdf_tools(app, jobs)

        async with Client(app) as client:
            result = await client.call_tool("fetch_pdf_by_url", {"url": pdf_url})
            inner = json.loads(result.content[0].text)

    assert "pdf_path" in inner
    assert "markdown" not in inner


async def test_fetch_pdf_by_url_cached(bundle: ServiceBundle, jobs: Jobs) -> None:
    """fetch_pdf_by_url returns cached path immediately."""
    pdf_dir = bundle.config.cache_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    cached = pdf_dir / "cached_paper.pdf"
    cached.write_bytes(b"%PDF cached")

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_pdf_tools(app, jobs)

    async with Client(app) as client:
        result = await client.call_tool(
            "fetch_pdf_by_url",
            {"url": "https://example.com/cached_paper.pdf", "filename": "cached_paper"},
        )
    data = json.loads(result.content[0].text)
    assert "queued" not in data
    assert data["pdf_path"] == str(cached)


def test_fetch_pdf_by_url_intercepts_epo_url(mcp_no_docling: FastMCP) -> None:
    """fetch_pdf_by_url returns helpful error for EPO OPS URLs."""

    async def run() -> dict:
        async with Client(mcp_no_docling) as client:
            result = await client.call_tool(
                "fetch_pdf_by_url",
                {
                    "url": "https://ops.epo.org/rest-services/published-data/publication/epodoc/EP3491801B1/fulltext/pdf"
                },
            )
        return json.loads(result.content[0].text)

    data = asyncio.run(run())
    assert "error" in data
    assert "fetch_patent_pdf" in str(data).lower() or "epo" in str(data).lower()
