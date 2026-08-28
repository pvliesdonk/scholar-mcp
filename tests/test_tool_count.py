"""Gate the tool counts that five documents state by hand.

The number of MCP tools is published in five places -- `README.md` (which
reaches PyPI), the tools reference, the docs landing page, the plugin guide and
the plugin README. Nothing failed when one was missed, which is how 13, 27 and
28 came to coexist (#268). This test makes the registry the source of truth and
the documents its assertions.

The count is taken with every tool visible: EPO credentials present and
read-only off. A read-only instance exposes fewer, and the documents describe
the full surface.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastmcp.client import Client

from scholar_mcp.server import make_server

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Each entry: the file, and a regex whose one capture group is the count.
_DOCUMENTED_COUNTS: dict[str, str] = {
    "README.md": r"^(\d+) tools, organised by scholarly source type\.$",
    "docs/tools/index.md": r"Scholar MCP provides (\d+) tools organised",
    "docs/index.md": r"Scholar MCP exposes (\d+) tools that let",
    "docs/guides/claude-code-plugin.md": r"^(\d+) tools across four scholarly",
    ".claude-plugin/plugin/README.md": r"^(\d+) tools across four scholarly",
}


async def _registered_tool_count(monkeypatch: pytest.MonkeyPatch, tmp: Path) -> int:
    """Count every tool a fully-configured server exposes.

    Args:
        monkeypatch: Used to supply the configuration that unhides everything.
        tmp: Scratch directory for the cache, so no real state is touched.

    Returns:
        The number of tools listed over the protocol.
    """
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp / "cache"))
    monkeypatch.setenv("SCHOLAR_MCP_READ_ONLY", "false")
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", "k")
    monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_SECRET", "s")
    async with Client(make_server()) as client:
        return len(await client.list_tools())


@pytest.mark.parametrize("relative_path", sorted(_DOCUMENTED_COUNTS))
async def test_documented_tool_count_matches_the_registry(
    relative_path: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every document's stated tool count equals the registry's.

    Parametrised per file so a failure names the document that drifted rather
    than the first one checked.
    """
    actual = await _registered_tool_count(monkeypatch, tmp_path)
    pattern = _DOCUMENTED_COUNTS[relative_path]
    text = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")

    match = re.search(pattern, text, re.MULTILINE)
    assert match is not None, (
        f"{relative_path} no longer states a tool count in the expected form "
        f"({pattern!r}). Update the pattern here, or restore the sentence."
    )
    documented = int(match.group(1))
    assert documented == actual, (
        f"{relative_path} says {documented} tools; the server registers "
        f"{actual}. Update the document, or this file if the sentence moved."
    )
