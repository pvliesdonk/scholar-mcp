"""Gate the Tool Registration Checklist's metadata requirements.

`CLAUDE.md` requires every registered tool to carry a human-readable
`annotations.title` and accurate behavioural hints. The checklist existed
while two thirds of the surface ignored it (#319), because nothing failed
when a tool was added without one -- the same shape as the tool-count drift
in #268, and the same remedy: make the registry the source of truth and
assert against it.

The enumeration deliberately uses the **full** registry rather than the
client-facing listing. `list_tools()` omits whatever the current
configuration hides -- eight tools disappear in read-only mode with no EPO
credentials -- so a tool registered without a title could sit behind a tag
gate and never be seen. `_list_tools()` returns every registered tool
regardless of gating; it is private API, so if a FastMCP upgrade removes it
the fix is to find the new full-registry accessor, never to fall back to the
filtered listing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp.client import Client
from mcp.types import Tool

from scholar_mcp.server import make_server

# The four tools `make_server` hides together when EPO is unconfigured.
_PATENT_TOOLS = frozenset(
    {"search_patents", "get_patent", "get_citing_patents", "fetch_patent_pdf"}
)


def _configure(monkeypatch: pytest.MonkeyPatch, tmp: Path, *, epo: bool) -> None:
    """Point the server at scratch state and set the visibility inputs.

    Args:
        monkeypatch: Used to supply the environment the server reads.
        tmp: Scratch directory for the cache, so no real state is touched.
        epo: Whether to supply EPO credentials. With them the patent tools
            are visible; without them `make_server` hides the tag.
    """
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp / "cache"))
    monkeypatch.setenv("SCHOLAR_MCP_KV_STORE_URL", "memory://")
    monkeypatch.setenv("SCHOLAR_MCP_READ_ONLY", "false")
    if epo:
        monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", "k")
        monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_SECRET", "s")
    else:
        monkeypatch.delenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", raising=False)
        monkeypatch.delenv("SCHOLAR_MCP_EPO_CONSUMER_SECRET", raising=False)


async def _full_registry(
    monkeypatch: pytest.MonkeyPatch, tmp: Path, *, epo: bool = True
) -> list[Tool]:
    """Return every registered tool, including those the config hides.

    Args:
        monkeypatch: Used to supply the configuration.
        tmp: Scratch directory for the cache.
        epo: Whether to supply EPO credentials.

    Returns:
        Every tool in the registry, gated or not.
    """
    _configure(monkeypatch, tmp, epo=epo)
    return list(await make_server()._list_tools())


async def test_the_full_registry_is_larger_than_the_client_listing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The two enumerations differ, so asserting on the wrong one is silent.

    This is the premise the rest of the module rests on: if `_list_tools`
    ever starts returning only what the configuration exposes, the title
    assertion below stops covering hidden tools without failing.
    """
    _configure(monkeypatch, tmp_path, epo=False)
    mcp = make_server()
    async with Client(mcp) as client:
        visible = {t.name for t in await client.list_tools()}
    registered = {t.name for t in await mcp._list_tools()}
    assert visible < registered, (
        "expected the EPO and write gates to hide part of the registry; "
        "if nothing is hidden this test no longer proves _list_tools is the "
        "unfiltered accessor"
    )
    assert registered - visible >= _PATENT_TOOLS


async def test_every_registered_tool_has_a_title(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every tool carries a non-empty `annotations.title`.

    Title-aware clients (VS Code honours only `title` and `readOnlyHint`)
    otherwise fall back to the raw machine name.
    """
    untitled = sorted(
        t.name
        for t in await _full_registry(monkeypatch, tmp_path)
        if not (t.annotations and (t.annotations.title or "").strip())
    )
    assert not untitled, (
        f"tools without annotations.title: {untitled}. Add a human-readable "
        "title to the tool's annotations dict (see the Tool Registration "
        "Checklist in CLAUDE.md)."
    )


async def test_every_registered_tool_declares_read_only_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every tool states whether it has side effects.

    `readOnlyHint` is the other annotation VS Code reads, and an absent hint
    is not the same claim as `False` -- it says nothing at all.
    """
    unhinted = sorted(
        t.name
        for t in await _full_registry(monkeypatch, tmp_path)
        if not t.annotations or t.annotations.readOnlyHint is None
    )
    assert not unhinted, f"tools without annotations.readOnlyHint: {unhinted}"


async def test_patent_tools_hide_together_when_epo_is_unconfigured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No patent tool is advertised without EPO credentials.

    `fetch_patent_pdf` carried only `tags={"write"}` and so stayed listed
    while its three siblings disappeared, leaving the model a tool that can
    only answer `epo_not_configured` (#316).
    """
    _configure(monkeypatch, tmp_path, epo=False)
    async with Client(make_server()) as client:
        visible = {t.name for t in await client.list_tools()}
    assert not (_PATENT_TOOLS & visible), (
        f"patent tools advertised without EPO credentials: "
        f"{sorted(_PATENT_TOOLS & visible)}"
    )


async def test_patent_tools_appear_together_when_epo_is_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """All four patent tools return once EPO credentials are present.

    The companion to the test above: it proves the gate is what hides them,
    rather than the tools being absent or misnamed.
    """
    _configure(monkeypatch, tmp_path, epo=True)
    async with Client(make_server()) as client:
        visible = {t.name for t in await client.list_tools()}
    assert visible >= _PATENT_TOOLS, (
        f"patent tools missing with EPO configured: {sorted(_PATENT_TOOLS - visible)}"
    )
