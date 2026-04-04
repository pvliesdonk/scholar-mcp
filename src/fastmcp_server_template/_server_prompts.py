"""MCP prompt registrations.

TODO: Add your domain prompts here.

Prompts provide reusable LLM instruction templates exposed to clients.
Write prompts should be tagged with ``tags={"write"}`` so they are hidden
in read-only mode alongside write tools.

See https://gofastmcp.com/servers/prompts for the full prompt API.
"""

from __future__ import annotations

from fastmcp import FastMCP


def register_prompts(mcp: FastMCP) -> None:
    """Register all MCP prompts on *mcp*.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register prompts on.
    """
    # TODO: Add your domain prompts here.
