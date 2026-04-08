"""Command-line interface for scholar-mcp.

Provides ``serve`` and ``cache`` subcommands. The entry point is :func:`main`,
registered as ``scholar-mcp`` in ``pyproject.toml``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import click

from scholar_mcp.config import _ENV_PREFIX

logger = logging.getLogger(__name__)

_PROG = "scholar-mcp"
_DEFAULT_HTTP_PATH = "/mcp"


def _normalise_http_path(path: str | None) -> str:
    """Normalise an HTTP endpoint path for FastMCP streamable HTTP transport.

    Ensures a leading slash and removes a trailing slash (except for root ``/``).
    Empty values fall back to ``/mcp``.

    Args:
        path: Raw path string or None.

    Returns:
        Normalised path string.
    """
    if path is None:
        return _DEFAULT_HTTP_PATH
    normalised = path.strip()
    if not normalised:
        return _DEFAULT_HTTP_PATH
    if not normalised.startswith("/"):
        normalised = f"/{normalised}"
    if len(normalised) > 1:
        normalised = normalised.rstrip("/")
    return normalised


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Scholar MCP — academic literature server."""
    # The -v flag overrides FASTMCP_LOG_LEVEL for convenience.
    if verbose:
        os.environ["FASTMCP_LOG_LEVEL"] = "DEBUG"
    from fastmcp.utilities.logging import configure_logging

    level_name = os.environ.get("FASTMCP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    configure_logging(level=level)
    # Attach FastMCP's handler to the root logger so application
    # loggers (scholar_mcp.*) share the same output format.
    # configure_logging() sets propagate=False on the fastmcp logger,
    # so fastmcp.* records won't double-fire through root.
    fastmcp_logger = logging.getLogger("fastmcp")
    root = logging.getLogger()
    root.setLevel(level)
    if fastmcp_logger.handlers and not fastmcp_logger.propagate:
        handler = fastmcp_logger.handlers[0]
        if handler not in root.handlers:
            root.addHandler(handler)
    if level == logging.DEBUG:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command("serve")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse", "http"]),
    default="stdio",
    show_default=True,
    help="MCP transport.",
)
@click.option(
    "--host", default="0.0.0.0", show_default=True, help="Bind host (http only)."
)
@click.option(
    "--port", type=int, default=8000, show_default=True, help="Bind port (http only)."
)
@click.option(
    "--path",
    default=None,
    help=f"Mount path (http only, default: ${_ENV_PREFIX}_HTTP_PATH or /mcp).",
)
def serve(transport: str, host: str, port: int, path: str | None) -> None:
    """Run the MCP server."""
    try:
        from scholar_mcp.mcp_server import build_event_store, create_server
    except ImportError as exc:
        logger.error(
            "FastMCP is not installed. Install with: pip install pvliesdonk-scholar-mcp[mcp]"
        )
        raise SystemExit(1) from exc

    server = create_server(transport=transport)
    env_http_path = os.environ.get(f"{_ENV_PREFIX}_HTTP_PATH")
    http_path = _normalise_http_path(path or env_http_path)

    if transport != "http" and (host != "0.0.0.0" or port != 8000 or path is not None):
        logger.warning("--host, --port and --path are only used with --transport http")

    if transport == "http":
        try:
            import uvicorn
        except ImportError as exc:
            logger.error(
                "HTTP transport requires uvicorn. Install with: pip install 'pvliesdonk-scholar-mcp[mcp]'"
            )
            raise SystemExit(1) from exc

        event_store = build_event_store()
        app = server.http_app(path=http_path, event_store=event_store)
        uvicorn.run(
            app, host=host, port=port, lifespan="on", timeout_graceful_shutdown=0
        )
    else:
        from typing import Literal, cast

        transport_literal = cast(
            "Literal['stdio', 'http', 'sse', 'streamable-http']", transport
        )
        server.run(transport=transport_literal)


@cli.group("cache")
def cache_group() -> None:
    """Manage the Scholar MCP local cache."""


@cache_group.command("stats")
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Override cache directory.",
)
def cache_stats(cache_dir: Path | None) -> None:
    """Show cache statistics (row counts, file size)."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp.config import load_config

    async def _run() -> None:
        config = load_config()
        db_path = (cache_dir or config.cache_dir) / "cache.db"
        if not db_path.exists():
            click.echo("No cache database found.")
            return
        c = ScholarCache(db_path)
        await c.open()
        stats = await c.stats()
        await c.close()
        for key, val in stats.items():
            click.echo(f"{key}: {val}")

    asyncio.run(_run())


@cache_group.command("clear")
@click.option(
    "--older-than",
    "older_than",
    type=int,
    default=None,
    help="Only remove entries older than this many days.",
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Override cache directory.",
)
def cache_clear(older_than: int | None, cache_dir: Path | None) -> None:
    """Clear cache entries.

    Without --older-than, wipes all cached data (preserves id_aliases).
    With --older-than N, removes only entries older than N days.
    """
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp.config import load_config

    async def _run() -> None:
        config = load_config()
        db_path = (cache_dir or config.cache_dir) / "cache.db"
        if not db_path.exists():
            click.echo("No cache database found.")
            return
        c = ScholarCache(db_path)
        await c.open()
        await c.clear(older_than_days=older_than)
        await c.close()
        if older_than is not None:
            click.echo(f"Cache cleared (older than {older_than} days).")
        else:
            click.echo("Cache cleared.")

    asyncio.run(_run())


def main() -> None:
    """CLI entry point."""
    cli()


if __name__ == "__main__":
    main()
