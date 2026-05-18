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
    FileExchangeHandle,
    ServerConfig,
    build_auth,
    build_instructions,
    configure_logging_from_env,
    register_file_exchange,
    register_server_info_tool,
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

# Module-level singleton holding the FileExchangeHandle that
# ``register_file_exchange`` returns from ``make_server()``.  Captured so tool
# bodies can call ``get_file_exchange().publish(...)`` (see issue #176 for the
# work that wires scholar tools to actually publish ``FileRef`` objects).
_file_exchange: FileExchangeHandle | None = None


def get_file_exchange() -> FileExchangeHandle:
    """Return the file-exchange handle captured by ``make_server()``.

    Raises:
        RuntimeError: If ``make_server()`` has not run yet.
    """
    if _file_exchange is None:
        raise RuntimeError(
            "file exchange is not initialised — call make_server() first"
        )
    return _file_exchange


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
    """Backward-compat wrapper around ``fastmcp_pvl_core.build_remote_auth``.

    Raises:
        ConfigurationError: under pvl-core 2.x the underlying builder raises
            on OIDC discovery failure / missing ``httpx`` / incomplete
            discovery document instead of returning ``None``. ``None`` is
            still returned when no remote-auth config is present at all.
    """
    from fastmcp_pvl_core import build_remote_auth

    return build_remote_auth(_load_server_config())


def _build_bearer_auth() -> object | None:
    """Backward-compat wrapper around ``fastmcp_pvl_core.build_bearer_auth``.

    Raises:
        ConfigurationError: under pvl-core 2.x the underlying builder raises
            when ``SCHOLAR_MCP_BEARER_TOKENS_FILE`` is set but the file is
            missing, unparseable, or schema-invalid.
    """
    from fastmcp_pvl_core import build_bearer_auth

    return build_bearer_auth(_load_server_config())


