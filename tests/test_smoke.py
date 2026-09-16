"""Smoke tests for Scholar MCP."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client

from scholar_mcp._server_apps import register_apps
from scholar_mcp.server import make_server

# pvl-core 6 shapes identity as "<server-name>: <product description>".
_IDENTITY = (
    "scholar-mcp: Scholarly papers, patents, books, standards and PDF conversion"
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


def test_register_apps_logs_when_app_domain_set(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """register_apps logs the configured app domain when the env var is set.

    Covers the ``if app_domain:`` branch of ``_server_apps.register_apps``,
    which the default smoke tests miss because no ``SCHOLAR_MCP_APP_DOMAIN``
    is set in the test env.  Pass a real ``FastMCP`` instance so the test
    keeps working if a downstream maintainer adds real registrations to the
    branch (the scaffold's no-op branch ignores the argument today).
    """
    monkeypatch.setenv("SCHOLAR_MCP_APP_DOMAIN", "example.com")
    with caplog.at_level("INFO", logger="scholar_mcp._server_apps"):
        register_apps(make_server())
    # Assert on the structured log argument by exact equality rather than a
    # substring test of the formatted message.  ``"example.com" in r.message``
    # trips CodeQL's ``py/incomplete-url-substring-sanitization`` rule on the
    # host-shaped literal, even though this is a log assertion and not URL
    # sanitization; ``==`` is not a substring-membership pattern, so it does
    # not.  The branch logs the configured domain as its sole ``%s`` arg.
    assert any(r.args == ("example.com",) for r in caplog.records)


def test_server_name_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """``SCHOLAR_MCP_SERVER_NAME`` overrides the FastMCP server name.

    Unset, the name defaults to ``scholar-mcp`` (locked by the
    ``get_server_info`` test above). Set, ``make_server()`` must honor it so an
    operator can rename an instance without editing template-owned code.
    """
    monkeypatch.setenv("SCHOLAR_MCP_SERVER_NAME", "renamed-instance")
    server = make_server()
    assert server.name == "renamed-instance"
    assert (server.instructions or "").startswith(
        "renamed-instance: Scholarly papers, patents, books, standards and PDF conversion"
    )


def test_server_name_env_override_reaches_server_info(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The overridden name also flows through to ``get_server_info``.

    ``register_server_info_tool`` is wired separately from the FastMCP ``name``,
    so this pins that both surfaces honor the same resolved name.
    """
    monkeypatch.setenv("SCHOLAR_MCP_SERVER_NAME", "renamed-instance")
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp_path / "cache"))
    server = make_server()

    async def _call_server_info() -> Any:
        async with Client(server) as smoke_client:
            return await smoke_client.call_tool("get_server_info", {})

    result = asyncio.run(_call_server_info())
    first = result.content[0]
    assert hasattr(first, "text"), (
        f"expected text tool content, got {type(first).__name__}"
    )
    assert json.loads(first.text)["server_name"] == "renamed-instance"


def test_instructions_env_override(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Legacy ``SCHOLAR_MCP_INSTRUCTIONS`` replaces all generated text and
    warns that both additive operator variables are ignored."""
    monkeypatch.setenv("SCHOLAR_MCP_INSTRUCTIONS", "Custom operator text.")
    monkeypatch.setenv("SCHOLAR_MCP_INSTANCE_DESCRIPTION", "Demo material.")
    monkeypatch.setenv("SCHOLAR_MCP_INSTRUCTIONS_EXTRA", "House rule: be brief.")
    # Scope to core's logger: make_server() re-applies FASTMCP_LOG_LEVEL to the
    # root logger, which would otherwise drop the record under a stricter env.
    monkeypatch.delenv("FASTMCP_LOG_LEVEL", raising=False)
    with caplog.at_level("WARNING", logger="fastmcp_pvl_core"):
        server = make_server()
    assert server.instructions == "Custom operator text."
    warning = next(
        rec.getMessage()
        for rec in caplog.records
        if "SCHOLAR_MCP_INSTRUCTIONS" in rec.getMessage()
    )
    assert "SCHOLAR_MCP_INSTANCE_DESCRIPTION" in warning
    assert "SCHOLAR_MCP_INSTRUCTIONS_EXTRA" in warning


def test_instructions_compose_semantic_operator_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Operator routing and policy retain their semantic positions."""
    monkeypatch.delenv("SCHOLAR_MCP_INSTRUCTIONS", raising=False)
    monkeypatch.setenv("SCHOLAR_MCP_INSTANCE_DESCRIPTION", "Demo material.")
    monkeypatch.setenv("SCHOLAR_MCP_INSTRUCTIONS_EXTRA", "House rule: be brief.")
    parts = (make_server().instructions or "").split("\n\n")
    # Scholar's own workflow snippets (job polling) sit between policy and the
    # documentation pointer, so pin the roles' positions, not the full list.
    assert parts[:3] == [
        "scholar-mcp: Scholarly papers, patents, books, standards and PDF conversion",
        "Demo material.",
        "House rule: be brief.",
    ]
    assert parts[-1] == (
        "Full documentation for this server: "
        "https://pvliesdonk.github.io/scholar-mcp/latest/llms.txt"
    )


def test_blank_overrides_fall_back_to_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whitespace-only overrides fall back, honoring the "unset/empty" contract.

    ``env`` strips and treats a blank value as unset, so a blank SERVER_NAME
    must revert to ``scholar-mcp`` rather than rename the instance to
    whitespace, and a blank INSTRUCTIONS must leave the composed text in place.
    Guards against a future refactor (e.g. raw ``os.environ.get``) that would
    pass the blank value through.
    """
    monkeypatch.setenv("SCHOLAR_MCP_SERVER_NAME", "   ")
    monkeypatch.setenv("SCHOLAR_MCP_INSTRUCTIONS", "   ")
    server = make_server()
    assert server.name == "scholar-mcp"
    assert (server.instructions or "").startswith(
        "scholar-mcp: Scholarly papers, patents, books, standards and PDF conversion",
    )
