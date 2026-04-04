"""Command-line interface for mcp-server.

Provides a ``serve`` subcommand.  The entry point is :func:`main`,
registered as ``mcp-server`` in ``pyproject.toml``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from fastmcp_server_template.config import _ENV_PREFIX, get_log_level

logger = logging.getLogger(__name__)

_PROG = "mcp-server"
_DEFAULT_HTTP_PATH = "/mcp"


def _normalise_http_path(path: str | None) -> str:
    """Normalise an HTTP endpoint path for FastMCP streamable HTTP transport.

    Ensures a leading slash and removes a trailing slash (except for root ``/``).
    Empty values fall back to ``/mcp``.
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


def _cmd_serve(args: argparse.Namespace) -> None:
    """Run the MCP server."""
    try:
        from fastmcp_server_template.mcp_server import build_event_store, create_server
    except ImportError:
        logger.error(
            "FastMCP is not installed. Install with: "
            "pip install fastmcp-server-template[mcp]"
        )
        sys.exit(1)

    transport = args.transport
    server = create_server(transport=transport)
    env_http_path = os.environ.get(f"{_ENV_PREFIX}_HTTP_PATH")
    http_path = _normalise_http_path(args.path or env_http_path)
    if transport == "stdio" and (
        args.host != "0.0.0.0" or args.port != 8000 or args.path is not None
    ):
        logger.warning("--host, --port and --path are only used with --transport http")
    if transport == "http":
        try:
            import uvicorn
        except ImportError:
            logger.error(
                "HTTP transport requires uvicorn. Install with: "
                "pip install 'fastmcp-server-template[mcp]'"
            )
            sys.exit(1)

        event_store = build_event_store()
        app = server.http_app(path=http_path, event_store=event_store)
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            lifespan="on",
            timeout_graceful_shutdown=0,
        )
    else:
        server.run(transport=transport)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        Configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description="FastMCP server — replace this description",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable debug logging",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # serve
    serve_parser = sub.add_parser("serve", help="run the MCP server")
    serve_parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default="stdio",
        help="MCP transport: stdio (default), sse, or http (streamable-http)",
    )
    serve_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="host to bind to for http transport (default: 0.0.0.0)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="port for http transport (default: 8000)",
    )
    serve_parser.add_argument(
        "--path",
        default=None,
        help=(
            f"mount path for http transport (default: ${_ENV_PREFIX}_HTTP_PATH or /mcp)"
        ),
    )

    return parser


_COMMANDS = {
    "serve": _cmd_serve,
}


def main() -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    # -v flag overrides LOG_LEVEL env var; env var overrides default INFO.
    level = logging.DEBUG if args.verbose else get_log_level()
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # httpx is noisy at DEBUG — keep it at WARNING unless explicitly targeted.
    if level == logging.DEBUG:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    handler = _COMMANDS[args.command]
    try:
        handler(args)
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
