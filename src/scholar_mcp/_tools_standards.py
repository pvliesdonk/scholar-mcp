"""Standards search, lookup, and identifier resolution MCP tools."""

from __future__ import annotations

from fastmcp import FastMCP  # noqa: TC002


def register_standards_tools(mcp: FastMCP) -> None:
    """Register standards tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """
