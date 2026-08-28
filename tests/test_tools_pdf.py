"""Tests for the PDF tools, which run on the pvl-core jobs framework.

Every tool here is registered with ``register_long_running_tool``, so the
same call answers two ways depending on how long the work takes.  Tests pick
the branch they mean with a fixture rather than by sleeping:

- ``slow_jobs`` (30s deadline) — mocked work finishes well inside the window,
  so the tool returns its own result inline. Most tests want this.
- ``jobs`` (0.05s deadline) — work that awaits anything at all misses the
  window and is promoted, so the caller gets a ``JobHandle`` and polls
  ``get_job_result``. The promotion tests at the end want this.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp_pvl_core import Jobs, register_job_tools

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


def pdf_app(bundle: ServiceBundle, jobs: Jobs) -> FastMCP:
    """Build a FastMCP app exposing the PDF tools and the job poller.

    ``register_job_tools`` is registered alongside because a promoted handle
    is only resolvable through it.

    Args:
        bundle: Service bundle yielded from the app's lifespan.
        jobs: Jobs mechanics the PDF tools register against.

    Returns:
        The configured :class:`FastMCP` instance.
    """

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_pdf_tools(app, jobs)
    register_job_tools(app, jobs)
    return app


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
def mcp_no_docling(bundle: ServiceBundle, slow_jobs: Jobs) -> FastMCP:
    return pdf_app(bundle, slow_jobs)


@pytest.fixture
def mcp_with_docling(bundle_with_docling: ServiceBundle, slow_jobs: Jobs) -> FastMCP:
    return pdf_app(bundle_with_docling, slow_jobs)


async def _poll_job(
    client: Client, job_id: str, max_attempts: int = 40
) -> dict[str, Any]:
    """Poll ``get_job_result`` until the job reaches a terminal status.

    Args:
        client: Connected FastMCP client.
        job_id: Identifier from the tool's job handle.
        max_attempts: Polls before giving up.

    Returns:
        The terminal polling payload.

    Raises:
        TimeoutError: If the job never settles.
    """
    for _ in range(max_attempts):
        result = await client.call_tool("get_job_result", {"job_id": job_id})
        data = json.loads(result.content[0].text)
        if data["status"] in ("completed", "failed"):
            return data
        await asyncio.sleep(0.05)
    raise TimeoutError(f"job {job_id} did not complete")


def _assert_inline(data: dict[str, Any]) -> None:
    """Assert a payload is a real result, not a job handle.

    Args:
        data: The decoded tool response.
    """
    assert "job_id" not in data, f"expected an inline result, got a handle: {data}"


# ---------------------------------------------------------------------------
# fetch_paper_pdf
# ---------------------------------------------------------------------------


@pytest.mark.respx(base_url=S2_BASE)
async def test_fetch_paper_pdf_no_oa(
    respx_mock: respx.MockRouter, mcp_no_docling: FastMCP
) -> None:
    """fetch_paper_pdf returns no_oa_pdf when the paper has no OA URL."""
    respx_mock.get("/paper/p1").mock(
        return_value=httpx.Response(
            200,
            json={"paperId": "p1", "openAccessPdf": None, "externalIds": {}},
        )
    )
    async with Client(mcp_no_docling) as client:
        result = await client.call_tool("fetch_paper_pdf", {"identifier": "p1"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "no_oa_pdf"


@pytest.mark.respx(base_url=S2_BASE)
async def test_fetch_paper_pdf_cache_hit(
    respx_mock: respx.MockRouter, mcp_no_docling: FastMCP, bundle: ServiceBundle
) -> None:
    """fetch_paper_pdf returns the cached path when the PDF exists on disk."""
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
    _assert_inline(data)
    assert data["path"] == str(pdf_path)
    assert data["source"] == "s2_oa"


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_paper_pdf_download_succeeds(
    bundle: ServiceBundle, slow_jobs: Jobs
) -> None:
    """fetch_paper_pdf downloads the PDF when it is not cached."""
    pdf_url = "https://example.com/paper.pdf"
    paper_json = {
        "paperId": "dl1",
        "openAccessPdf": {"url": pdf_url},
        "title": "Download Test",
    }

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{S2_BASE}/paper/dl1").mock(
            return_value=httpx.Response(200, json=paper_json)
        )
        router.get(pdf_url).mock(
            return_value=httpx.Response(200, content=b"%PDF-1.4 fake content")
        )
        async with Client(pdf_app(bundle, slow_jobs)) as client:
            result = await client.call_tool("fetch_paper_pdf", {"identifier": "dl1"})

    data = json.loads(result.content[0].text)
    _assert_inline(data)
    pdf_path = Path(data["path"])
    assert pdf_path.exists()
    assert pdf_path.read_bytes() == b"%PDF-1.4 fake content"


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_paper_pdf_rate_limited_then_succeeds(
    bundle: ServiceBundle, slow_jobs: Jobs
) -> None:
    """A 429 is absorbed by the client's own backoff, not by a queue hop.

    The tool always calls with retries enabled now, so a transient 429 is
    retried inside the coroutine and the caller still gets its result.
    """
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
        async with Client(pdf_app(bundle, slow_jobs)) as client:
            result = await client.call_tool("fetch_paper_pdf", {"identifier": "rl1"})

    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert call_count >= 2, "expected the 429 to be retried"
    assert Path(data["path"]).read_bytes() == b"%PDF rate limited ok"


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_paper_pdf_arxiv_fallback(
    bundle: ServiceBundle, slow_jobs: Jobs
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
        async with Client(pdf_app(bundle, slow_jobs)) as client:
            result = await client.call_tool("fetch_paper_pdf", {"identifier": "arx1"})

    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert data["source"] == "arxiv"
    assert Path(data["path"]).exists()


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_paper_pdf_rate_limited_arxiv_fallback(
    bundle: ServiceBundle, slow_jobs: Jobs
) -> None:
    """A retried metadata fetch still reaches the arXiv fallback."""
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
        async with Client(pdf_app(bundle, slow_jobs)) as client:
            result = await client.call_tool("fetch_paper_pdf", {"identifier": "rl_arx"})

    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert data["source"] == "arxiv"
    assert Path(data["path"]).exists()


@pytest.mark.respx(base_url=S2_BASE)
async def test_fetch_paper_pdf_upstream_error(
    respx_mock: respx.MockRouter, mcp_no_docling: FastMCP
) -> None:
    """A non-404 upstream failure returns the generic S2 error payload."""
    respx_mock.get("/paper/boom").mock(return_value=httpx.Response(500))
    async with Client(mcp_no_docling) as client:
        result = await client.call_tool("fetch_paper_pdf", {"identifier": "boom"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "upstream_error"
    assert data["status"] == 500


@pytest.mark.respx(base_url=S2_BASE)
async def test_fetch_paper_pdf_not_found(
    respx_mock: respx.MockRouter, mcp_no_docling: FastMCP
) -> None:
    """A 404 from S2 is reported as not_found rather than an upstream error."""
    respx_mock.get("/paper/missing").mock(return_value=httpx.Response(404))
    async with Client(mcp_no_docling) as client:
        result = await client.call_tool("fetch_paper_pdf", {"identifier": "missing"})
    data = json.loads(result.content[0].text)
    assert data == {"error": "not_found", "identifier": "missing"}


# ---------------------------------------------------------------------------
# convert_pdf_to_markdown
# ---------------------------------------------------------------------------


async def test_convert_no_docling(mcp_no_docling: FastMCP, tmp_path: Path) -> None:
    """convert_pdf_to_markdown errors when docling is not configured."""
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF fake")
    async with Client(mcp_no_docling) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
    data = json.loads(result.content[0].text)
    assert data["error"] == "docling_not_configured"


async def test_convert_missing_file(mcp_with_docling: FastMCP, tmp_path: Path) -> None:
    """convert_pdf_to_markdown errors when the PDF is not on disk."""
    missing = tmp_path / "absent.pdf"
    async with Client(mcp_with_docling) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(missing)}
        )
    data = json.loads(result.content[0].text)
    assert data == {"error": "file_not_found", "path": str(missing)}


async def test_convert_standard(
    bundle_with_docling: ServiceBundle, tmp_path: Path, slow_jobs: Jobs
) -> None:
    """convert_pdf_to_markdown converts and returns the markdown."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        return_value="# Paper\n\nText."
    )

    async with Client(pdf_app(bundle_with_docling, slow_jobs)) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )

    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert "# Paper" in data["markdown"]
    assert data["vlm_used"] is False


