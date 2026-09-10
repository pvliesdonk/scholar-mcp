"""Tests for MCP server factory — auth wiring and read-only mode."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import FastMCP
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

# Env applied to the `server` fixture by indirect parametrisation.  The fixture
# builds the server synchronously, so an async test never calls `make_server()`
# inside the running loop -- see the fixture's docstring and #338.
_READ_WRITE = {"SCHOLAR_MCP_READ_ONLY": "false"}
_EPO_READ_WRITE = _READ_WRITE | {
    "SCHOLAR_MCP_EPO_CONSUMER_KEY": "test-key",
    "SCHOLAR_MCP_EPO_CONSUMER_SECRET": "test-secret",
}
_NAMED = {"SCHOLAR_MCP_SERVER_NAME": "scholar-mcp-prod"}


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

    async def test_read_only_by_default(self, server: FastMCP) -> None:
        """Server is read-only by default — creates without error."""
        # No write-tagged tools should be present in read-only mode.
        write_tools = [
            t for t in await server.list_tools() if "write" in (t.tags or set())
        ]
        assert write_tools == []

    @pytest.mark.parametrize("server", [_READ_WRITE], indirect=True, ids=["read-write"])
    async def test_read_write_mode(self, server: FastMCP) -> None:
        """Setting READ_ONLY=false creates server in read-write mode."""
        # Server should be created successfully in read-write mode.
        assert server is not None


class TestPatentToolGating:
    """Patent tools (tagged 'patent') are hidden unless EPO OPS is configured."""

    async def test_patent_tools_hidden_without_epo(self, server: FastMCP) -> None:
        """With no EPO env vars, patent-tagged tools must be disabled.

        The autouse `_clean_env` fixture strips every `SCHOLAR_MCP_*` var, so
        the default `server` is already the unconfigured case.
        """
        patent_tools = [
            t for t in await server.list_tools() if "patent" in (t.tags or set())
        ]
        assert patent_tools == []

    @pytest.mark.parametrize("server", [_EPO_READ_WRITE], indirect=True, ids=["epo"])
    async def test_patent_tools_visible_with_epo(self, server: FastMCP) -> None:
        """With both EPO creds set, patent-tagged tools stay visible."""
        # At least one patent-tagged tool should be visible when EPO is configured.
        patent_tools = [
            t for t in await server.list_tools() if "patent" in (t.tags or set())
        ]
        assert len(patent_tools) > 0


class TestServerInfoTool:
    """make_server() registers the get_server_info tool from pvl-core."""

    async def test_get_server_info_registered(self, server: FastMCP) -> None:
        """get_server_info is registered and visible in default (read-only) mode."""
        tool_names = {t.name for t in await server.list_tools()}
        assert "get_server_info" in tool_names

    async def test_get_server_info_payload_shape(self, server: FastMCP) -> None:
        """Calling get_server_info returns scholar's identity and version keys.

        Locks in that this server wires the pvl-core helper (catches an
        accidental swap to a custom tool that names itself get_server_info
        but returns a different payload).
        """
        result = await server.call_tool("get_server_info")
        assert result.content, "get_server_info returned empty content"
        first = result.content[0]
        assert isinstance(first, TextContent)
        payload = json.loads(first.text)
        assert payload["server_name"] == "scholar-mcp"
        assert isinstance(payload["server_version"], str) and payload["server_version"]
        assert "core_version" in payload

    @pytest.mark.parametrize("server", [_NAMED], indirect=True, ids=["named"])
    async def test_get_server_info_uses_configured_server_name(
        self, server: FastMCP
    ) -> None:
        """A custom SCHOLAR_MCP_SERVER_NAME flows through to get_server_info.

        Regression guard: the register_server_info_tool call must pass the
        resolved server_name variable, not a hardcoded literal — otherwise
        operators reading get_server_info see a different name than the one
        used by the FastMCP instance and operational logs.
        """
        result = await server.call_tool("get_server_info")
        assert result.content, "get_server_info returned empty content"
        first = result.content[0]
        assert isinstance(first, TextContent)
        payload = json.loads(first.text)
        assert payload["server_name"] == "scholar-mcp-prod"

    async def test_get_server_info_reports_s2_key_health(self, server: FastMCP) -> None:
        """The keepalive's verdict is readable, not only loggable (#229).

        Reported here rather than gated on in `/health/ready`: a revoked key
        breaks the Semantic Scholar tools while every other upstream keeps
        serving, and no restart revives it.
        """
        result = await server.call_tool("get_server_info")
        payload = json.loads(result.content[0].text)

        assert "semantic_scholar" in payload, f"no S2 block in {sorted(payload)}"
        s2 = payload["semantic_scholar"]
        assert set(s2) == {
            "key_configured",
            "key_status",
            "consecutive_failures",
            "last_success",
            "last_failure",
            "last_failure_kind",
        }
        # The test server configures no key, so the absence reports itself
        # rather than looking like a key that has never been pinged.
        assert s2["key_configured"] is False
        assert s2["key_status"] == "not_configured"

    async def test_get_server_info_s2_block_tracks_the_keepalive(
        self, server: FastMCP, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A degraded key shows up in the payload, not just the log."""
        from scholar_mcp._s2_client import S2_KEEPALIVE_STATUS

        monkeypatch.setattr(S2_KEEPALIVE_STATUS, "configured", True)
        monkeypatch.setattr(S2_KEEPALIVE_STATUS, "consecutive_failures", 24)
        monkeypatch.setattr(S2_KEEPALIVE_STATUS, "last_failure_kind", "rate_limited")

        result = await server.call_tool("get_server_info")
        s2 = json.loads(result.content[0].text)["semantic_scholar"]
        assert s2["key_status"] == "degraded"
        assert s2["consecutive_failures"] == 24
        assert s2["last_failure_kind"] == "rate_limited"


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

    ``build_remote_auth`` raises ``ConfigurationError`` on misconfiguration
    / discovery failure rather than silently returning ``None``. The intent
    is to page operators on real misconfig instead of producing a degraded
    server. ``None`` is still returned when no remote-auth config is
    present at all (the "not requested" case).
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

        The auth pipeline is transport-agnostic — if the operator set OIDC
        env vars they get OIDC, and discovery failure raises
        ``ConfigurationError`` regardless of transport. This locks in that
        scholar does not silently degrade stdio servers that happen to have
        unreachable OIDC config.
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

        pvl-core raises ``ConfigurationError`` on remote/multi auth discovery
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
    triggered through normal env-var config (pvl-core maintains the
    invariant).
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


# TestMiddlewareStack was removed in the pvl-core 3.x upgrade. The middleware
# class imports (ErrorHandlingMiddleware, LoggingMiddleware, TimingMiddleware)
# moved under pvl-core 3.x and are no longer importable from their former paths.
# wire_middleware_stack() itself is still called in make_server() and is covered
# by pvl-core's own test suite.
