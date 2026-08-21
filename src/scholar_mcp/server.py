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
<<<<<<< before updating
    ServerConfig,
=======
    ServerConfig,  # noqa: F401  — re-exported for downstream projects' convenience
    apply_tool_visibility,
>>>>>>> after updating
    build_auth,
    build_instructions,
    configure_logging_from_env,
    configure_task_backend,
    env,
    register_server_info_tool,
    wire_middleware_stack,
)
from fastmcp_pvl_core import (
    build_event_store as _core_build_event_store,
)
from fastmcp_pvl_core import (
    build_kv_store as build_kv_store,  # re-exported for downstream projects' convenience
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
    """Backward-compat wrapper around ``fastmcp_pvl_core.build_remote_auth``.

    Raises:
        ConfigurationError: The underlying builder raises on OIDC discovery
            failure / missing ``httpx`` / incomplete discovery document
            instead of returning ``None``. ``None`` is still returned when
            no remote-auth config is present at all.
    """
    from fastmcp_pvl_core import build_remote_auth

    return build_remote_auth(_load_server_config())


def _build_bearer_auth() -> object | None:
    """Backward-compat wrapper around ``fastmcp_pvl_core.build_bearer_auth``.

    Raises:
        ConfigurationError: The underlying builder raises when
            ``SCHOLAR_MCP_BEARER_TOKENS_FILE`` is set but the file is
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
        transport: ``"stdio"`` / ``"http"`` / ``"sse"``.  Gates any
            transport-specific wiring added in the DOMAIN-WIRING block
            (e.g. HTTP-only custom routes, which cannot be served under
            stdio) and appears as ``transport=%s`` in the startup log.
        config: Optional pre-loaded config; default loads from env.

    Returns:
        A configured :class:`fastmcp.FastMCP` instance.
    """
    config = config or ProjectConfig.from_env()
    configure_logging_from_env()

    # Background-task backend (SEP-1686 / Docket).  Unconditional and
    # template-owned: pydocket ships in fastmcp-pvl-core's base dependencies,
    # so the backend is always configurable, and whether this server actually
    # uses tasks is decided by registering ``task=True`` tools — not by
    # packaging or by an opt-in switch here.  It mutates fastmcp's
    # process-global settings, which fastmcp reads lazily at root-lifespan
    # entry, so doing it inside ``make_server`` covers both CLI paths (
    # ``server.run(...)`` and the uvicorn ``http_app()`` one).
    # ``SCHOLAR_MCP_TASKS_URL`` selects the backend; unset, a
    # ``redis://`` ``SCHOLAR_MCP_KV_STORE_URL`` is reused so one URL
    # configures every stateful subsystem, and otherwise fastmcp's
    # ``memory://`` default applies.  The queue name is derived from the env
    # prefix, so two servers sharing one Redis do not share a queue.
    configure_task_backend(_ENV_PREFIX, config.server)

    # Operator overrides: SERVER_NAME renames this instance; INSTRUCTIONS
    # replaces the default instructions text (the latter is the override that
    # build_instructions' hint advertises). Both fall back when unset/empty.
    server_name = env(_ENV_PREFIX, "SERVER_NAME") or _DEFAULT_SERVER_NAME
    instructions = env(_ENV_PREFIX, "INSTRUCTIONS") or build_instructions(
        read_only=config.read_only,
        env_prefix=_ENV_PREFIX,
        domain_line=(
            "Scholar MCP — academic literature server: Semantic Scholar + "
            "OpenAlex + Crossref + OpenLibrary + Google Books + EPO (patents) "
            "+ standards (ISO/IEC/IEEE/CEN/CC) enrichment and docling PDF "
            "conversion.  Read-only tools are always available; write-tagged "
            "tools (cache writes) are hidden in read-only mode."
        ),
    )

    auth = build_auth(config.server)
    auth_mode = _core_resolve_auth_mode(config.server)
    # Belt-and-braces invariant: build_auth returns None iff
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

    logger.info(
        "Server config: version=%s name=%s transport=%s auth=%s mode=%s cache_dir=%s",
        pkg_ver,
        server_name,
        transport,
        auth_mode,
        "read-only" if config.read_only else "read-write",
        config.cache_dir,
    )

    mcp = FastMCP(
        name=server_name,
        instructions=instructions,
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
    #
    # -- Transfer subsystem (capability-link upload + download) ----------------
    #
    # Wiring the /transfer/{token} route needs HTTP transport (the route cannot
    # be served under stdio) and, at build time, base_url — pvl-core raises
    # ConfigurationError when it is unset, so gate only on the transport and let
    # that error surface a misconfigured deployment rather than silently
    # dropping the feature. Requires fastmcp-pvl-core >= 4.8.0.
    #
    # First compose a TransferConfig into ProjectConfig (config.py): add
    # ``TransferConfig`` to its ``from fastmcp_pvl_core import (...)`` block, then
    # a ``transfer: TransferConfig = field(default_factory=TransferConfig)`` field
    # in CONFIG-FIELDS and ``transfer=TransferConfig.from_env(_ENV_PREFIX),`` in
    # CONFIG-FROM-ENV. The second line is required — without it the
    # SCHOLAR_MCP_TRANSFER_* env vars are ignored and the defaults always win.
    #
    # Path 1 — the generic tools, the common case. Registers create_download_link
    # and create_upload_link with pvl-core's shared metadata (names, icons, tags):
    #
    # if transport != "stdio":
    #     from fastmcp_pvl_core import register_transfer_routes
    #
    #     register_transfer_routes(
    #         mcp,
    #         config.server,
    #         config.transfer,          # TransferConfig composed into ProjectConfig
    #         sink=_my_transfer_sink,   # implements TransferSink (read/write)
    #         validate=_my_validator,   # TransferValidator: (ref, kind) -> handle
    #         # download_note/upload_note (optional) append a domain sentence to
    #         # the generic tool descriptions — context only, no shape change.
    #     )
    #
    # Path 2 — your own tool over the same capability-link machinery, when the
    # generic pair cannot express it (a different name, a domain-accurate
    # description, domain-specific parameters). build_transfer_links mounts the
    # route and returns a minter, registering no tools; your tool validates the
    # caller ref itself, then mints over the already-validated sink handle:
    #
    # if transport != "stdio":
    #     from fastmcp_pvl_core import build_transfer_links
    #
    #     links = build_transfer_links(
    #         mcp, config.server, config.transfer, sink=_my_transfer_sink
    #     )
    #
    #     @mcp.tool
    #     async def share_document(doc_id: str) -> dict[str, object]:
    #         """Mint a one-shot download link for a document."""
    #         handle = _resolve_and_check(doc_id)  # your validation -> sink handle
    #         return await links.mint_download(handle)
    # DOMAIN-WIRING-END

    # Operator tool visibility (SCHOLAR_MCP_TOOLS_ALLOW /
    # SCHOLAR_MCP_TOOLS_DENY) applies last: fastmcp resolves visibility
    # transforms in call order, so the operator's lists win over any
    # visibility calls in the wiring above, and pvl-core's zero-tools-exposed
    # diagnostic judges the full registered tool set.
    apply_tool_visibility(mcp, config.server)

    return mcp