def _build_oidc_auth() -> object | None:
    """Backward-compat wrapper around ``fastmcp_pvl_core.build_oidc_proxy_auth``.

    Note that pvl-core's ``build_oidc_proxy_auth`` itself does not raise
    ``ConfigurationError`` — but it calls ``OIDCProxy(...)``, whose
    ``__init__`` performs OIDC discovery against the configured
    ``oidc_config_url``. Discovery failures raise raw ``httpx.HTTPError``
    (network/HTTP) or ``pydantic.ValidationError`` (malformed discovery
    doc) which propagate unchanged through this wrapper. Upstream issue
    to normalise these to ``ConfigurationError`` for symmetry with the
    remote-auth path is tracked separately.
    """
    from fastmcp_pvl_core import build_oidc_proxy_auth

    return build_oidc_proxy_auth(_load_server_config())


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
        transport: ``"stdio"`` / ``"http"`` / ``"sse"``.  Logged for
            operational visibility and passed through to
            ``register_file_exchange`` (``"stdio"`` disables the facade by
            default; anything else is treated as HTTP-class).
            ``SCHOLAR_MCP_FILE_EXCHANGE_ENABLED`` can override the
            on/off default per-transport.
        config: Optional pre-loaded config; defaults to env-based load.

    Returns:
        A configured :class:`fastmcp.FastMCP` instance.
    """
    if config is None:
        from scholar_mcp.config import load_config

        config = load_config()
    configure_logging_from_env()

    auth = build_auth(config.server)
    auth_mode = _core_resolve_auth_mode(config.server)
    # Belt-and-braces invariant: pvl-core 2.x's build_auth returns None iff
    # resolve_auth_mode returns "none", and raises ConfigurationError on real
    # misconfig (no silent downgrade). A mismatch would indicate a pvl-core
    # regression that silently degraded a configured auth mode to None.
    # Explicit raise rather than ``assert`` so the guard survives
    # ``python -O`` / ``PYTHONOPTIMIZE=1``.
    if (auth is None) != (auth_mode == "none"):
        raise RuntimeError(
            f"pvl-core auth/mode invariant violation: auth={auth!r} "
            f"mode={auth_mode!r} — refusing to start an unauthenticated "
            "server while resolve_auth_mode reports a configured mode"
        )
    if auth_mode == "none":
        logger.warning(
            "No auth configured — server accepts unauthenticated connections"
        )
    elif transport == "stdio":
        # FastMCP's stdio transport skips auth enforcement on incoming
        # messages (stdio has no Authorization header), so a configured
        # verifier is built but never consulted. Log this as a WARNING
        # rather than the misleading "Auth enabled: mode=X" so operators
        # don't trust startup logs that promise enforcement they won't get.
        logger.warning(
            "auth_configured_but_stdio_skips_enforcement mode=%s — "
            "FastMCP's stdio transport bypasses all auth providers; "
            "switch to --transport http to actually exercise auth",
            auth_mode,
        )
    else:
        # Unified shape across all non-"none" modes (bearer-single,
        # bearer-mapped, oidc-proxy, remote, multi). Sub-builders emit their
        # own DEBUG lines if operators need the bearer/OIDC sub-mode for
        # multi-auth deployments.
        logger.info("Auth enabled: mode=%s", auth_mode)

    try:
        pkg_ver = _pkg_version("pvliesdonk-scholar-mcp")
    except PackageNotFoundError:
        pkg_ver = "unknown"

    server_name = config.server_name or _DEFAULT_SERVER_NAME

    logger.info(
        "Server config: name=%s version=%s transport=%s auth=%s mode=%s cache_dir=%s",
        server_name,
        pkg_ver,
        transport,
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

    # Optional: enable opt-in per-subject authorization on tools / resources /
    # prompts.  See fastmcp-pvl-core's README "Authorization" section for the
    # design.  Tools, resources, and prompts opt in by setting
    # ``meta={"required_scope": "<scope>"}``; absence of the key means
    # unrestricted.  The middleware is only installed when ``acl_path`` is set.
    #
    # from fastmcp_pvl_core import (
    #     AuthorizationMiddleware,
    #     load_acl,
    #     make_acl_authorizer,
    # )
    #
    # if config.acl_path is not None:
    #     authorizer = make_acl_authorizer(load_acl(config.acl_path))
    #     mcp.add_middleware(AuthorizationMiddleware(authorizer=authorizer))

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

    register_server_info_tool(
        mcp,
        server_name=server_name,
        server_version=pkg_ver,
        # DOMAIN-UPSTREAM-START — wire upstream version reporting for servers
        # that talk to a single remote service. Scholar consumes multiple
        # upstreams (S2/OpenAlex/EPO/OpenLibrary/...) with no canonical
        # "the upstream", so this block stays empty by default. Uncomment if
        # we ever want to surface a primary upstream's version through
        # get_server_info.
        # upstream_version=lambda: _upstream_client.remote_version(),
        # upstream_label="semantic-scholar",
        # DOMAIN-UPSTREAM-END
    )

    # DOMAIN-WIRING-START — project-specific wiring (custom HTTP routes,
    # transforms, mode toggles, alternative middleware, additional registrations);
    # kept across copier update. Leave empty for projects that don't customise
    # make_server() beyond the standard scaffold.
    # DOMAIN-WIRING-END

<<<<<<< before updating
    # Capture the FileExchangeHandle into the module-level singleton so tool
    # bodies can call ``get_file_exchange().publish(...)`` once they start
    # producing FileRefs (tracked in #176). We pass our resolved transport
    # explicitly (rather than "auto") so the CLI ``--transport`` flag wins
    # over ``SCHOLAR_MCP_TRANSPORT`` / ``FASTMCP_TRANSPORT`` env vars, which
    # the facade's "auto" mode reads.
    global _file_exchange
    _file_exchange = register_file_exchange(
=======
    # DOMAIN-FILE-EXCHANGE-START — file-exchange wiring (download direction
    # always; upload direction opt-in by uncommenting). Kept across copier
    # update so opt-in customisations (consumer_sink=, produces=, upload
    # receiver) survive subsequent template updates.
    #
    # To publish files from a tool body, capture the returned handle
    # — see docs/guides/file-exchange.md for the module-level singleton
    # pattern (e.g. ``_file_exchange = register_file_exchange(...)``).
    register_file_exchange(
>>>>>>> after updating
        mcp,
        # ``namespace`` is the server's logical name per pvl-core's docstring —
        # used as ``FileRef.origin_server`` and the exchange namespace. Pass the
        # resolved ``server_name`` so peers see the same identity as
        # ``get_server_info`` / FastMCP / the startup log.
        namespace=server_name,
        env_prefix=_ENV_PREFIX,
        transport="stdio" if transport == "stdio" else "http",
    )

    # Optional upload direction — uncomment + flesh out the helpers below
    # to accept agent-pushed files via POST /<namespace>/uploads/{token}.
    # The route mounts only when transport is HTTP/SSE AND
    # SCHOLAR_MCP_BASE_URL is set; sync receivers run in a thread.
    # See docs/guides/file-exchange.md for the full pattern. When
    # uncommenting, move the two ``from`` imports below to the
    # module-level import block at the top of this file.
    #
    # from typing import Any
    #
    # from fastmcp_pvl_core import (
    #     UploadRecord,
    #     register_file_exchange_upload,
    # )
    #
    # def _validate_upload_target(target_id: str, extra: dict[str, Any] | None) -> None:
    #     """Pre-link validator: reject obviously bad target_ids in-band.
    #
    #     Runs inside create_upload_link before the token is minted, so an
    #     LLM gets a clean tool error rather than after a wasted upload
    #     round-trip.
    #     """
    #     # Example: reject anything outside the domain's allowlist.
    #     # raise ValueError(f"target_id not allowed: {target_id}")
    #     pass
    #
    # def _upload_receiver(record: UploadRecord, body: bytes) -> dict[str, Any]:
    #     """Commit the uploaded bytes. Raise ValueError → 400,
    #     FileExistsError → 409, anything else → 500 (with traceback
    #     logged). Return value MUST be a dict — non-dict returns are
    #     treated as receiver bugs (500 + WARNING log)."""
    #     # TODO: replace with your storage logic.
    #     return {"path": record.target_id, "size_bytes": len(body)}
    #
    # register_file_exchange_upload(
    #     mcp,
    #     namespace="scholar-mcp",
    #     env_prefix=_ENV_PREFIX,
    #     transport="auto",
    #     receiver=_upload_receiver,
    #     pre_link_validator=_validate_upload_target,
    # )
    # DOMAIN-FILE-EXCHANGE-END

    return mcp
