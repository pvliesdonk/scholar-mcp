"""Scholar MCP — FastMCP server entry point.

Composes the primitives from ``fastmcp-pvl-core`` into scholar's
``make_server()``.  See https://gofastmcp.com/servers for the FastMCP
server surface and the fastmcp-pvl-core README for the helpers used here.
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from fastmcp import FastMCP
from fastmcp.server.event_store import EventStore
from fastmcp_pvl_core import (
    ServerConfig,
    build_auth,
    build_instructions,
    configure_logging_from_env,
    wire_middleware_stack,
)
from fastmcp_pvl_core import (
    build_event_store as _core_build_event_store,
)
from fastmcp_pvl_core import (
    resolve_auth_mode as _core_resolve_auth_mode,
)

from scholar_mcp._server_deps import make_service_lifespan
from scholar_mcp._server_prompts import register_prompts
from scholar_mcp._server_resources import register_resources
from scholar_mcp._server_tools import register_tools
from scholar_mcp.config import _ENV_PREFIX, ProjectConfig

logger = logging.getLogger(__name__)

_DEFAULT_SERVER_NAME = "scholar-mcp"


def _load_server_config() -> ServerConfig:
    """Compat helper — load ServerConfig slice from scholar env vars.

    Used by backward-compat wrappers ``_resolve_auth_mode`` / ``_build_*_auth``
    that preserve their historical zero-arg call shape for existing tests.
    """
    return ServerConfig.from_env(env_prefix=_ENV_PREFIX)


def _resolve_auth_mode() -> str | None:
    """Backward-compat wrapper — returns ``None`` when core returns ``"none"``."""
    mode = _core_resolve_auth_mode(_load_server_config())
    return None if mode == "none" else mode


def _build_remote_auth() -> object | None:
    """Backward-compat wrapper around ``fastmcp_pvl_core.build_remote_auth``."""
    from fastmcp_pvl_core import build_remote_auth

    return build_remote_auth(_load_server_config())


def _build_bearer_auth() -> object | None:
    """Backward-compat wrapper around ``fastmcp_pvl_core.build_bearer_auth``."""
    from fastmcp_pvl_core import build_bearer_auth

    return build_bearer_auth(_load_server_config())


def _build_oidc_auth() -> object | None:
    """Backward-compat wrapper around ``fastmcp_pvl_core.build_oidc_proxy_auth``."""
    from fastmcp_pvl_core import build_oidc_proxy_auth

    return build_oidc_proxy_auth(_load_server_config())


# Module-level re-export for tests that patch resolve_auth_mode.
resolve_auth_mode = _core_resolve_auth_mode


def build_event_store(url: str | None = None) -> EventStore:
    """Build an ``EventStore`` — thin shim over core's helper.

    Preserves the legacy zero-arg call shape used by cli.py.  When ``url``
    is ``None`` we load ``ServerConfig`` from env so ``SCHOLAR_MCP_EVENT_STORE_URL``
    is honored; when ``url`` is provided explicitly it overrides the env.
    """
    if url is None:
        return _core_build_event_store(_ENV_PREFIX, _load_server_config())
    return _core_build_event_store(_ENV_PREFIX, ServerConfig(event_store_url=url))


def make_server(
    *,
    transport: str = "stdio",
    config: ProjectConfig | None = None,
) -> FastMCP:
    """Construct the Scholar MCP FastMCP server.

    Args:
        transport: ``"stdio"`` / ``"http"`` / ``"sse"``.  Tools that depend
            on HTTP transport (e.g. artifact downloads) are wired only when
            transport != ``"stdio"``.
        config: Optional pre-loaded config; defaults to env-based load.

    Returns:
        A configured :class:`fastmcp.FastMCP` instance.
    """
    if config is None:
        from scholar_mcp.config import load_config

        config = load_config()
    configure_logging_from_env()

    auth = build_auth(config.server)
    auth_mode = _core_resolve_auth_mode(config.server) if auth is not None else "none"
    if auth_mode == "none":
        logger.warning(
            "No auth configured — server accepts unauthenticated connections"
        )
    elif auth_mode == "multi":
        logger.info("Multi-auth enabled: bearer + OIDC")
    else:
        logger.info("Auth enabled: mode=%s", auth_mode)

    try:
        pkg_ver = _pkg_version("pvliesdonk-scholar-mcp")
    except PackageNotFoundError:
        pkg_ver = "unknown"

    server_name = config.server_name or _DEFAULT_SERVER_NAME

    logger.info(
        "Server config: name=%s version=%s auth=%s mode=%s cache_dir=%s",
        server_name,
        pkg_ver,
        auth_mode,
        "read-only" if config.read_only else "read-write",
        config.cache_dir,
    )

    mcp = FastMCP(
        name=server_name,
        instructions=build_instructions(
            read_only=config.read_only,
            env_prefix=_ENV_PREFIX,
            domain_line=(
                "Scholar MCP — academic literature server: Semantic Scholar + "
                "OpenAlex + Crossref + OpenLibrary + Google Books + EPO (patents) "
                "+ standards (ISO/IEC/IEEE/CEN/CC) enrichment and docling PDF "
                "conversion.  Read-only tools are always available; write-tagged "
                "tools (cache writes) are hidden in read-only mode."
            ),
        ),
        lifespan=make_service_lifespan,
        auth=auth,
    )

    wire_middleware_stack(mcp)

    register_tools(mcp)
    register_resources(mcp)
    register_prompts(mcp)

    if config.read_only:
        mcp.disable(tags={"write"})
    if not config.epo_configured:
        # Hide patent-related tools when the EPO OPS credentials aren't set —
        # otherwise the model sees ``search_patents``/etc. in its tool list and
        # fails at call time with an auth error.
        mcp.disable(tags={"patent"})

    return mcp


# Backward-compat alias: existing callers import `create_server`.
create_server = make_server
