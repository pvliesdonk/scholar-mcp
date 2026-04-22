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
from typing import TYPE_CHECKING, cast

import httpx
import typer
from fastmcp_pvl_core import configure_logging_from_env, normalise_http_path

from scholar_mcp.config import _ENV_PREFIX

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
    transport: str = typer.Option("stdio", help="MCP transport (stdio / http / sse)."),
    host: str = typer.Option("0.0.0.0", help="Bind host (http only)."),
    port: int = typer.Option(8000, help="Bind port (http only)."),
    http_path: str | None = typer.Option(
        None,
        "--http-path",
        "--path",
        help=(f"Mount path (http only, default: ${_ENV_PREFIX}_HTTP_PATH or /mcp)."),
    ),
) -> None:
    """Run the MCP server."""
    try:
        from scholar_mcp.server import build_event_store, make_server
    except ImportError as exc:
        logger.error(
            "FastMCP is not installed. Install with: "
            "pip install pvliesdonk-scholar-mcp[mcp]"
        )
        raise typer.Exit(code=1) from exc

    server = make_server(transport=transport)
    env_http_path = os.environ.get(f"{_ENV_PREFIX}_HTTP_PATH")
    path = normalise_http_path(http_path or env_http_path)

    if transport != "http" and (
        host != "0.0.0.0" or port != 8000 or http_path is not None
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

        event_store = build_event_store()
        app_ = server.http_app(path=path, event_store=event_store)
        uvicorn.run(
            app_,
            host=host,
            port=port,
            lifespan="on",
            timeout_graceful_shutdown=0,
        )
    else:
        from typing import Literal
        from typing import cast as type_cast

        transport_literal = type_cast(
            "Literal['stdio', 'http', 'sse', 'streamable-http']", transport
        )
        server.run(transport=transport_literal)


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
    from scholar_mcp.config import load_config

    async def _run() -> int:
        from scholar_mcp._standards_sync import SyncReport

        config = load_config()
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
    from scholar_mcp.config import load_config

    async def _run() -> None:
        config = load_config()
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
    from scholar_mcp.config import load_config

    async def _run() -> None:
        config = load_config()
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


def main() -> None:
    """CLI entry point — used by ``[project.scripts]`` in pyproject.toml."""
    app()


if __name__ == "__main__":
    main()
