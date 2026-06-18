"""Tests for MCP server factory — auth wiring and read-only mode."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from mcp.types import TextContent

from scholar_mcp import server as server_module
from scholar_mcp.server import (
    _build_remote_auth,
    _resolve_auth_mode,
    make_server,
)

# OIDC vars required by _build_oidc_auth()
_OIDC_REQUIRED = {
    "SCHOLAR_MCP_BASE_URL": "https://mcp.example.com",
    "SCHOLAR_MCP_OIDC_CONFIG_URL": "https://auth.example.com/.well-known/openid-configuration",
    "SCHOLAR_MCP_OIDC_CLIENT_ID": "mcp-client",
    "SCHOLAR_MCP_OIDC_CLIENT_SECRET": "test-secret",
}


class TestAuthModeSelection:
    """Tests for make_server() auth mode selection.

    Covers all four modes: multi (both configured), bearer-only,
    OIDC-only, and none.
    """

    def test_no_auth_when_nothing_configured(self) -> None:
        """Default: no auth when no auth env vars are set."""
        server = make_server()
        assert server.auth is None

    def test_bearer_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bearer-only: StaticTokenVerifier when only BEARER_TOKEN is set."""
        from fastmcp.server.auth import StaticTokenVerifier

        monkeypatch.setenv("SCHOLAR_MCP_BEARER_TOKEN", "my-secret-token")
        server = make_server()
        assert isinstance(server.auth, StaticTokenVerifier)

    def test_oidc_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OIDC-only: OIDCProxy when only OIDC vars are set."""
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_oidc = MagicMock()
        mock_cls = MagicMock(return_value=mock_oidc)
        with patch("fastmcp.server.auth.oidc_proxy.OIDCProxy", mock_cls):
            server = make_server(transport="http")

        assert server.auth is mock_oidc

    def test_multi_auth_when_both_configured(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Multi-auth: MultiAuth when both BEARER_TOKEN and OIDC vars are set."""
        from fastmcp.server.auth import MultiAuth

        monkeypatch.setenv("SCHOLAR_MCP_BEARER_TOKEN", "my-secret-token")
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_oidc = MagicMock()
        mock_cls = MagicMock(return_value=mock_oidc)
        with (
            patch("fastmcp.server.auth.oidc_proxy.OIDCProxy", mock_cls),
            caplog.at_level(logging.INFO),
        ):
            server = make_server(transport="http")

        assert isinstance(server.auth, MultiAuth)
        assert "Auth enabled: mode=multi" in caplog.text

    def test_multi_auth_structure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OIDCProxy must be server= (not in verifiers=) for OAuth routes to mount."""
        from fastmcp.server.auth import MultiAuth, StaticTokenVerifier

        monkeypatch.setenv("SCHOLAR_MCP_BEARER_TOKEN", "my-secret-token")
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_oidc = MagicMock()
        mock_cls = MagicMock(return_value=mock_oidc)
        with patch("fastmcp.server.auth.oidc_proxy.OIDCProxy", mock_cls):
            server = make_server(transport="http")

        assert isinstance(server.auth, MultiAuth)
        # OIDCProxy is an OAuthProvider — must be server=, not in verifiers=,
        # so that MultiAuth.get_routes() delegates OAuth endpoints to it.
        assert server.auth.server is mock_oidc
        verifiers = server.auth.verifiers
        assert len(verifiers) == 1
        assert isinstance(verifiers[0], StaticTokenVerifier)


class TestReadOnlyMode:
    """Tests for read-only vs read-write tool visibility."""

    async def test_read_only_by_default(self) -> None:
        """Server is read-only by default — creates without error."""
        server = make_server()
        # No write-tagged tools should be present in read-only mode.
        write_tools = [
            t for t in await server.list_tools() if "write" in (t.tags or set())
        ]
        assert write_tools == []

    async def test_read_write_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Setting READ_ONLY=false creates server in read-write mode."""
        monkeypatch.setenv("SCHOLAR_MCP_READ_ONLY", "false")
        server = make_server()
        # Server should be created successfully in read-write mode.
        assert server is not None


class TestPatentToolGating:
    """Patent tools (tagged 'patent') are hidden unless EPO OPS is configured."""

    async def test_patent_tools_hidden_without_epo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no EPO env vars, patent-tagged tools must be disabled."""
        monkeypatch.delenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", raising=False)
        monkeypatch.delenv("SCHOLAR_MCP_EPO_CONSUMER_SECRET", raising=False)
        server = make_server()
        patent_tools = [
            t for t in await server.list_tools() if "patent" in (t.tags or set())
        ]
        assert patent_tools == []

    async def test_patent_tools_visible_with_epo(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With both EPO creds set, patent-tagged tools stay visible."""
        monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_KEY", "test-key")
        monkeypatch.setenv("SCHOLAR_MCP_EPO_CONSUMER_SECRET", "test-secret")
        monkeypatch.setenv("SCHOLAR_MCP_READ_ONLY", "false")
        server = make_server()
        # At least one patent-tagged tool should be visible when EPO is configured.
        patent_tools = [
            t for t in await server.list_tools() if "patent" in (t.tags or set())
        ]
        assert len(patent_tools) > 0


