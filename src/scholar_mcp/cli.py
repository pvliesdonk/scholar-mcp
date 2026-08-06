"""Command-line interface for scholar-mcp.

Provides ``serve``, ``sync-standards``, and ``cache`` subcommands.  The
entry point is :func:`main`, registered as ``scholar-mcp`` in
``pyproject.toml``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

import httpx
import typer
from fastmcp_pvl_core import (
    build_event_store,
    configure_logging_from_env,
    maybe_start_debugpy,
    normalise_http_path,
)

from scholar_mcp.config import _ENV_PREFIX, ProjectConfig

if TYPE_CHECKING:
    from scholar_mcp._standards_sync import Loader

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="scholar-mcp",
    help="Scholar MCP — academic literature server.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
)

Transport = Literal["stdio", "http", "sse"]


@app.callback()
def _root(
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Enable debug logging."
    ),
) -> None:
    """Root callback — bootstraps logging for every subcommand."""
    configure_logging_from_env(verbose=verbose)
    if verbose:
        # httpx is noisy at DEBUG; keep it at WARNING.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


@app.command()
def serve(
    transport: Transport = typer.Option(
        "stdio", help="MCP transport (stdio / http / sse)."
    ),
    host: str | None = typer.Option(
        None, help=f"Bind host (http only; default: ${_ENV_PREFIX}_HOST or 127.0.0.1)."
    ),
    port: int | None = typer.Option(
        None, help=f"Bind port (http only; default: ${_ENV_PREFIX}_PORT or 8000)."
    ),
    http_path: str | None = typer.Option(
        None,
        "--http-path",
        "--path",
        help=(f"Mount path (http only, default: ${_ENV_PREFIX}_HTTP_PATH or /mcp)."),
    ),
) -> None:
    """Run the MCP server."""
    try:
        from scholar_mcp.server import make_server
    except ImportError as exc:
        logger.error(
            "FastMCP is not installed. Install with: "
            "pip install pvliesdonk-scholar-mcp[mcp]"
        )
        raise typer.Exit(code=1) from exc

    from fastmcp_pvl_core import ConfigurationError

    # Optional remote-debugger listener — placed in ``serve`` (not the
    # typer root callback) so non-server commands like ``--help``,
    # ``--version``, or future ``dump-config``-style subcommands are
    # never blocked by ``SCHOLAR_MCP_DEBUG_WAIT=true``.  No-op
    # unless ``SCHOLAR_MCP_DEBUG_PORT`` is set; ``debugpy`` is only
    # present when the image was built with ``--build-arg DEBUG=true``
    # (a missing import logs a WARNING and continues).  ``_root`` has
    # already attached the StreamHandler by the time ``serve`` runs, so
    # the helper's INFO/WARNING logs route through the configured
    # formatter rather than Python's lastResort.
    maybe_start_debugpy(_ENV_PREFIX)

    try:
        # Config loading is inside the guard: ``ServerConfig.from_env``
        # raises ``ConfigurationError`` on a malformed value (e.g. a
        # non-integer SCHOLAR_MCP_PORT) just like the auth builders do on
        # real auth misconfig (OIDC discovery failure, missing httpx,
        # incomplete discovery doc). The exception message is
        # operator-actionable on its own; don't bury it under a
        # multi-screen rich traceback. Print to stderr via ``typer.echo``
        # rather than ``logger.error`` so the message is visible even if
        # the operator runs with ``FASTMCP_LOG_LEVEL=CRITICAL`` or another
        # level that filters ERROR. Operators who want the full chain can
        # re-run with ``-v`` (FASTMCP_LOG_LEVEL=DEBUG) — the DEBUG line
        # below renders the traceback when the level allows it.
        config = ProjectConfig.from_env()
        server = make_server(transport=transport, config=config)
    except ConfigurationError as exc:
        typer.echo(f"ERROR: configuration error: {exc}", err=True)
        logger.debug("configuration_error_traceback", exc_info=True)
        raise typer.Exit(code=1) from exc

    if transport != "http" and (
        host is not None or port is not None or http_path is not None
    ):
        logger.warning("--host, --port and --path are only used with --transport http")

    if transport == "http":
        try:
            import uvicorn
        except ImportError as exc:
            logger.error(
                "HTTP transport requires uvicorn. Install with: "
                "pip install 'pvliesdonk-scholar-mcp[mcp]'"
            )
            raise typer.Exit(code=1) from exc

        path = normalise_http_path(
            http_path or os.environ.get(f"{_ENV_PREFIX}_HTTP_PATH")
        )
        event_store = build_event_store(_ENV_PREFIX, config.server)
        # lifespan="on" is essential: FastMCP's lifespan (startup/shutdown
        # hooks, including service init) runs through the ASGI lifespan
        # protocol.
        uvicorn.run(
            server.http_app(path=path, event_store=event_store),
            host=host if host is not None else config.server.host,
            port=port if port is not None else config.server.port,
            lifespan="on",
            timeout_graceful_shutdown=0,
        )
    else:
        server.run(transport=transport)


# DOMAIN-COMMANDS-START — add domain @app.command()s (and their helpers) below; kept across copier update
cache_app = typer.Typer(
    name="cache",
    help="Manage the Scholar MCP local cache.",
    no_args_is_help=True,
    rich_markup_mode=None,
)
app.add_typer(cache_app, name="cache")


class _Body(StrEnum):
    """Standards bodies known to ``sync-standards``.  Case-insensitive on CLI."""

    ISO = "ISO"
    IEC = "IEC"
    IEEE = "IEEE"
    CEN = "CEN"
    CC = "CC"
    ALL = "all"


@app.command("sync-standards")
def sync_standards(
    body: _Body = typer.Option(
        _Body.ALL,
        "--body",
        case_sensitive=False,
        help="Body to sync.  'all' runs every registered loader.",
    ),
    force: bool = typer.Option(
        False, "--force", help="Bypass upstream-freshness checks and re-sync."
    ),
    cache_dir: Path | None = typer.Option(
        None, "--cache-dir", help="Override cache directory."
    ),
) -> None:
    """Sync Tier 2 standards catalogue data into the local cache.

    Safe to schedule under cron / launchd / systemd timers.

    Exit codes:
        0 — no changes OR synced with updates
        1 — hard failure (no body synced)
        3 — partial failure (some bodies succeeded, some did not)
    """
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._standards_sync import format_reports, run_sync

    async def _run() -> int:
        from scholar_mcp._standards_sync import SyncReport

        config = ProjectConfig.from_env()
        db_path = (cache_dir or config.cache_dir) / "cache.db"
        c = ScholarCache(db_path)
        await c.open()
        http = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
        loaders: list[Loader] = []
        reports: list[SyncReport] = []
        try:
            loaders = _select_loaders(body.value, http=http, token=config.github_token)
            reports = await run_sync(loaders, c, force=force)
        finally:
            await http.aclose()
            await c.close()

        typer.echo(format_reports(reports))

        if not loaders:
            typer.echo("no loaders registered for the requested body")
            return 0
        failures = [r for r in reports if r.errors]
        successes = [r for r in reports if not r.errors]
        if failures and not successes:
            return 1
        if failures and successes:
            return 3
        return 0

    exit_code = asyncio.run(_run())
    raise typer.Exit(code=exit_code)


@cache_app.command("stats")
def cache_stats(
    cache_dir: Path | None = typer.Option(
        None, "--cache-dir", help="Override cache directory."
    ),
) -> None:
    """Show cache statistics (row counts, file size)."""
    from scholar_mcp._cache import ScholarCache

    async def _run() -> None:
        config = ProjectConfig.from_env()
        db_path = (cache_dir or config.cache_dir) / "cache.db"
        if not db_path.exists():
            typer.echo("No cache database found.")
            return
        c = ScholarCache(db_path)
        await c.open()
        stats = await c.stats()
        await c.close()
        for key, val in stats.items():
            typer.echo(f"{key}: {val}")

    asyncio.run(_run())


@cache_app.command("clear")
def cache_clear(
    older_than: int | None = typer.Option(
        None,
        "--older-than",
        help="Only remove entries older than this many days.",
    ),
    cache_dir: Path | None = typer.Option(
        None, "--cache-dir", help="Override cache directory."
    ),
) -> None:
    """Clear cache entries.

    Without ``--older-than``, wipes all cached data (preserves id_aliases).
    With ``--older-than N``, removes only entries older than N days.
    """
    from scholar_mcp._cache import ScholarCache

    async def _run() -> None:
        config = ProjectConfig.from_env()
        db_path = (cache_dir or config.cache_dir) / "cache.db"
        if not db_path.exists():
            typer.echo("No cache database found.")
            return
        c = ScholarCache(db_path)
        await c.open()
        await c.clear(older_than_days=older_than)
        await c.close()
        if older_than is not None:
            typer.echo(f"Cache cleared (older than {older_than} days).")
        else:
            typer.echo("Cache cleared.")

    asyncio.run(_run())


def _select_loaders(
    body: str, *, http: httpx.AsyncClient, token: str | None
) -> list[Loader]:
    """Return loaders matching *body* ('all' returns every registered).

    All loaders share the passed-in ``httpx.AsyncClient``; the caller is
    responsible for closing it.
    """
    from scholar_mcp._sync_cc import CCLoader
    from scholar_mcp._sync_cen import CENLoader
    from scholar_mcp._sync_relaton import RelatonLoader

    registered: list[Loader] = cast(
        "list[Loader]",
        [
            RelatonLoader("ISO", http=http, token=token),
            RelatonLoader("IEC", http=http, token=token),
            RelatonLoader("IEEE", http=http, token=token),
            CCLoader(http=http),
            CENLoader(),
        ],
    )
    if body.upper() == "ALL":
        return registered
    return [loader for loader in registered if loader.body == body.upper()]


# DOMAIN-COMMANDS-END


def main() -> None:
    """CLI entry point — used by ``[project.scripts]`` in pyproject.toml."""
    app()


if __name__ == "__main__":
    main()
