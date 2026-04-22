"""Smoke tests for Scholar MCP."""

from __future__ import annotations


def test_make_server_constructs() -> None:
    """make_server() returns a FastMCP instance without raising."""
    from scholar_mcp.server import make_server

    server = make_server()
    assert server is not None
