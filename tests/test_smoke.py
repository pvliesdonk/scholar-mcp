"""Smoke tests for Scholar MCP."""

from __future__ import annotations

from scholar_mcp.server import make_server


def test_make_server_constructs() -> None:
    """make_server() returns a FastMCP instance without raising."""
    server = make_server()
    assert server is not None
