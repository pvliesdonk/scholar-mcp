"""Command-line interface for Scholar MCP."""

from __future__ import annotations

from typing import Literal

import typer
from fastmcp_pvl_core import (
    ConfigurationError,
    build_event_store,
    configure_logging_from_env,
    maybe_start_debugpy,
    normalise_http_path,
    run_http,
)

from scholar_mcp.config import _ENV_PREFIX, ProjectConfig

app = typer.Typer(
    name="scholar-mcp",
    help="Scholarly papers, patents, books, standards and PDF conversion",
    no_args_is_help=True,
    add_completion=False,
)

Transport = Literal["stdio", "http", "sse"]


@app.callback()
def _root(
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Enable debug logging."
    ),
) -> None:
    """Root callback — bootstraps logging for every subcommand.

    pvl-core owns the root logger.  ``configure_logging_from_env`` installs
    the one console handler chain every logger in the process renders
    through — ``scholar_mcp.*``, ``fastmcp.*`` and uvicorn alike —
    picks Rich or JSON from ``SCHOLAR_MCP_LOG_FORMAT`` (unset: Rich on
    a terminal, JSON anywhere else), resolves the level from ``-v`` or
    ``SCHOLAR_MCP_LOG_LEVEL``, and governs the noisy third-party
    loggers (``httpx``, ``httpcore``, the MCP SDK request line) itself.
    Nothing to attach or quiet here: a second root handler would render
    every line twice.  The call is idempotent, so ``make_server()``
    repeating it in the same process is safe.
    """
    configure_logging_from_env(_ENV_PREFIX, verbose=verbose)


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
    import os

    from scholar_mcp.server import make_server

    # Optional remote-debugger listener — placed in ``serve`` (not the
    # typer root callback) so non-server commands like ``--help``,
    # ``--version``, or future ``dump-config``-style subcommands are
    # never blocked by ``SCHOLAR_MCP_DEBUG_WAIT=true``.  No-op
    # unless ``SCHOLAR_MCP_DEBUG_PORT`` is set; ``debugpy`` is only
    # present when the image was built with ``--build-arg DEBUG=true``
    # (a missing import logs a WARNING and continues).  ``_root`` has
    # already installed pvl-core's root handler chain by the time ``serve``
    # runs, so the helper's INFO/WARNING logs render through it rather
    # than Python's lastResort.
    maybe_start_debugpy(_ENV_PREFIX)

    try:
        config = ProjectConfig.from_env()
        # Resolved once, ahead of ``make_server``: the health routes it
        # registers derive their prefix from the mount path, so the value
        # handed to ``http_app(path=...)`` below and the one the server saw
        # must be the same object, not two reads that could drift.
        path = normalise_http_path(
            http_path or os.environ.get(f"{_ENV_PREFIX}_HTTP_PATH")
        )
        server = make_server(transport=transport, config=config, http_path=path)
        # Inside the guard: since pvl-core 9 ``build_event_store`` raises
        # ``ConfigurationError`` for a malformed ``SCHOLAR_MCP_KV_STORE_URL``
        # or legacy ``SCHOLAR_MCP_EVENT_STORE_URL``, which must get the
        # same one-line exit as every other operator value (#647).
        event_store = (
            build_event_store(_ENV_PREFIX, config.server)
            if transport == "http"
            else None
        )
    except ConfigurationError as exc:
        # A malformed or missing operator value is one actionable line on
        # stderr, not Typer's Rich traceback: the message already names the
        # variable and the problem (#616). stderr keeps stdout clean for the
        # stdio transport.
        typer.echo(f"ERROR: configuration error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if transport == "http":
        # pvl-core runs uvicorn.  It pins ``lifespan="on"`` (FastMCP's
        # startup/shutdown hooks run through the ASGI lifespan protocol),
        # ``log_config=None`` (uvicorn must not reinstall its own handlers
        # over the root chain ``_root`` set up) and the SIGTERM drain window
        # from ``SCHOLAR_MCP_SHUTDOWN_GRACE_S`` (default 3s, so
        # containers stop cleanly).  ``None`` for host or port means "not
        # given on the command line"; ``run_http`` then reads ``config.server``.
        run_http(
            server.http_app(path=path, event_store=event_store),
            config=config.server,
            host=host,
            port=port,
        )
    else:
        server.run(transport=transport)


# DOMAIN-COMMANDS-START — add domain @app.command()s (and their helpers) below; kept across copier update
# Domain CLI subcommands live here so the rest of this file stays byte-identical
# to the template and applies cleanly on copier update. Use function-local
# imports for domain modules (as ``serve`` does) to keep the top-level import
# surface template-owned. Module-level names typer resolves from annotations
# (``Path``, ``StrEnum``) and ``TYPE_CHECKING`` guards are imported here.

import asyncio  # noqa: E402
from enum import StrEnum  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:
    import httpx

    from scholar_mcp._standards_sync import Loader

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
    import httpx

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
    from typing import cast

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