class TestServerInfoTool:
    """make_server() registers the get_server_info tool from pvl-core."""

    async def test_get_server_info_registered(self) -> None:
        """get_server_info is registered and visible in default (read-only) mode."""
        server = make_server()
        tool_names = {t.name for t in await server.list_tools()}
        assert "get_server_info" in tool_names

    async def test_get_server_info_payload_shape(self) -> None:
        """Calling get_server_info returns scholar's identity and version keys.

        Locks in that this server wires the pvl-core helper (catches an
        accidental swap to a custom tool that names itself get_server_info
        but returns a different payload).
        """
        server = make_server()
        result = await server.call_tool("get_server_info")
        assert result.content, "get_server_info returned empty content"
        first = result.content[0]
        assert isinstance(first, TextContent)
        payload = json.loads(first.text)
        assert payload["server_name"] == "scholar-mcp"
        assert isinstance(payload["server_version"], str) and payload["server_version"]
        assert "core_version" in payload

    async def test_get_server_info_uses_configured_server_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A custom SCHOLAR_MCP_SERVER_NAME flows through to get_server_info.

        Regression guard: the register_server_info_tool call must pass the
        resolved server_name variable, not a hardcoded literal — otherwise
        operators reading get_server_info see a different name than the one
        used by the FastMCP instance and operational logs.
        """
        monkeypatch.setenv("SCHOLAR_MCP_SERVER_NAME", "scholar-mcp-prod")
        server = make_server()
        result = await server.call_tool("get_server_info")
        assert result.content, "get_server_info returned empty content"
        first = result.content[0]
        assert isinstance(first, TextContent)
        payload = json.loads(first.text)
        assert payload["server_name"] == "scholar-mcp-prod"


class TestResolveAuthMode:
    """Tests for _resolve_auth_mode() auto-detection and explicit overrides."""

    def test_returns_none_when_no_vars(self) -> None:
        assert _resolve_auth_mode() is None

    def test_explicit_remote(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOLAR_MCP_AUTH_MODE", "remote")
        assert _resolve_auth_mode() == "remote"

    def test_explicit_oidc_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOLAR_MCP_AUTH_MODE", "oidc-proxy")
        assert _resolve_auth_mode() == "oidc-proxy"

    def test_unknown_mode_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("SCHOLAR_MCP_AUTH_MODE", "bogus")
        with caplog.at_level(logging.WARNING):
            result = _resolve_auth_mode()
        assert result is None
        assert "auth_mode_unknown" in caplog.text

    def test_auto_detects_oidc_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)
        assert _resolve_auth_mode() == "oidc-proxy"

    def test_auto_detects_remote(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv(
            "SCHOLAR_MCP_OIDC_CONFIG_URL",
            "https://auth.example.com/.well-known/openid-configuration",
        )
        assert _resolve_auth_mode() == "remote"


class TestBuildRemoteAuth:
    """Tests for _build_remote_auth() — OIDC discovery and RemoteAuthProvider.

    Semantics under fastmcp-pvl-core 2.x: ``build_remote_auth`` raises
    ``ConfigurationError`` on misconfiguration / discovery failure rather
    than silently returning ``None``. The intent (per pvl-core's release
    notes) is to page operators on real misconfig instead of producing a
    degraded server. ``None`` is still returned when no remote-auth config
    is present at all (the "not requested" case).
    """

    def test_returns_none_without_vars(self) -> None:
        assert _build_remote_auth() is None

    def test_raises_on_discovery_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv("SCHOLAR_MCP_OIDC_CONFIG_URL", "https://bad.url/oidc")
        import httpx
        from fastmcp_pvl_core import ConfigurationError

        with (
            patch("httpx.get", side_effect=httpx.ConnectError("fail")),
            pytest.raises(ConfigurationError, match="OIDC discovery failed"),
        ):
            _build_remote_auth()

    def test_raises_on_missing_jwks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv("SCHOLAR_MCP_OIDC_CONFIG_URL", "https://auth.example.com/d")
        from fastmcp_pvl_core import ConfigurationError

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"issuer": "https://auth.example.com"}
        mock_resp.raise_for_status = MagicMock()
        with (
            patch("httpx.get", return_value=mock_resp),
            pytest.raises(ConfigurationError),
        ):
            _build_remote_auth()

    def test_raises_on_missing_issuer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv("SCHOLAR_MCP_OIDC_CONFIG_URL", "https://auth.example.com/d")
        from fastmcp_pvl_core import ConfigurationError

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"jwks_uri": "https://auth.example.com/jwks.json"}
        mock_resp.raise_for_status = MagicMock()
        with (
            patch("httpx.get", return_value=mock_resp),
            pytest.raises(ConfigurationError),
        ):
            _build_remote_auth()

    def test_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from fastmcp.server.auth import RemoteAuthProvider

        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv("SCHOLAR_MCP_OIDC_CONFIG_URL", "https://auth.example.com/d")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "jwks_uri": "https://auth.example.com/jwks.json",
            "issuer": "https://auth.example.com",
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_resp):
            result = _build_remote_auth()
        assert isinstance(result, RemoteAuthProvider)

    def test_make_server_remote_mode(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """make_server(transport=http) uses remote auth when only BASE_URL + CONFIG_URL set."""
        from fastmcp.server.auth import RemoteAuthProvider

        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv("SCHOLAR_MCP_OIDC_CONFIG_URL", "https://auth.example.com/d")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "jwks_uri": "https://auth.example.com/jwks.json",
            "issuer": "https://auth.example.com",
        }
        with patch("httpx.get", return_value=mock_resp), caplog.at_level(logging.INFO):
            server = make_server(transport="http")
        assert isinstance(server.auth, RemoteAuthProvider)

    def test_make_server_multi_remote_bearer(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """make_server(transport=http) uses MultiAuth(remote+bearer) when both configured."""
        from fastmcp.server.auth import MultiAuth

        monkeypatch.setenv("SCHOLAR_MCP_BEARER_TOKEN", "my-token")
        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv("SCHOLAR_MCP_OIDC_CONFIG_URL", "https://auth.example.com/d")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "jwks_uri": "https://auth.example.com/jwks.json",
            "issuer": "https://auth.example.com",
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_resp), caplog.at_level(logging.INFO):
            server = make_server(transport="http")
        assert isinstance(server.auth, MultiAuth)
        assert "Auth enabled: mode=multi" in caplog.text

    def test_make_server_propagates_oidc_failure_on_stdio(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """make_server(transport=stdio) does NOT magically skip OIDC discovery.

        Under pvl-core 2.x, the auth pipeline is transport-agnostic — if the
        operator set OIDC env vars they get OIDC, and discovery failure
        raises ``ConfigurationError`` regardless of transport. This locks in
        that scholar does not silently degrade stdio servers that happen to
        have unreachable OIDC config (which pre-2.x's silent-degradation
        behavior had been accidentally tolerant of).
        """
        import httpx
        from fastmcp_pvl_core import ConfigurationError

        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv("SCHOLAR_MCP_OIDC_CONFIG_URL", "https://bad.url/oidc")
        with (
            patch("httpx.get", side_effect=httpx.ConnectError("fail")),
            pytest.raises(ConfigurationError, match="OIDC discovery failed"),
        ):
            make_server(transport="stdio")

    def test_make_server_propagates_remote_discovery_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """make_server(transport=http) propagates ConfigurationError on OIDC discovery failure.

        pvl-core 2.x raises ``ConfigurationError`` on remote/multi auth discovery
        failures rather than degrading silently — the intent is that operators
        get paged on misconfig instead of running an unauthed server thinking
        they have auth. scholar passes the exception through.
        """
        import httpx
        from fastmcp_pvl_core import ConfigurationError

        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv("SCHOLAR_MCP_OIDC_CONFIG_URL", "https://bad.url/oidc")
        with (
            patch("httpx.get", side_effect=httpx.ConnectError("fail")),
            pytest.raises(ConfigurationError, match="OIDC discovery failed"),
        ):
            make_server(transport="http")


class TestAuthModeInvariant:
    """make_server() refuses to start if build_auth and resolve_auth_mode disagree.

    Locks in the explicit invariant raise that catches a future pvl-core
    regression where ``build_auth`` silently downgraded a configured mode to
    ``None``. Tested with monkeypatching because the invariant cannot be
    triggered through normal env-var config (pvl-core 2.x maintains the
    invariant correctly today).
    """

    def test_raises_on_auth_mode_mismatch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force build_auth to return None while resolve_auth_mode still
        # claims a non-"none" mode — the asymmetry we want to catch.
        monkeypatch.setattr(server_module, "build_auth", lambda _config: None)
        monkeypatch.setattr(
            server_module, "_core_resolve_auth_mode", lambda _config: "bearer-single"
        )
        with pytest.raises(RuntimeError, match="invariant violation"):
            make_server()