async def test_convert_docling_failure(
    bundle_with_docling: ServiceBundle, tmp_path: Path, slow_jobs: Jobs
) -> None:
    """A docling failure inside the deadline is reported as docling_error."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        side_effect=RuntimeError("converter exploded")
    )

    async with Client(pdf_app(bundle_with_docling, slow_jobs)) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )

    data = json.loads(result.content[0].text)
    assert data["error"] == "docling_error"
    assert "converter exploded" in data["detail"]


async def test_convert_cached_markdown(
    mcp_with_docling: FastMCP, bundle_with_docling: ServiceBundle, tmp_path: Path
) -> None:
    """convert_pdf_to_markdown returns cached markdown without converting."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    md_dir = bundle_with_docling.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    (md_dir / "paper.md").write_text("# Cached\n\nCached text.", encoding="utf-8")

    async with Client(mcp_with_docling) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert "# Cached" in data["markdown"]


async def test_convert_cached_markdown_vlm_not_configured(
    mcp_with_docling: FastMCP, bundle_with_docling: ServiceBundle, tmp_path: Path
) -> None:
    """Cache hit with use_vlm=True but VLM unconfigured reports vlm_skip_reason."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    md_dir = bundle_with_docling.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    # Standard cache path (no _vlm suffix — VLM not available so standard is used)
    (md_dir / "paper.md").write_text("# Cached\n\nCached text.", encoding="utf-8")

    async with Client(mcp_with_docling) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf), "use_vlm": True}
        )
    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert "# Cached" in data["markdown"]
    assert data["vlm_used"] is False
    assert data["vlm_skip_reason"] == "vlm_api_url_not_configured"


async def test_convert_cached_standard_no_vlm_skip_reason(
    mcp_with_docling: FastMCP, bundle_with_docling: ServiceBundle, tmp_path: Path
) -> None:
    """Cache hit with use_vlm=False (default) omits vlm_skip_reason."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    md_dir = bundle_with_docling.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)
    (md_dir / "paper.md").write_text("# Standard\n\nText.", encoding="utf-8")

    async with Client(mcp_with_docling) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert "vlm_skip_reason" not in data


