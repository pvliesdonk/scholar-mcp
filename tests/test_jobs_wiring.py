"""Guards for the pvl-core Jobs wiring in `make_server` (#298).

The bespoke `TaskQueue` these tools used to defer to had no persistence, no
per-caller bound, and evicted by age from submission rather than from
completion. Jobs replaces it, and these tests assert the three things that
wiring has to get right and that nothing else checks:

* the shared `Jobs` instance reaches both the tools and the polling tool, so
  a handle a tool hands out is actually redeemable;
* the slow tools are registered dual-mode, which is what finally makes
  `configure_task_backend` (`tests/test_task_backend.py`) reach live work
  rather than an empty queue;
* the operator knobs are read from the environment rather than defaulted.

Behaviour that belongs to pvl-core — promotion mechanics, the handle shape,
subject scoping — is core's to test; what is asserted here is that scholar
reaches it.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.exceptions import ToolError
from fastmcp_pvl_core import (
    JobsConfig,
    ServerConfig,
    build_jobs,
    register_job_tools,
)

from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_patent import register_patent_tools
from scholar_mcp._tools_pdf import register_pdf_tools
from scholar_mcp.config import ProjectConfig
from scholar_mcp.server import make_server

# Every tool that downloads or converts a document — the set that must be
# dual-mode, and the reason a Jobs instance exists on this server at all.
_LONG_RUNNING_TOOLS = {
    "fetch_paper_pdf",
    "convert_pdf_to_markdown",
    "fetch_and_convert",
    "fetch_pdf_by_url",
    "fetch_patent_pdf",
}


async def test_polling_tool_is_registered() -> None:
    """`make_server` exposes pvl-core's generic polling tool."""
    mcp = make_server()
    names = {tool.name for tool in await mcp.list_tools()}
    assert "get_job_result" in names


async def test_long_running_tools_are_task_capable(
    bundle: ServiceBundle,
) -> None:
    """The document-producing tools register `TaskConfig(mode="optional")`.

    This is what stops the SEP-1686 backend being inert: before Jobs, no tool
    anywhere was task-capable, so the queue `SCHOLAR_MCP_TASKS_URL` configures
    never received work. Every tool that can outrun a request is registered
    this way now, so the assertion names the slowest ones rather than trying
    to enumerate the whole surface.
    """
    jobs = build_jobs(ServerConfig(kv_store_url="memory://"), JobsConfig())
    mcp = FastMCP("test")
    register_pdf_tools(mcp, jobs)
    register_patent_tools(mcp, jobs)

    modes = {t.name: t.task_config.mode for t in await mcp.list_tools()}

    for name in _LONG_RUNNING_TOOLS:
        assert modes[name] == "optional", name


def test_jobs_config_is_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """`SCHOLAR_MCP_JOBS_*` reach `ProjectConfig.jobs`.

    Composition rather than restatement is what makes this work — the field
    metadata the config-surface generator reads is core's.
    """
    monkeypatch.setenv("SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S", "3.5")
    monkeypatch.setenv("SCHOLAR_MCP_JOBS_RESULT_TTL_S", "120")
    monkeypatch.setenv("SCHOLAR_MCP_JOBS_MAX_PER_SUBJECT", "7")

    config = ProjectConfig.from_env()

    assert config.jobs.soft_deadline_s == 3.5
    assert config.jobs.result_ttl_s == 120
    assert config.jobs.max_per_subject == 7


def test_jobs_config_defaults_when_unset() -> None:
    """Absent env vars leave core's defaults in place."""
    config = ProjectConfig.from_env()
    assert config.jobs == JobsConfig()


async def test_promoted_conversion_error_survives_to_polling(
    bundle_with_docling: ServiceBundle,
    tmp_path: Path,
) -> None:
    """A promoted conversion's structured error reaches the caller intact.

    `convert_pdf_to_markdown` degrades rather than raising, so the interesting
    case is not a failed job but a completed one whose result is the tool's own
    error payload. Under the bespoke queue a result produced after the TTL
    elapsed was dropped; here it is retained for `JOBS_RESULT_TTL_S` and
    arrives as a native object.
    """
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")

    async def _slow_boom(*args: object, **kwargs: object) -> str:
        await asyncio.sleep(0.2)
        raise RuntimeError("docling exploded")

    bundle_with_docling.docling.convert = _slow_boom  # type: ignore[union-attr,assignment]

    jobs = build_jobs(
        ServerConfig(kv_store_url="memory://"),
        JobsConfig(soft_deadline_s=0.05),
    )

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle_with_docling}

    mcp = FastMCP("test", lifespan=lifespan)
    register_pdf_tools(mcp, jobs)
    register_job_tools(mcp, jobs)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
        handle = json.loads(result.content[0].text)
        assert handle["status"] == "working"

        for _ in range(40):
            polled = await client.call_tool(
                "get_job_result", {"job_id": handle["job_id"]}
            )
            data = json.loads(polled.content[0].text)
            if data["status"] != "working":
                break
            await asyncio.sleep(0.05)

    assert data["status"] == "completed"
    assert data["result"]["error"] == "docling_error"
    assert "docling exploded" in data["result"]["detail"]


async def test_job_cap_rejects_further_promotions(
    bundle_with_docling: ServiceBundle,
    tmp_path,
) -> None:
    """Past `max_per_subject`, a promotion is refused rather than queued.

    A bound the bespoke queue never had: it spawned a task per submission with
    no ceiling. Over stdio every caller collapses to one subject, so the cap is
    a whole-server bound there.
    """
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")

    async def _slow(*args: object, **kwargs: object) -> str:
        await asyncio.sleep(0.3)
        return "# Slow"

    bundle_with_docling.docling.convert = _slow  # type: ignore[union-attr,assignment]

    jobs = build_jobs(
        ServerConfig(kv_store_url="memory://"),
        JobsConfig(soft_deadline_s=0.05, max_per_subject=1),
    )

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle_with_docling}

    mcp = FastMCP("test", lifespan=lifespan)
    register_pdf_tools(mcp, jobs)
    register_job_tools(mcp, jobs)

    async with Client(mcp) as client:
        first = await client.call_tool(
            "convert_pdf_to_markdown", {"file_path": str(pdf)}
        )
        assert json.loads(first.content[0].text)["status"] == "working"

        second = tmp_path / "other.pdf"
        second.write_bytes(b"%PDF fake 2")
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool(
                "convert_pdf_to_markdown", {"file_path": str(second)}
            )

    assert "job" in str(excinfo.value).lower()


async def test_unknown_job_id_is_an_error(bundle: ServiceBundle) -> None:
    """Polling an id this caller does not own is an error, not an empty result.

    Unknown, expired, and another subject's id are deliberately
    indistinguishable, so a job id is not probeable across tenants.
    """
    jobs = build_jobs(ServerConfig(kv_store_url="memory://"), JobsConfig())

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    mcp = FastMCP("test", lifespan=lifespan)
    register_job_tools(mcp, jobs)

    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("get_job_result", {"job_id": "nope"})
