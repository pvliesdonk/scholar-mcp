"""Generic FastMCP server scaffold.

Exposes tools, resources, and prompts registered in the ``_server_*``
submodules.  Uses a lifespan hook to build the service object once at
startup and tear it down on shutdown.

The server is configured entirely via environment variables (see
:mod:`scholar_mcp.config`).  Call :func:`create_server` to
build a configured :class:`~fastmcp.FastMCP` instance.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from fastmcp import FastMCP

from scholar_mcp.config import _ENV_PREFIX, load_config

from ._server_deps import make_service_lifespan
from ._server_prompts import register_prompts
from ._server_resources import register_resources
from ._server_tools import register_tools

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def _build_default_instructions(*, read_only: bool) -> str:
    """Build the default instructions string based on read-only state.

    Args:
        read_only: Whether write tools are disabled on this instance.

    Returns:
        Instructions string suitable for the ``instructions`` parameter
        of :class:`~fastmcp.FastMCP`.
    """
    write_line = (
        "This instance is READ-ONLY — write tools are not available."
        if read_only
        else "This instance is READ-WRITE — write tools are available."
    )
    return (
        "A FastMCP service. "
        f"{write_line} "
        f"Operators: set {_ENV_PREFIX}_INSTRUCTIONS to describe this "
        "service's domain and capabilities."
    )


def _build_bearer_auth() -> Any:
    """Build a StaticTokenVerifier from ``SCHOLAR_MCP_BEARER_TOKEN``.

    When the env var is set (non-empty), returns a
    :class:`~fastmcp.server.auth.StaticTokenVerifier` that
    validates ``Authorization: Bearer <token>`` headers against the
    configured static token.

    Returns:
        A configured ``StaticTokenVerifier``, or ``None`` when the env var
        is absent or empty.
    """
    token = os.environ.get(f"{_ENV_PREFIX}_BEARER_TOKEN", "").strip()
    if not token:
        logger.debug("Bearer auth: BEARER_TOKEN not set — skipping")
        return None
    logger.debug("Bearer auth: BEARER_TOKEN is set (value redacted)")
    from fastmcp.server.auth import StaticTokenVerifier

    return StaticTokenVerifier(
        tokens={token: {"client_id": "bearer", "scopes": ["read", "write"]}}
    )


def _build_oidc_auth() -> Any:
    """Build an OIDCProxy auth provider from environment variables, or return None.

    All four of ``BASE_URL``, ``OIDC_CONFIG_URL``, ``OIDC_CLIENT_ID``, and
    ``OIDC_CLIENT_SECRET`` must be set to enable authentication.  If any is
    absent the server starts unauthenticated.

    By default the proxy verifies the upstream ``id_token`` (a standard JWT
    per OIDC Core) instead of the ``access_token``.  This works with every
    OIDC provider — including those that issue opaque access tokens (e.g.
    Authelia).  Set ``SCHOLAR_MCP_OIDC_VERIFY_ACCESS_TOKEN=true`` to revert to
    access-token verification when you know the provider issues JWT access
    tokens and you need audience-claim validation on that token.

    Returns:
        A configured :class:`~fastmcp.server.auth.oidc_proxy.OIDCProxy` instance,
        or ``None`` when authentication is disabled.
    """
    base_url = os.environ.get(f"{_ENV_PREFIX}_BASE_URL", "").strip()
    config_url = os.environ.get(f"{_ENV_PREFIX}_OIDC_CONFIG_URL", "").strip()
    client_id = os.environ.get(f"{_ENV_PREFIX}_OIDC_CLIENT_ID", "").strip()
    client_secret = os.environ.get(f"{_ENV_PREFIX}_OIDC_CLIENT_SECRET", "").strip()

    if not all([base_url, config_url, client_id, client_secret]):
        missing = [
            name
            for name, val in [
                ("BASE_URL", base_url),
                ("OIDC_CONFIG_URL", config_url),
                ("OIDC_CLIENT_ID", client_id),
                ("OIDC_CLIENT_SECRET", client_secret),
            ]
            if not val
        ]
        logger.debug("OIDC auth: disabled — missing env vars: %s", ", ".join(missing))
        return None

    try:
        from fastmcp.server.auth.oidc_proxy import OIDCProxy
    except ImportError as exc:
        raise RuntimeError(
            "OIDC auth requires httpx. Install with: pip install 'scholar-mcp[mcp]'"
        ) from exc

    jwt_signing_key = (
        os.environ.get(f"{_ENV_PREFIX}_OIDC_JWT_SIGNING_KEY", "").strip() or None
    )
    audience = os.environ.get(f"{_ENV_PREFIX}_OIDC_AUDIENCE", "").strip() or None
    raw_scopes = os.environ.get(f"{_ENV_PREFIX}_OIDC_REQUIRED_SCOPES", "openid").strip()
    required_scopes = [s.strip() for s in raw_scopes.split(",") if s.strip()] or [
        "openid"
    ]

    verify_access_token = os.environ.get(
        f"{_ENV_PREFIX}_OIDC_VERIFY_ACCESS_TOKEN", ""
    ).strip().lower() in ("true", "1", "yes")
    verify_id_token = not verify_access_token

    logger.debug(
        "OIDC auth config:\n"
        "  config_url          = %s\n"
        "  client_id           = %s\n"
        "  client_secret       = <redacted>\n"
        "  base_url            = %s\n"
        "  audience            = %s\n"
        "  required_scopes     = %s\n"
        "  jwt_signing_key     = %s\n"
        "  verify_id_token     = %s\n"
        "  verify_access_token = %s",
        config_url,
        client_id,
        base_url,
        audience or "(not set)",
        required_scopes,
        "(set)" if jwt_signing_key else "(not set)",
        verify_id_token,
        verify_access_token,
    )

    if verify_id_token and "openid" not in required_scopes:
        logger.warning(
            "OIDC: verify_id_token=True requires the 'openid' scope but it is "
            "not in SCHOLAR_MCP_OIDC_REQUIRED_SCOPES — the id_token may "
            "be absent from the token response; add 'openid' to the scope list "
            "or set SCHOLAR_MCP_OIDC_VERIFY_ACCESS_TOKEN=true"
        )

    if jwt_signing_key is None and sys.platform.startswith("linux"):
        logger.warning(
            "OIDC: SCHOLAR_MCP_OIDC_JWT_SIGNING_KEY is not set — "
            "the JWT signing key is ephemeral on Linux; all clients must "
            "re-authenticate after every server restart"
        )

    if verify_id_token:
        logger.info(
            "OIDC: verifying upstream id_token (works with opaque access tokens)"
        )
    else:
        logger.info(
            "OIDC: verifying upstream access_token as JWT "
            "(SCHOLAR_MCP_OIDC_VERIFY_ACCESS_TOKEN=true)"
        )

    return OIDCProxy(
        config_url=config_url,
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
        audience=audience,
        required_scopes=required_scopes,
        jwt_signing_key=jwt_signing_key,
        verify_id_token=verify_id_token,
    )


def build_event_store() -> Any:
    """Build an event store for HTTP transport SSE resumability.

    Returns an :class:`~fastmcp.server.event_store.EventStore` backed by
    an in-memory store by default.  For production deployments, replace the
    backing store with a persistent :class:`~key_value.aio.AsyncKeyValue`
    backend (e.g. Redis) so events survive restarts.

    The event store is only meaningful for the ``http`` transport — pass the
    return value to :meth:`~fastmcp.FastMCP.http_app` via the ``event_store``
    kwarg to enable client reconnection / SSE event replay.

    Returns:
        A configured :class:`~fastmcp.server.event_store.EventStore`.
    """
    from fastmcp.server.event_store import EventStore

    return EventStore()  # type is EventStore; typed as Any to avoid top-level import


def create_server(*, transport: str = "stdio") -> FastMCP:
    """Create and configure the FastMCP server.

    Reads configuration from environment variables via :func:`load_config`.
    Write tools are tagged with ``{"write"}`` and hidden via
    ``mcp.disable(tags={"write"})`` when ``READ_ONLY=true``.

    Server identity is configurable via:

    - ``SCHOLAR_MCP_SERVER_NAME``: MCP server name shown to clients
      (default ``"scholar-mcp"``).
    - ``SCHOLAR_MCP_INSTRUCTIONS``: system-level instructions injected
      into LLM context (default: dynamic description reflecting read-only state).

    Args:
        transport: Active transport (``"stdio"``, ``"sse"``, or ``"http"``).
            Passed to :func:`register_tools` so tools can conditionally register
            HTTP-only endpoints (e.g. artifact download handlers).

    Returns:
        A fully configured :class:`~fastmcp.FastMCP` instance ready to run.
    """
    config = load_config()
    is_read_only = config.read_only

    server_name = os.environ.get(f"{_ENV_PREFIX}_SERVER_NAME", "scholar-mcp")
    default_instructions = _build_default_instructions(read_only=is_read_only)
    instructions = os.environ.get(f"{_ENV_PREFIX}_INSTRUCTIONS", default_instructions)

    bearer_auth = _build_bearer_auth()
    oidc_auth = _build_oidc_auth()

    if bearer_auth and oidc_auth:
        from fastmcp.server.auth import MultiAuth

        auth = MultiAuth(server=oidc_auth, verifiers=[bearer_auth])
        auth_mode = "multi"
        logger.info("Multi-auth enabled: bearer token + OIDC (either accepted)")
    elif bearer_auth:
        auth = bearer_auth
        auth_mode = "bearer"
        logger.info("Bearer token auth enabled")
    elif oidc_auth:
        auth = oidc_auth
        auth_mode = "oidc"
        logger.info("OIDC auth enabled")
    else:
        auth = None
        auth_mode = "none"
        logger.info("No auth configured — server accepts unauthenticated connections")

    logger.info(
        "Server config: name=%s auth=%s mode=%s",
        server_name,
        auth_mode,
        "read-only" if is_read_only else "read-write",
    )

    mcp = FastMCP(
        server_name,
        instructions=instructions,
        lifespan=make_service_lifespan,
        auth=auth,
    )

    register_tools(mcp, transport=transport)
    register_resources(mcp)
    register_prompts(mcp)

    # --- Visibility: hide write-tagged components in read-only mode ---

    if is_read_only:
        mcp.disable(tags={"write"})

    return mcp
