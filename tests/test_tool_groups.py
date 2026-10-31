"""Every scholar tool names its reference-page group.

``scripts/gen_reference.py`` writes one page per ``group:<slug>`` tag and
falls back to the registering module's name (``tools_pdf``) without one, so
an untagged tool lands on a page named after a private module.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

_ALL_TOOLS_ENV = {
    "SCHOLAR_MCP_READ_ONLY": "false",
    "SCHOLAR_MCP_EPO_CONSUMER_KEY": "test",
    "SCHOLAR_MCP_EPO_CONSUMER_SECRET": "test",
}

_GROUPS = {
    "papers",
    "citation-graph",
    "recommendations",
    "citations",
    "cross-source",
    "books",
    "standards",
    "patents",
    "full-text",
}


@pytest.mark.parametrize("server", [_ALL_TOOLS_ENV], indirect=True, ids=["all"])
async def test_every_domain_tool_has_one_known_group(server: FastMCP) -> None:
    """Each tool registered from a ``_tools_*`` module carries one group tag."""
    tools = [
        t
        for t in await server.list_tools()
        if getattr(t, "fn", None) is not None
        and t.fn.__module__.startswith("scholar_mcp._tools_")  # type: ignore[attr-defined]
    ]
    assert len(tools) == 27
    for tool in tools:
        groups = {tag.removeprefix("group:") for tag in tool.tags} - set(tool.tags)
        assert len(groups) == 1, (tool.name, sorted(tool.tags))
        assert groups <= _GROUPS, (tool.name, groups)
