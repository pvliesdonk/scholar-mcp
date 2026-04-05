"""Tests for task polling MCP tools (get_task_result, list_tasks)."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_tasks import register_task_tools


@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_task_tools(app)
    return app


async def test_get_task_result_unknown_id(mcp: FastMCP) -> None:
    """get_task_result returns task_not_found for unknown task_id."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_task_result", {"task_id": "nonexistent123"}
        )
    data = json.loads(result.content[0].text)
    assert data["error"] == "task_not_found"
    assert data["task_id"] == "nonexistent123"


async def test_get_task_result_failed_task(mcp: FastMCP, bundle: ServiceBundle) -> None:
    """get_task_result returns error field when task has failed."""

    async def _failing_coro() -> str:
        raise ValueError("something went wrong")

    task_id = bundle.tasks.submit(_failing_coro())
    # Wait for the background task to finish
    for _ in range(40):
        task = bundle.tasks.get(task_id)
        if task and task.status in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    async with Client(mcp) as client:
        result = await client.call_tool("get_task_result", {"task_id": task_id})
    data = json.loads(result.content[0].text)
    assert data["status"] == "failed"
    assert "something went wrong" in data["error"]


async def test_get_task_result_in_progress_includes_context(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_task_result includes elapsed_seconds, tool, and hint while running."""

    async def _slow_coro() -> str:
        await asyncio.sleep(10)
        return "{}"

    task_id = bundle.tasks.submit(_slow_coro(), tool="convert_pdf_to_markdown")

    async with Client(mcp) as client:
        result = await client.call_tool("get_task_result", {"task_id": task_id})
    data = json.loads(result.content[0].text)
    assert data["status"] in ("pending", "running")
    assert "elapsed_seconds" in data
    assert isinstance(data["elapsed_seconds"], int)
    assert data["tool"] == "convert_pdf_to_markdown"
    assert "hint" in data
    assert "1-5 minutes" in data["hint"]


async def test_get_task_result_no_hint_for_unknown_tool(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_task_result includes elapsed_seconds but no hint for tools without hints."""

    async def _slow_coro() -> str:
        await asyncio.sleep(10)
        return "{}"

    task_id = bundle.tasks.submit(_slow_coro(), tool="search_papers")

    async with Client(mcp) as client:
        result = await client.call_tool("get_task_result", {"task_id": task_id})
    data = json.loads(result.content[0].text)
    assert data["status"] in ("pending", "running")
    assert "elapsed_seconds" in data
    assert data["tool"] == "search_papers"
    assert "hint" not in data


async def test_list_tasks(mcp: FastMCP, bundle: ServiceBundle) -> None:
    """list_tasks returns all active tasks with tool and elapsed_seconds."""

    async def _slow_coro() -> str:
        await asyncio.sleep(10)
        return "{}"

    task_id = bundle.tasks.submit(_slow_coro(), tool="fetch_paper_pdf")

    async with Client(mcp) as client:
        result = await client.call_tool("list_tasks", {})
    data = json.loads(result.content[0].text)
    assert isinstance(data, list)
    assert len(data) >= 1
    task_entry = next(t for t in data if t["task_id"] == task_id)
    assert task_entry["tool"] == "fetch_paper_pdf"
    assert "elapsed_seconds" in task_entry
