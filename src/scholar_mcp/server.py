"""Scholar MCP — FastMCP server entry point.

Composes the primitives from ``fastmcp-pvl-core`` into a
project-specific ``make_server()``.  See
https://gofastmcp.com/servers for the FastMCP server surface and
``fastmcp-pvl-core``'s README for the composable helpers used below.
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from fastmcp import FastMCP
from fastmcp_pvl_core import (
    HealthCheck,
    ServerConfig,  # noqa: F401  — re-exported for downstream projects' convenience
    apply_tool_visibility,
    build_auth,
    build_event_store,  # noqa: F401  — re-exported for downstream projects' convenience
    build_kv_store,  # noqa: F401  — re-exported for downstream projects' convenience
    configure_logging_from_env,
    configure_task_backend,
    env,  # also used by DOMAIN-WIRING additions, so no new import is needed there
    finalize_instructions,
    instructions_for,
    normalise_http_path,
    register_health_routes,
    register_server_info_tool,
    resolve_auth_mode,
    wire_middleware_stack,
)

from scholar_mcp._s2_client import S2_KEEPALIVE_STATUS
from scholar_mcp._server_apps import register_apps
from scholar_mcp._server_deps import server_lifespan
from scholar_mcp.config import ProjectConfig
from scholar_mcp.prompts import register_prompts
from scholar_mcp.resources import register_resources
from scholar_mcp.tools import register_tools

logger = logging.getLogger(__name__)

_ENV_PREFIX = "SCHOLAR_MCP"


def make_server(
    *,
    transport: str = "stdio",
    config: ProjectConfig | None = None,
    http_path: str | None = None,
) -> FastMCP:
    """Construct the Scholar MCP FastMCP server.

    Args:
        transport: ``"stdio"`` / ``"http"`` / ``"sse"``.  Gates any
            transport-specific wiring added in the DOMAIN-WIRING block
            (e.g. HTTP-only custom routes, which cannot be served under
            stdio), gates the template's own liveness and readiness
            routes, which register for ``"http"`` alone, and appears as
            ``transport=%s`` in the startup log.
        config: Optional pre-loaded config; default loads from env.
        http_path: The MCP mount path the caller will hand to
            ``http_app(path=...)``.  The health routes derive their prefix
            from it, so the CLI passes the value it resolved; unset, the
            same ``SCHOLAR_MCP_HTTP_PATH``-or-``/mcp`` fallback the
            CLI uses applies, so a direct ``make_server(transport="http")``
            and ``serve --transport http`` publish the routes at the same
            place.

    Returns:
        A configured :class:`fastmcp.FastMCP` instance.
    """
    config = config or ProjectConfig.from_env()
    configure_logging_from_env()
    mount_path = normalise_http_path(http_path or env(_ENV_PREFIX, "HTTP_PATH"))

    # One source for the name, so `FastMCP(name=...)` below and the shaped
    # instruction identity cannot disagree.  `ProjectConfig.server_name`
    # defaults to `SCHOLAR_MCP_SERVER_NAME` (falling back to the project
    # name) via a default_factory, so the operator override still works
    # unchanged — but a config passed in programmatically now wins, which
    # reading the environment here would have ignored.  Instructions are
    # composed by pvl-core's InstructionsBuilder below and finalised last; see
    # finalize_instructions() at the end.
    server_name = config.server_name

    auth = build_auth(config.server)
    auth_mode = resolve_auth_mode(config.server) if auth is not None else "none"
    if auth_mode == "none":
        logger.warning(
            "No auth configured — server accepts unauthenticated connections"
        )
    else:
        logger.info("Auth enabled: mode=%s", auth_mode)

    try:
        pkg_ver = _pkg_version("pvliesdonk-scholar-mcp")
    except PackageNotFoundError:
        pkg_ver = "unknown"

    logger.info(
        "Server config: version=%s name=%s transport=%s auth=%s",
        pkg_ver,
        server_name,
        transport,
        auth_mode,
    )

    mcp = FastMCP(
        name=server_name,
        lifespan=server_lifespan,
        auth=auth,
    )

    wire_middleware_stack(mcp)

    # Background-task backend (SEP-2663 / Docket).  Unconditional and
    # template-owned: fastmcp-tasks (and pydocket with it) ships in
    # fastmcp-pvl-core's base dependencies, so the backend is always
    # configurable, and whether this server actually uses tasks is decided
    # by registering ``task=True`` tools — not by packaging or by an opt-in
    # switch here.  The helper registers the SEP-2663 tasks extension on
    # ``mcp`` with the resolved backend — fastmcp refuses to start a server
    # carrying task-enabled tools without one — so doing it inside
    # ``make_server`` covers both CLI paths (``server.run(...)`` and the
    # uvicorn ``http_app()`` one).
    # ``SCHOLAR_MCP_TASKS_URL`` selects the backend; unset, a
    # ``redis://`` ``SCHOLAR_MCP_KV_STORE_URL`` is reused so one URL
    # configures every stateful subsystem, and otherwise the ``memory://``
    # default applies.  The queue name is derived from the env prefix, so
    # two servers sharing one Redis do not share a queue.
    configure_task_backend(mcp, _ENV_PREFIX, config.server)

    # Server instructions are composed, not templated: every contributor adds
    # a snippet to the builder (identity here; core register_* helpers add
    # their workflow prose; domain code adds its own via
    # ``instructions_for(mcp).add(text, role=InstructionRole.WORKFLOWS,
    # requires_tools=(...))`` in the DOMAIN-WIRING block. General contributors
    # may use only INSTANCE, CAPABILITIES, and WORKFLOWS; pvl-core reserves the
    # shaped identity, operator routing/policy, and documentation roles.
    # ``finalize_instructions`` renders them once, after tool visibility.
    instructions_for(mcp).identity(
        server_name, "Scholarly papers, patents, books, standards and PDF conversion"
    )
    # The docs site publishes llms.txt per version (mkdocs-llmstxt, mike);
    # `/latest/` resolves once the first release has published the site.
    instructions_for(mcp).documentation(
        "https://pvliesdonk.github.io/scholar-mcp/latest/llms.txt"
    )

    register_tools(mcp)
    register_resources(mcp)
    register_prompts(mcp)
    register_apps(mcp)

    register_server_info_tool(
        mcp,
        server_name=server_name,
        server_version=pkg_ver,
        # DOMAIN-UPSTREAM-START — wire upstream version reporting for servers
        # that talks to a single remote service. Scholar consumes many upstreams
        # (S2/OpenAlex/EPO/OpenLibrary/...) with no canonical "the upstream",
        # so this slot reports the one piece of upstream state an operator
        # cannot otherwise see: whether the configured Semantic Scholar key
        # still buys authenticated quota (#229).
        #
        # Reported here rather than as a `/health/ready` check on purpose. A
        # readiness failure answers 503 for the whole server, dropping it from
        # rotation wherever something polls that route, and that does not
        # revive a revoked key -- while OpenAlex, Crossref, EPO, OpenLibrary
        # and the standards sources carry on serving.
        upstream_version=S2_KEEPALIVE_STATUS.as_dict,
        upstream_label="semantic_scholar",
        # DOMAIN-UPSTREAM-END
    )

    # Readiness checks for ``<prefix>/health/ready``, registered below once
    # the DOMAIN-WIRING block has had its say.  pvl-core contributes the
    # ``kv_store`` write probe itself; this dict is the domain hook, filled
    # from inside the block (the name ``kv_store`` is reserved).  A check is
    # a zero-arg callable, sync or async, answering "does this make the
    # server unable to serve" — falsy or raising means not-ready and the
    # route answers 503.  Nothing about *how* it answers is prescribed:
    # a cached flag a background task keeps fresh is as valid as a live
    # round-trip, and anything touching the network should be async so the
    # five-second ceiling applies.  A partial degradation you would rather
    # report than be taken out of rotation for belongs in ``get_server_info``.
    # Two shapes that both fit:
    #
    #   health_checks["upstream_key"] = lambda: _keepalive.last_ok   # cached flag
    #   health_checks["index"] = _index.is_loaded                    # async probe
    health_checks: dict[str, HealthCheck] = {}

    # DOMAIN-WIRING-START — project-specific wiring (custom HTTP routes,
    # transforms, mode toggles, alternative middleware, additional registrations);
    # kept across copier update. Leave empty for projects that don't customise
    # make_server() beyond the standard scaffold.

    if config.read_only:
        mcp.disable(tags={"write"})
    if not config.epo_configured:
        # Hide patent-related tools when the EPO OPS credentials aren't set --
        # otherwise the model sees ``search_patents``/etc. in its tool list and
        # fails at call time with an auth error.
        mcp.disable(tags={"patent"})

    # ``requires_tools`` keeps this honest: pvl-core drops a snippet whose
    # required tools are hidden, so a read-only deployment -- where these four
    # are disabled by tag -- never sees a sentence about tools it does not have.
    from fastmcp_pvl_core import InstructionRole

    instructions_for(mcp).add(
        "This instance is in read-write mode: alongside the read-only tools, "
        "it exposes write-tagged tools that populate the local cache by "
        "downloading open-access PDFs and converting them to Markdown. Their "
        "results persist, so a repeated request is served from the cache "
        "rather than re-downloaded.",
        role=InstructionRole.WORKFLOWS,
        requires_tools=(
            "fetch_paper_pdf",
            "convert_pdf_to_markdown",
            "fetch_and_convert",
            "fetch_pdf_by_url",
        ),
    )

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
    #     from fastmcp_pvl_core import add_transfer_workflow, build_transfer_links
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
    #
    #     # Contribute the core's capability-link workflow prose for your tool
    #     # (dropped automatically if the tool is hidden by TOOLS_DENY):
    #     add_transfer_workflow(mcp, download_tool="share_document")
    # DOMAIN-WIRING-END

    # Unauthenticated liveness (``<prefix>/health``, static 200) and readiness
    # (``<prefix>/health/ready``, 503 when any check fails) routes for a
    # container orchestrator; ``compose.yml`` probes the first.  They sit
    # outside the MCP mount and outside auth, which is what a probe needs.
    # ``<prefix>`` is the mount path minus a conventional trailing ``mcp``
    # segment, so the default ``/mcp`` publishes ``/health`` and
    # ``/scholar/mcp`` publishes ``/scholar/health`` — two servers on one
    # hostname never collide.  Registered for the http transport only: it is
    # the one the CLI mounts at ``http_path``, so it is the only one where
    # the derived prefix is a fact rather than a guess, and under stdio there
    # is no HTTP app at all.  ``SCHOLAR_MCP_HEALTH_DETAIL`` (``status``
    # / ``standard`` / ``full``) decides how much the bodies say.
    if transport == "http":
        register_health_routes(
            mcp,
            config.server,
            server_version=pkg_ver,
            http_path=mount_path,
            env_prefix=_ENV_PREFIX,
            checks=health_checks,
        )

    # Operator tool visibility (SCHOLAR_MCP_TOOLS_ALLOW /
    # SCHOLAR_MCP_TOOLS_DENY) applies last: fastmcp resolves visibility
    # transforms in call order, so the operator's lists win over any
    # visibility calls in the wiring above, and pvl-core's zero-tools-exposed
    # diagnostic judges the full registered tool set.
    apply_tool_visibility(mcp, config.server)

    # Render the composed instructions exactly once, after visibility: a
    # snippet whose required tools are hidden is dropped,
    # SCHOLAR_MCP_INSTANCE_DESCRIPTION supplies operator routing,
    # SCHOLAR_MCP_INSTRUCTIONS_EXTRA supplies operator policy, and the
    # legacy SCHOLAR_MCP_INSTRUCTIONS full replacement still wins with a
    # deprecation warning. Must run synchronously and stay the last call that
    # touches tools or instructions.
    finalize_instructions(mcp, config.server, env_prefix=_ENV_PREFIX)

    return mcp