async def test_convert_standard_vlm_not_configured_includes_skip_reason(
    bundle_with_docling: ServiceBundle, tmp_path: Path, slow_jobs: Jobs
) -> None:
    """A fresh conversion with use_vlm=True but VLM unconfigured reports the reason."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        return_value="# Paper\n\nText."
    )

    async with Client(pdf_app(bundle_with_docling, slow_jobs)) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf), "use_vlm": True}
        )

    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert data["vlm_used"] is False
    assert data["vlm_skip_reason"] == "vlm_api_url_not_configured"


# ---------------------------------------------------------------------------
# fetch_and_convert
# ---------------------------------------------------------------------------


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_and_convert_success(
    bundle_with_docling: ServiceBundle, slow_jobs: Jobs
) -> None:
    """fetch_and_convert resolves, downloads and converts in one call."""
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
        async with Client(pdf_app(bundle_with_docling, slow_jobs)) as client:
            result = await client.call_tool("fetch_and_convert", {"identifier": "fc1"})

    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert data["metadata"]["paperId"] == "fc1"
    assert "# Converted" in data["markdown"]
    assert data["pdf_path"].endswith("fc1.pdf")
    assert data["md_path"].endswith("fc1.md")
    assert data["vlm_used"] is False
    assert data["pdf_source"] == "s2_oa"


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_and_convert_arxiv_fallback(
    bundle_with_docling: ServiceBundle, slow_jobs: Jobs
) -> None:
    """fetch_and_convert uses the arXiv fallback and reports pdf_source."""
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
        async with Client(pdf_app(bundle_with_docling, slow_jobs)) as client:
            result = await client.call_tool("fetch_and_convert", {"identifier": "fca1"})

    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert data["pdf_source"] == "arxiv"
    assert "# ArXiv Paper" in data["markdown"]


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_and_convert_no_docling(
    bundle: ServiceBundle, slow_jobs: Jobs
) -> None:
    """fetch_and_convert still returns metadata and the PDF without docling."""
    pdf_url = "https://example.com/nd_paper.pdf"
    paper_json = {
        "paperId": "nd1",
        "openAccessPdf": {"url": pdf_url},
        "title": "No Docling",
    }

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{S2_BASE}/paper/nd1").mock(
            return_value=httpx.Response(200, json=paper_json)
        )
        router.get(pdf_url).mock(return_value=httpx.Response(200, content=b"%PDF nd"))
        async with Client(pdf_app(bundle, slow_jobs)) as client:
            result = await client.call_tool("fetch_and_convert", {"identifier": "nd1"})

    data = json.loads(result.content[0].text)
    assert data["error"] == "docling_not_configured"
    assert data["metadata"]["paperId"] == "nd1"
    assert Path(data["pdf_path"]).exists()


# ---------------------------------------------------------------------------
# fetch_pdf_by_url
# ---------------------------------------------------------------------------


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_pdf_by_url_download_and_convert(
    bundle_with_docling: ServiceBundle, slow_jobs: Jobs
) -> None:
    """fetch_pdf_by_url downloads a PDF and converts it to markdown."""
    pdf_url = "https://example.com/custom/paper.pdf"
    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        return_value="# Custom Paper\n\nFrom URL."
    )

    with respx.mock(assert_all_called=False) as router:
        router.get(pdf_url).mock(
            return_value=httpx.Response(200, content=b"%PDF custom")
        )
        async with Client(pdf_app(bundle_with_docling, slow_jobs)) as client:
            result = await client.call_tool(
                "fetch_pdf_by_url",
                {"url": pdf_url, "filename": "custom_paper"},
            )

    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert data["pdf_path"].endswith("custom_paper.pdf")
    assert "# Custom Paper" in data["markdown"]
    assert data["vlm_used"] is False


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_pdf_by_url_no_docling(
    bundle: ServiceBundle, slow_jobs: Jobs
) -> None:
    """fetch_pdf_by_url without docling returns just the pdf_path."""
    pdf_url = "https://example.com/nodocling.pdf"

    with respx.mock(assert_all_called=False) as router:
        router.get(pdf_url).mock(
            return_value=httpx.Response(200, content=b"%PDF no docling")
        )
        async with Client(pdf_app(bundle, slow_jobs)) as client:
            result = await client.call_tool("fetch_pdf_by_url", {"url": pdf_url})

    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert "pdf_path" in data
    assert "markdown" not in data


async def test_fetch_pdf_by_url_cached(bundle: ServiceBundle, slow_jobs: Jobs) -> None:
    """fetch_pdf_by_url returns the cached path without re-downloading."""
    pdf_dir = bundle.config.cache_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    cached = pdf_dir / "cached_paper.pdf"
    cached.write_bytes(b"%PDF cached")

    async with Client(pdf_app(bundle, slow_jobs)) as client:
        result = await client.call_tool(
            "fetch_pdf_by_url",
            {"url": "https://example.com/cached_paper.pdf", "filename": "cached_paper"},
        )
    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert data["pdf_path"] == str(cached)


async def test_fetch_pdf_by_url_intercepts_epo_url(mcp_no_docling: FastMCP) -> None:
    """fetch_pdf_by_url returns a helpful error for EPO OPS URLs."""
    async with Client(mcp_no_docling) as client:
        result = await client.call_tool(
            "fetch_pdf_by_url",
            {
                "url": (
                    "https://ops.epo.org/rest-services/published-data/"
                    "publication/epodoc/EP3491801B1/fulltext/pdf"
                )
            },
        )
    data = json.loads(result.content[0].text)
    assert data["error"] == "use_fetch_patent_pdf"
    assert "fetch_patent_pdf" in data["detail"]


# ---------------------------------------------------------------------------
# Promotion: the same tools under a soft deadline they cannot meet
# ---------------------------------------------------------------------------


async def test_slow_conversion_is_promoted_and_polled(
    bundle_with_docling: ServiceBundle, tmp_path: Path, jobs: Jobs
) -> None:
    """Work past the deadline returns a handle whose result arrives by polling."""
    pdf = tmp_path / "slow.pdf"
    pdf.write_bytes(b"%PDF fake")

    async def slow_convert(*args: object, **kwargs: object) -> str:
        await asyncio.sleep(0.2)
        return "# Slow\n\nConverted late."

    bundle_with_docling.docling.convert = slow_convert  # type: ignore[union-attr,assignment]

    async with Client(pdf_app(bundle_with_docling, jobs)) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
        handle = json.loads(result.content[0].text)
        assert handle["status"] == "working"
        assert handle["poll_with"] == "get_job_result"
        assert handle["retry_after_s"] > 0
        assert "convert_pdf_to_markdown" in handle["message"]

        settled = await _poll_job(client, handle["job_id"])

    assert settled["status"] == "completed"
    assert "# Slow" in settled["result"]["markdown"]


async def test_cache_hit_answers_inline_even_under_a_short_deadline(
    mcp_no_docling: FastMCP, bundle: ServiceBundle, jobs: Jobs
) -> None:
    """A cache hit mints no job: there is nothing slow to promote.

    This is the behaviour that replaces the old always-queue branching — the
    fast path is fast because it finishes, not because the tool special-cases
    it.
    """
    pdf_dir = bundle.config.cache_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    cached = pdf_dir / "quick.pdf"
    cached.write_bytes(b"%PDF cached")

    async with Client(pdf_app(bundle, jobs)) as client:
        result = await client.call_tool(
            "fetch_pdf_by_url",
            {"url": "https://example.com/quick.pdf", "filename": "quick"},
        )
    data = json.loads(result.content[0].text)
    _assert_inline(data)
    assert data["pdf_path"] == str(cached)


async def test_unknown_job_id_is_an_error(mcp_no_docling: FastMCP) -> None:
    """Polling an id that never existed fails rather than inventing a result."""
    async with Client(mcp_no_docling) as client:
        result = await client.call_tool(
            "get_job_result", {"job_id": "nope"}, raise_on_error=False
        )
    assert result.is_error


# ---------------------------------------------------------------------------
# Failure branches
# ---------------------------------------------------------------------------


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_paper_pdf_download_failure(
    bundle: ServiceBundle, slow_jobs: Jobs
) -> None:
    """A failed download is reported rather than raised."""
    pdf_url = "https://example.com/broken.pdf"
    paper_json = {
        "paperId": "brk1",
        "openAccessPdf": {"url": pdf_url},
        "title": "Broken",
    }

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{S2_BASE}/paper/brk1").mock(
            return_value=httpx.Response(200, json=paper_json)
        )
        router.get(pdf_url).mock(return_value=httpx.Response(503))
        async with Client(pdf_app(bundle, slow_jobs)) as client:
            result = await client.call_tool("fetch_paper_pdf", {"identifier": "brk1"})

    data = json.loads(result.content[0].text)
    assert data["error"] == "download_failed"
    assert data["detail"]


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_and_convert_download_failure(
    bundle_with_docling: ServiceBundle, slow_jobs: Jobs
) -> None:
    """fetch_and_convert still returns metadata when the download fails."""
    pdf_url = "https://example.com/fc_broken.pdf"
    paper_json = {
        "paperId": "fcb1",
        "openAccessPdf": {"url": pdf_url},
        "title": "FC Broken",
    }

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{S2_BASE}/paper/fcb1").mock(
            return_value=httpx.Response(200, json=paper_json)
        )
        router.get(pdf_url).mock(return_value=httpx.Response(503))
        async with Client(pdf_app(bundle_with_docling, slow_jobs)) as client:
            result = await client.call_tool("fetch_and_convert", {"identifier": "fcb1"})

    data = json.loads(result.content[0].text)
    assert data["error"] == "download_failed"
    assert data["metadata"]["paperId"] == "fcb1"
    assert data["pdf_source"] == "s2_oa"


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_and_convert_conversion_failure(
    bundle_with_docling: ServiceBundle, slow_jobs: Jobs
) -> None:
    """A docling failure leaves the downloaded PDF reachable."""
    pdf_url = "https://example.com/fc_conv.pdf"
    paper_json = {
        "paperId": "fcc1",
        "openAccessPdf": {"url": pdf_url},
        "title": "FC Conv",
    }
    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        side_effect=RuntimeError("boom")
    )

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{S2_BASE}/paper/fcc1").mock(
            return_value=httpx.Response(200, json=paper_json)
        )
        router.get(pdf_url).mock(return_value=httpx.Response(200, content=b"%PDF conv"))
        async with Client(pdf_app(bundle_with_docling, slow_jobs)) as client:
            result = await client.call_tool("fetch_and_convert", {"identifier": "fcc1"})

    data = json.loads(result.content[0].text)
    assert data["error"] == "conversion_failed"
    assert Path(data["pdf_path"]).exists()


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_and_convert_no_oa_pdf(
    bundle_with_docling: ServiceBundle, slow_jobs: Jobs
) -> None:
    """fetch_and_convert reports no_oa_pdf alongside the metadata it did get."""
    paper_json = {"paperId": "noa1", "openAccessPdf": None, "externalIds": {}}

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{S2_BASE}/paper/noa1").mock(
            return_value=httpx.Response(200, json=paper_json)
        )
        async with Client(pdf_app(bundle_with_docling, slow_jobs)) as client:
            result = await client.call_tool("fetch_and_convert", {"identifier": "noa1"})

    data = json.loads(result.content[0].text)
    assert data["error"] == "no_oa_pdf"
    assert data["metadata"]["paperId"] == "noa1"


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_pdf_by_url_download_failure(
    bundle: ServiceBundle, slow_jobs: Jobs
) -> None:
    """fetch_pdf_by_url reports a failed download."""
    pdf_url = "https://example.com/url_broken.pdf"

    with respx.mock(assert_all_called=False) as router:
        router.get(pdf_url).mock(return_value=httpx.Response(404))
        async with Client(pdf_app(bundle, slow_jobs)) as client:
            result = await client.call_tool("fetch_pdf_by_url", {"url": pdf_url})

    data = json.loads(result.content[0].text)
    assert data["error"] == "download_failed"


@pytest.mark.respx(assert_all_called=False)
async def test_fetch_pdf_by_url_conversion_failure(
    bundle_with_docling: ServiceBundle, slow_jobs: Jobs
) -> None:
    """fetch_pdf_by_url reports a conversion failure but keeps the PDF path."""
    pdf_url = "https://example.com/url_conv.pdf"
    bundle_with_docling.docling.convert = AsyncMock(  # type: ignore[union-attr]
        side_effect=RuntimeError("boom")
    )

    with respx.mock(assert_all_called=False) as router:
        router.get(pdf_url).mock(return_value=httpx.Response(200, content=b"%PDF conv"))
        async with Client(pdf_app(bundle_with_docling, slow_jobs)) as client:
            result = await client.call_tool(
                "fetch_pdf_by_url", {"url": pdf_url, "filename": "url_conv"}
            )

    data = json.loads(result.content[0].text)
    assert data["error"] == "conversion_failed"
    assert Path(data["pdf_path"]).exists()


async def test_fetch_pdf_by_url_derives_stem_from_url(
    bundle: ServiceBundle, slow_jobs: Jobs
) -> None:
    """Without an explicit filename the stem is derived and hash-suffixed."""
    pdf_url = "https://example.com/deep/path/report.pdf"

    with respx.mock(assert_all_called=False) as router:
        router.get(pdf_url).mock(
            return_value=httpx.Response(200, content=b"%PDF derived")
        )
        async with Client(pdf_app(bundle, slow_jobs)) as client:
            result = await client.call_tool("fetch_pdf_by_url", {"url": pdf_url})

    data = json.loads(result.content[0].text)
    stem = Path(data["pdf_path"]).stem
    assert stem.startswith("report_")
    assert len(stem) == len("report_") + 8
