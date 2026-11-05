"""register_s2_tool's registration contract."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool
from fastmcp_pvl_core import JobsConfig, is_tool_boundary, register_job_tools
from fastmcp_pvl_core._tool_boundary import FAULT_MESSAGE

from scholar_mcp._s2_jobs import register_s2_tool, throttle_reason
from tests.conftest import PlainClient, tasks_server

if TYPE_CHECKING:
    from fastmcp_pvl_core import Jobs


def test_register_s2_tool_applies_tool_boundary(slow_jobs: Jobs) -> None:
    """The registered function carries pvl-core's boundary marker."""
    mcp = FastMCP("t")

    @register_s2_tool(mcp, slow_jobs)
    async def boom() -> dict[str, Any]:
        raise RuntimeError("secret upstream detail")

    tools = asyncio.run(mcp.local_provider.list_tools())
    (tool,) = [t for t in tools if t.name == "boom"]
    assert isinstance(tool, FunctionTool)
    assert is_tool_boundary(tool.fn)


async def test_promoted_s2_failure_reaches_the_poller_as_a_fault(jobs: Jobs) -> None:
    """A body that fails after promotion never leaks its exception text.

    The boundary on the registered wrapper guards the inline path; once the
    body is promoted it finishes inside pvl-core's job record, and the poller
    must get the same fixed fault message, not the RuntimeError's text.
    """
    app = tasks_server("t")

    @register_s2_tool(app, jobs, jobs_config=JobsConfig(soft_deadline_s=0.05))
    async def slow_boom() -> dict[str, Any]:
        await asyncio.sleep(0.2)
        raise RuntimeError("secret upstream detail")

    register_job_tools(app, jobs)

    async with PlainClient(app) as client:
        started = await client.call_tool("slow_boom", {})
        handle = json.loads(started.content[0].text)
        assert handle["status"] == "working"
        for _ in range(40):
            polled = await client.call_tool(
                "get_job_result", {"job_id": handle["job_id"]}, raise_on_error=False
            )
            text = polled.content[0].text
            if polled.is_error or json.loads(text).get("status") != "working":
                break
            await asyncio.sleep(0.05)

    assert "secret upstream detail" not in text
    assert FAULT_MESSAGE in text


def test_throttle_reason_states_what_the_caller_needs() -> None:
    """The deferral tells the caller to keep polling, for how long, and why (#569)."""
    reason = throttle_reason(JobsConfig(result_ttl_s=3600.0))
    assert "Keep polling get_job_result" in reason
    assert "up to about 50 minutes" in reason
    assert "shares one Semantic Scholar rate budget" in reason
    assert "unknown, not empty" in reason


def test_throttle_reason_follows_the_configured_ttl() -> None:
    """The minutes promised track the retry window, with a floor of one."""
    assert "up to about 10 minutes" in throttle_reason(JobsConfig(result_ttl_s=720.0))
    assert "up to about 1 minute." in throttle_reason(JobsConfig(result_ttl_s=1.0))
