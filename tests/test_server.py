"""Tests for MCP server factory — auth wiring and read-only mode."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware.logging import (
    LoggingMiddleware,
    StructuredLoggingMiddleware,
)
from fastmcp.server.middleware.timing import TimingMiddleware

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
        assert "Multi-auth enabled" in caplog.text

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

    Semantics changed in the fastmcp-pvl-core retrofit: the helper now
    returns ``None`` on misconfiguration / discovery failure and logs
    rather than raising ``RuntimeError``.
    """

    def test_returns_none_without_vars(self) -> None:
        assert _build_remote_auth() is None

    def test_returns_none_on_discovery_failure(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv("SCHOLAR_MCP_OIDC_CONFIG_URL", "https://bad.url/oidc")
        import httpx

        with (
            patch("httpx.get", side_effect=httpx.ConnectError("fail")),
            caplog.at_level(logging.ERROR),
        ):
            result = _build_remote_auth()
        assert result is None
        assert "discovery_failed" in caplog.text

    def test_returns_none_on_missing_jwks(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv("SCHOLAR_MCP_OIDC_CONFIG_URL", "https://auth.example.com/d")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"issuer": "https://auth.example.com"}
        mock_resp.raise_for_status = MagicMock()
        with (
            patch("httpx.get", return_value=mock_resp),
            caplog.at_level(logging.ERROR),
        ):
            result = _build_remote_auth()
        assert result is None

    def test_returns_none_on_missing_issuer(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv("SCHOLAR_MCP_OIDC_CONFIG_URL", "https://auth.example.com/d")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"jwks_uri": "https://auth.example.com/jwks.json"}
        mock_resp.raise_for_status = MagicMock()
        with (
            patch("httpx.get", return_value=mock_resp),
            caplog.at_level(logging.ERROR),
        ):
            result = _build_remote_auth()
        assert result is None

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
        assert "Multi-auth enabled" in caplog.text

    def test_make_server_skips_oidc_for_stdio(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """make_server() skips OIDC setup for stdio transport."""
        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv("SCHOLAR_MCP_OIDC_CONFIG_URL", "https://auth.example.com/d")
        # No httpx mock needed — _build_remote_auth should never be called
        server = make_server(transport="stdio")
        assert server.auth is None

    def test_make_server_remote_discovery_failure_returns_no_auth(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """make_server() falls back to no-auth when remote discovery fails.

        Semantics changed post-retrofit: core's build_remote_auth logs and
        returns None on discovery failure instead of raising.
        """
        import httpx

        monkeypatch.setenv("SCHOLAR_MCP_BASE_URL", "https://mcp.example.com")
        monkeypatch.setenv("SCHOLAR_MCP_OIDC_CONFIG_URL", "https://bad.url/oidc")
        with (
            patch("httpx.get", side_effect=httpx.ConnectError("fail")),
            caplog.at_level(logging.ERROR),
        ):
            server = make_server(transport="http")
        assert server.auth is None
        assert "discovery_failed" in caplog.text


class TestMiddlewareStack:
    """Tests for logging/timing/error middleware wiring."""

    def test_default_middleware_stack(self) -> None:
        """Default config wires ErrorHandling + Timing + LoggingMiddleware."""
        server = make_server()
        types = [type(m) for m in server.middleware]
        assert ErrorHandlingMiddleware in types
        assert TimingMiddleware in types
        assert LoggingMiddleware in types
        assert StructuredLoggingMiddleware not in types

    def test_rich_disabled_uses_structured_logging(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FASTMCP_ENABLE_RICH_LOGGING=false wires StructuredLoggingMiddleware."""
        monkeypatch.setenv("FASTMCP_ENABLE_RICH_LOGGING", "false")
        server = make_server()
        types = [type(m) for m in server.middleware]
        assert StructuredLoggingMiddleware in types
        assert LoggingMiddleware not in types

    def test_middleware_order(self) -> None:
        """ErrorHandling is first, Timing second, Logging third."""
        server = make_server()
        types = [type(m) for m in server.middleware]
        err_idx = types.index(ErrorHandlingMiddleware)
        time_idx = types.index(TimingMiddleware)
        log_idx = types.index(LoggingMiddleware)
        assert err_idx < time_idx < log_idx
