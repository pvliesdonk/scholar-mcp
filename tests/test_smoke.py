"""Smoke tests for Scholar MCP."""

from __future__ import annotations

import pytest

from scholar_mcp.server import make_server

_IDENTITY = (
    "Scholar MCP — academic literature server: Semantic Scholar + OpenAlex + "
    "Crossref + OpenLibrary + Google Books + EPO (patents) + standards "
    "(ISO/IEC/IEEE/CEN/CC) enrichment and docling PDF conversion."
)
_LLMS_TXT = "https://pvliesdonk.github.io/scholar-mcp/latest/llms.txt"


def test_make_server_constructs() -> None:
    """make_server() returns a FastMCP instance without raising."""
    server = make_server()
    assert server is not None


def test_instructions_are_composed_not_templated() -> None:
    """The instructions pvl-core 5 renders carry all three contributors.

    Identity comes from this server's `instructions_for(mcp).identity(...)`,
    the documentation pointer from its `.documentation(...)`, and the polling
    contract from pvl-core's own `register_job_tools`. Asserting all three
    proves `finalize_instructions` ran after registration rather than before,
    which is the ordering the composition depends on.
    """
    text = make_server().instructions or ""
    assert text.startswith(_IDENTITY)
    assert _LLMS_TXT in text
    assert "get_job_result" in text, (
        "expected pvl-core's job-polling workflow prose; its absence means "
        "finalize_instructions ran before the tools were registered"
    )


def test_instructions_extra_is_appended_to_the_generated_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_INSTRUCTIONS_EXTRA` adds operator context without replacing anything."""
    monkeypatch.setenv("SCHOLAR_MCP_INSTRUCTIONS_EXTRA", "House rule: be brief.")
    text = make_server().instructions or ""
    assert text.startswith(_IDENTITY)
    assert _LLMS_TXT in text
    assert text.rstrip().endswith("House rule: be brief.")


def test_legacy_instructions_replaces_everything_and_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`SCHOLAR_MCP_INSTRUCTIONS` still full-replaces, and says it is legacy.

    Operators who set it keep their behaviour across this upgrade; the
    deprecation warning is what tells them `_EXTRA` is the replacement.
    """
    monkeypatch.setenv("SCHOLAR_MCP_INSTRUCTIONS", "Custom operator text.")
    # Scope to core's logger: make_server() re-applies FASTMCP_LOG_LEVEL to the
    # root logger, which would otherwise drop the record under a stricter env.
    monkeypatch.delenv("FASTMCP_LOG_LEVEL", raising=False)
    with caplog.at_level("WARNING", logger="fastmcp_pvl_core"):
        server = make_server()
    assert server.instructions == "Custom operator text."
    assert any(
        "SCHOLAR_MCP_INSTRUCTIONS_EXTRA" in rec.getMessage() for rec in caplog.records
    ), "expected the deprecation warning naming the _EXTRA replacement"


def test_blank_instructions_falls_back_to_the_composed_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blank override reverts to the composed text rather than blanking it.

    `env` strips and treats a blank value as unset; a future refactor to raw
    `os.environ.get` would pass the whitespace through and ship an empty
    instructions string to every client.
    """
    monkeypatch.setenv("SCHOLAR_MCP_INSTRUCTIONS", "   ")
    assert (make_server().instructions or "").startswith(_IDENTITY)
