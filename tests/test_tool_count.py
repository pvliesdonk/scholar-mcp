"""Gate the tool counts that three documents state by hand.

The number of MCP tools is published in three places -- `README.md` (which
reaches PyPI), the docs landing page and the plugin README.
The generated tools reference lists the registry itself, so it needs no gate. Nothing failed when one was missed, which is how 13, 27 and
28 came to coexist (#268). This test makes the registry the source of truth and
the documents its assertions.

The count is taken with every tool visible: EPO credentials present and
read-only off. A read-only instance exposes fewer, and the documents describe
the full surface. That surface depends on the transport: `create_upload_link`
exists only over HTTP with a public base URL (#546), so the README and the
landing page count an HTTP server, and the plugin README, whose server runs
over stdio, counts a stdio one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP

from scholar_mcp.server import make_server

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Each entry: the file, a regex whose one capture group is the count, and the
# transport the document's readers run the server on.
_DOCUMENTED_COUNTS: dict[str, tuple[str, str]] = {
    "README.md": (r"^(\d+) tools, organised by scholarly source type\.$", "http"),
    "docs/index.md": (r"Scholar MCP exposes (\d+) tools that let", "http"),
    ".claude-plugin/plugin/README.md": (r"^(\d+) tools across four scholarly", "stdio"),
}

# The configuration that unhides everything.  BASE_URL only matters over HTTP,
# where it is what wires create_upload_link.
_EVERYTHING_VISIBLE = {
    "SCHOLAR_MCP_READ_ONLY": "false",
    "SCHOLAR_MCP_EPO_CONSUMER_KEY": "k",
    "SCHOLAR_MCP_EPO_CONSUMER_SECRET": "s",
    "SCHOLAR_MCP_BASE_URL": "https://mcp.test",
}


@pytest.fixture(params=sorted(_DOCUMENTED_COUNTS))
def documented(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[str, FastMCP]:
    """A document and a server built, synchronously, on its readers' transport.

    Built here rather than in the test body so an async test never calls
    ``make_server()`` inside the running loop (#338).
    """
    relative_path: str = request.param
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp_path / "cache"))
    for key, value in _EVERYTHING_VISIBLE.items():
        monkeypatch.setenv(key, value)
    transport = _DOCUMENTED_COUNTS[relative_path][1]
    return relative_path, make_server(transport=transport, configure_logging=False)


async def test_documented_tool_count_matches_the_registry(
    documented: tuple[str, FastMCP],
) -> None:
    """Every document's stated tool count equals the registry's.

    Parametrised per file so a failure names the document that drifted rather
    than the first one checked.
    """
    relative_path, server = documented
    async with Client(server) as client:
        actual = len(await client.list_tools())
    pattern = _DOCUMENTED_COUNTS[relative_path][0]
    text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
    match = re.search(pattern, text, re.MULTILINE)
    assert match is not None, (
        f"{relative_path} no longer states a tool count in the expected form "
        f"({pattern!r}). Update the pattern here, or restore the sentence."
    )
    documented_count = int(match.group(1))
    assert documented_count == actual, (
        f"{relative_path} says {documented_count} tools; the server registers "
        f"{actual}. Update the document, or this file if the sentence moved."
    )
