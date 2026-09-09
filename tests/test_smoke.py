"""Smoke tests for Scholar MCP."""

from __future__ import annotations

import pytest

from scholar_mcp.server import make_server

# pvl-core 6 shapes identity as "<server-name>: <product description>".
_IDENTITY = (
    "scholar-mcp: Scholar MCP — academic literature server: Semantic Scholar "
    "+ OpenAlex + Crossref + OpenLibrary + Google Books + EPO (patents) + "
    "standards (ISO/IEC/IEEE/CEN/CC) enrichment and docling PDF conversion."
)
_LLMS_TXT = "https://pvliesdonk.github.io/scholar-mcp/latest/llms.txt"
_WRITE_MODE_SNIPPET = "This instance is in read-write mode"


def test_make_server_constructs() -> None:
    """make_server() returns a FastMCP instance without raising."""
    server = make_server()
    assert server is not None


def test_instructions_are_composed_not_templated() -> None:
    """The instructions pvl-core renders carry all three contributors.

    Identity comes from this server's `instructions_for(mcp).identity(...)` --
    shaped `<server-name>: <description>` since pvl-core 6 -- the
    documentation pointer from its `.documentation(...)`, and the polling
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


def test_routing_and_policy_are_placed_by_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_INSTANCE_DESCRIPTION` is routing and `_INSTRUCTIONS_EXTRA` is policy.

    pvl-core 6 separates the two: routing describes what this deployment
    holds, policy describes how to behave. Both are additive and both land
    after the identity line, in that order -- not appended at the end, which
    is where the pre-6 `_EXTRA` went.
    """
    monkeypatch.setenv("SCHOLAR_MCP_INSTANCE_DESCRIPTION", "Holds the physics corpus.")
    monkeypatch.setenv("SCHOLAR_MCP_INSTRUCTIONS_EXTRA", "House rule: be brief.")
    text = make_server().instructions or ""

    assert text.startswith(_IDENTITY)
    routing = text.index("Holds the physics corpus.")
    policy = text.index("House rule: be brief.")
    assert len(_IDENTITY) <= routing < policy < text.index(_LLMS_TXT), (
        "expected identity, then routing, then policy, then the documentation "
        f"pointer; got:\n{text}"
    )


def test_write_mode_prose_is_gated_on_the_tools_it_describes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The read-write workflow snippet appears only when those tools do.

    `requires_tools` is what keeps the sentence honest: pvl-core drops a
    snippet whose required tools are hidden, so a read-only instance -- where
    the four write-tagged PDF tools are disabled by tag -- never tells the
    model about tools it cannot call. Both directions are asserted, because a
    snippet that never renders and one that always renders both pass a
    one-sided check.
    """
    read_only = make_server().instructions or ""
    assert _WRITE_MODE_SNIPPET not in read_only, (
        "read-only instance advertised write-tagged tools it does not expose"
    )

    monkeypatch.setenv("SCHOLAR_MCP_READ_ONLY", "false")
    assert _WRITE_MODE_SNIPPET in (make_server().instructions or "")


def test_legacy_instructions_replaces_everything_and_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`SCHOLAR_MCP_INSTRUCTIONS` still full-replaces, and says it is legacy.

    Operators who set it keep their behaviour across this upgrade; the
    deprecation warning is what tells them the additive variables exist.
    """
    monkeypatch.setenv("SCHOLAR_MCP_INSTRUCTIONS", "Custom operator text.")
    # Scope to core's logger: make_server() re-applies FASTMCP_LOG_LEVEL to the
    # root logger, which would otherwise drop the record under a stricter env.
    monkeypatch.delenv("FASTMCP_LOG_LEVEL", raising=False)
    with caplog.at_level("WARNING", logger="fastmcp_pvl_core"):
        server = make_server()
    assert server.instructions == "Custom operator text."
    assert any(
        "SCHOLAR_MCP_INSTRUCTIONS" in rec.getMessage() for rec in caplog.records
    ), "expected the deprecation warning naming the additive replacements"


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
