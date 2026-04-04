"""MCP resource registrations.

TODO: Add your domain resources here.

Resources expose read-only structured data to LLM clients via URI patterns.
See https://gofastmcp.com/servers/resources for the full resource API.

Example::

    @mcp.resource("info://service")
    async def service_info(ctx: Context = Depends(get_service)) -> str:
        return json.dumps({"status": "ok", "version": "1.0"})
"""

from __future__ import annotations

from fastmcp import FastMCP


def register_resources(mcp: FastMCP) -> None:
    """Register all MCP resources on *mcp*.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register resources on.
    """
    # TODO: Add your domain resources here.
