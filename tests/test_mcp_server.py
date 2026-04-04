"""Tests for MCP server factory — auth wiring and read-only mode."""

from __future__ import annotations

import logging

import pytest

from scholar_mcp.mcp_server import create_server

# OIDC vars required by _build_oidc_auth()
_OIDC_REQUIRED = {
    "SCHOLAR_MCP_BASE_URL": "https://mcp.example.com",
    "SCHOLAR_MCP_OIDC_CONFIG_URL": "https://auth.example.com/.well-known/openid-configuration",
    "SCHOLAR_MCP_OIDC_CLIENT_ID": "mcp-client",
    "SCHOLAR_MCP_OIDC_CLIENT_SECRET": "test-secret",
}


class TestAuthModeSelection:
    """Tests for create_server() auth mode selection.

    Covers all four modes: multi (both configured), bearer-only,
    OIDC-only, and none.
    """

    def test_no_auth_when_nothing_configured(self) -> None:
        """Default: no auth when no auth env vars are set."""
        server = create_server()
        assert server.auth is None

    def test_bearer_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bearer-only: StaticTokenVerifier when only BEARER_TOKEN is set."""
        from fastmcp.server.auth import StaticTokenVerifier

        monkeypatch.setenv("SCHOLAR_MCP_BEARER_TOKEN", "my-secret-token")
        server = create_server()
        assert isinstance(server.auth, StaticTokenVerifier)

    def test_oidc_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OIDC-only: OIDCProxy when only OIDC vars are set."""
        from unittest.mock import MagicMock, patch

        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_oidc = MagicMock()
        mock_cls = MagicMock(return_value=mock_oidc)
        with patch("fastmcp.server.auth.oidc_proxy.OIDCProxy", mock_cls):
            server = create_server()

        assert server.auth is mock_oidc

    def test_multi_auth_when_both_configured(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Multi-auth: MultiAuth when both BEARER_TOKEN and OIDC vars are set."""
        from unittest.mock import MagicMock, patch

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
            server = create_server()

        assert isinstance(server.auth, MultiAuth)
        assert "Multi-auth enabled" in caplog.text

    def test_multi_auth_structure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OIDCProxy must be server= (not in verifiers=) for OAuth routes to mount."""
        from unittest.mock import MagicMock, patch

        from fastmcp.server.auth import MultiAuth, StaticTokenVerifier

        monkeypatch.setenv("SCHOLAR_MCP_BEARER_TOKEN", "my-secret-token")
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_oidc = MagicMock()
        mock_cls = MagicMock(return_value=mock_oidc)
        with patch("fastmcp.server.auth.oidc_proxy.OIDCProxy", mock_cls):
            server = create_server()

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
        server = create_server()
        # No write-tagged tools should be present in read-only mode.
        write_tools = [
            t for t in await server.list_tools() if "write" in (t.tags or set())
        ]
        assert write_tools == []

    async def test_read_write_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Setting READ_ONLY=false creates server in read-write mode."""
        monkeypatch.setenv("SCHOLAR_MCP_READ_ONLY", "false")
        server = create_server()
        # Server should be created successfully in read-write mode.
        assert server is not None
