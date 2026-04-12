"""Smoke tests for the Claude Desktop .mcpb bundle and Claude Code plugin.

These tests do not run the packaged server — they assert that the packaging
files are syntactically valid and that invariants the release workflow
depends on (version strings, import paths) stay consistent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MCPB_DIR = REPO_ROOT / "packaging" / "mcpb"
PLUGIN_DIR = REPO_ROOT / ".claude-plugin" / "plugin"


def test_cli_main_import_target_exists() -> None:
    """The mcpb shim imports scholar_mcp.cli.main — make sure it exists."""
    from scholar_mcp.cli import main

    assert callable(main)


def test_mcpb_server_shim_calls_main_serve() -> None:
    """The shim must import cli.main and ensure 'serve' is in sys.argv."""
    shim = MCPB_DIR / "src" / "server.py"
    assert shim.exists(), f"missing shim at {shim}"
    content = shim.read_text(encoding="utf-8")
    assert "from scholar_mcp.cli import main" in content
    # cli.main() parses sys.argv; the shim must inject "serve" rather than
    # passing it as a positional argument (main takes no positional args).
    assert "serve" in content
    assert "sys.argv" in content


def _load_manifest_template() -> dict:  # type: ignore[type-arg]
    """Load the mcpb manifest template with ${VERSION} replaced by a literal."""
    template = (MCPB_DIR / "manifest.json.in").read_text(encoding="utf-8")
    # Guard: ${DOCUMENTS} is a runtime placeholder for the host's document
    # directory. It must NOT be consumed by envsubst during the build (which
    # only substitutes ${VERSION}). If someone accidentally adds envsubst
    # without the variable-list argument, ${DOCUMENTS} becomes empty and
    # the default cache path in every released bundle becomes "/scholar-mcp".
    assert "${DOCUMENTS}" in template, (
        "manifest template must contain ${DOCUMENTS} as a runtime placeholder; "
        "if it was removed, restore it or this test is no longer needed"
    )
    rendered = template.replace("${VERSION}", "0.0.0-test")
    # After the VERSION substitution, ${DOCUMENTS} must still be present.
    assert "${DOCUMENTS}" in rendered, (
        "${DOCUMENTS} was lost during template rendering — "
        "envsubst must be called with '${VERSION}' argument to restrict substitution"
    )
    return json.loads(rendered)


def test_mcpb_manifest_template_valid_and_complete() -> None:
    """The mcpb manifest must parse and carry the fields the spec requires."""
    manifest = _load_manifest_template()

    assert manifest["manifest_version"] == "0.4"
    assert manifest["name"] == "scholar-mcp"
    assert manifest["version"] == "0.0.0-test"

    server = manifest["server"]
    assert server["type"] == "uv"
    assert server["entry_point"] == "src/server.py"

    # mcp_config must NOT use --from . (local source dir) — that would fail
    # at runtime in an installed bundle.
    mcp_config = server["mcp_config"]
    if "args" in mcp_config and "--from" in mcp_config["args"]:
        from_idx = mcp_config["args"].index("--from")
        assert mcp_config["args"][from_idx + 1] != ".", (
            "mcp_config.args must not use '--from .' (local source); "
            "use '--from pvliesdonk-scholar-mcp[mcp]==${VERSION}' instead"
        )

    env = server["mcp_config"]["env"]
    # Core env vars must be wired through user_config.
    assert env["SCHOLAR_MCP_S2_API_KEY"] == "${user_config.s2_api_key}"
    assert env["SCHOLAR_MCP_READ_ONLY"] == "${user_config.read_only}"

    user_config = manifest["user_config"]
    # Sensitive fields must be marked so the host stores them in the keychain.
    assert user_config["s2_api_key"]["sensitive"] is True
    assert user_config["vlm_api_key"]["sensitive"] is True
    assert user_config["epo_consumer_secret"]["sensitive"] is True


def test_mcpb_pyproject_template_pins_versioned_package() -> None:
    """The bundle pyproject must pin pvliesdonk-scholar-mcp[mcp] to VERSION."""
    template = (MCPB_DIR / "pyproject.toml.in").read_text(encoding="utf-8")
    assert "${VERSION}" in template, "template must use ${VERSION} placeholder"
    # The dep line should pin [mcp] extras to the same version.
    assert "pvliesdonk-scholar-mcp[mcp]==${VERSION}" in template
    assert 'requires-python = ">=3.11"' in template


def _load_plugin_json() -> dict:  # type: ignore[type-arg]
    """Load the Claude Code plugin.json metadata file."""
    path = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_claude_code_plugin_json_shape() -> None:
    """plugin.json must carry the expected name, repo, and a concrete version."""
    plugin = _load_plugin_json()
    assert plugin["name"] == "scholar-mcp"
    assert plugin["repository"] == "https://github.com/pvliesdonk/scholar-mcp"
    assert plugin["license"] == "MIT"

    # Version must look like a real semver — not a template literal.
    version = plugin["version"]
    assert version != "${VERSION}"
    parts = version.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts), (
        f"expected X.Y.Z semver, got {version!r}"
    )


def _load_plugin_mcp_json() -> dict:  # type: ignore[type-arg]
    """Load the Claude Code .mcp.json server launch config."""
    path = PLUGIN_DIR / ".mcp.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_plugin_mcp_json_pinned_and_matches_plugin_version() -> None:
    """.mcp.json must pin --from pvliesdonk-scholar-mcp[mcp]==X.Y.Z."""
    mcp_cfg = _load_plugin_mcp_json()
    entry = mcp_cfg["scholar-mcp"]
    assert entry["command"] == "uvx"

    args = entry["args"]
    assert "--from" in args, f"args must include --from, got {args}"
    from_index = args.index("--from")
    spec = args[from_index + 1]
    match = re.fullmatch(r"pvliesdonk-scholar-mcp\[mcp\]==(\d+\.\d+\.\d+)", spec)
    assert match, f"unexpected --from spec: {spec!r}"

    plugin_version = _load_plugin_json()["version"]
    assert match.group(1) == plugin_version, (
        f".mcp.json pinned to {match.group(1)} but plugin.json is {plugin_version}"
    )

    env = entry["env"]
    assert "SCHOLAR_MCP_S2_API_KEY" in env
    assert "SCHOLAR_MCP_READ_ONLY" in env
    assert "SCHOLAR_MCP_VLM_API_URL" in env
    assert "SCHOLAR_MCP_VLM_API_KEY" in env
    assert "SCHOLAR_MCP_VLM_MODEL" in env
