"""CLI tests."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from click import unstyle
from typer.testing import CliRunner

from scholar_mcp.cli import app

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastmcp_pvl_core import ServerConfig
    from typer.testing import Result


async def _init_db(path: Path) -> None:
    from scholar_mcp._cache import ScholarCache

    c = ScholarCache(path)
    await c.open()
    await c.close()


def test_cache_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["cache", "--help"])
    assert result.exit_code == 0
    assert "stats" in result.output
    assert "clear" in result.output


def test_cache_stats_no_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With no real DB, stats should exit gracefully with code 0."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["cache", "stats"])
    assert result.exit_code == 0
    assert "No cache database found" in result.output


def test_cache_stats_with_db(tmp_path: Path) -> None:
    """Stats on a real (empty) database."""
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    runner = CliRunner()
    result = runner.invoke(app, ["cache", "stats", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "papers:" in result.output


def test_cache_clear_no_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With no real DB, clear should exit gracefully with code 0."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["cache", "clear"])
    assert result.exit_code == 0
    assert "No cache database found" in result.output


def test_cache_clear_with_db(tmp_path: Path) -> None:
    """Clear all cache entries."""
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    runner = CliRunner()
    result = runner.invoke(app, ["cache", "clear", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "cleared" in result.output.lower()


def test_cache_clear_older_than(tmp_path: Path) -> None:
    """Clear entries older than N days."""
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    runner = CliRunner()
    result = runner.invoke(
        app, ["cache", "clear", "--older-than", "30", "--cache-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "30" in result.output


@pytest.fixture
def _restore_root_level() -> Iterator[None]:
    """Undo the root-logger level the CLI callback sets for the process."""
    root = logging.getLogger()
    level = root.level
    yield
    root.setLevel(level)


@pytest.mark.usefixtures("_restore_root_level")
def test_verbose_sets_debug_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """The -v flag puts the root logger at DEBUG."""
    monkeypatch.delenv("SCHOLAR_MCP_LOG_LEVEL", raising=False)
    CliRunner().invoke(app, ["-v", "serve", "--help"])
    assert logging.getLogger().level == logging.DEBUG


@pytest.mark.usefixtures("_restore_root_level")
def test_verbose_overrides_log_level_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The -v flag wins over an explicit SCHOLAR_MCP_LOG_LEVEL."""
    monkeypatch.setenv("SCHOLAR_MCP_LOG_LEVEL", "WARNING")
    CliRunner().invoke(app, ["-v", "serve", "--help"])
    assert logging.getLogger().level == logging.DEBUG


@pytest.mark.usefixtures("_restore_root_level")
def test_log_level_env_applies_without_verbose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without -v the root level comes from SCHOLAR_MCP_LOG_LEVEL."""
    # ERROR, not WARNING: WARNING is the root logger's own default, so it
    # would pass even if the variable were ignored.
    monkeypatch.setenv("SCHOLAR_MCP_LOG_LEVEL", "ERROR")
    CliRunner().invoke(app, ["serve", "--help"])
    assert logging.getLogger().level == logging.ERROR


def test_serve_help() -> None:
    """Existing serve command still works."""
    runner = CliRunner()
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    # Rich styles option names when it detects CI or FORCE_COLOR, splitting
    # "--transport" across escape sequences; compare the unstyled text.
    assert "--transport" in unstyle(result.output)


def test_serve_stdio_invokes_make_server() -> None:
    """`serve` (default stdio) wires make_server(transport='stdio') and runs it."""
    mock_server = MagicMock()
    with (
        patch(
            "scholar_mcp.server.make_server", return_value=mock_server
        ) as mock_make_server,
        patch("scholar_mcp.server.build_event_store"),
    ):
        result = CliRunner().invoke(app, ["serve"])
    assert result.exit_code == 0
    assert mock_make_server.call_count == 1
    assert mock_make_server.call_args.kwargs["transport"] == "stdio"
    mock_server.run.assert_called_once_with(transport="stdio")


def test_serve_calls_maybe_start_debugpy() -> None:
    """`serve` invokes ``maybe_start_debugpy`` with the scholar-mcp env prefix.

    The call is a no-op unless ``SCHOLAR_MCP_DEBUG_PORT`` is set, but it must
    happen on every ``serve`` invocation so operators can attach a debugger by
    setting the env var without rebuilding or rewriting the entrypoint.
    """
    mock_server = MagicMock()
    with (
        patch("scholar_mcp.server.make_server", return_value=mock_server),
        patch("scholar_mcp.server.build_event_store"),
        patch("scholar_mcp.cli.maybe_start_debugpy") as mock_debugpy,
    ):
        result = CliRunner().invoke(app, ["serve"])
    assert result.exit_code == 0
    mock_debugpy.assert_called_once_with("SCHOLAR_MCP")


def _invoke_http_serve(
    extra_args: list[str] | None = None,
) -> tuple[Result, dict[str, object]]:
    """Invoke ``serve --transport http`` with every blocking side effect patched.

    Returns the result and the bind address the fake ``run_http`` resolved the
    way the real one does: a CLI flag beats ``config.server``, and ``None``
    means the flag was not given.
    """
    captured: dict[str, object] = {}

    def fake_run_http(
        _asgi_app: object,
        *,
        config: ServerConfig,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        captured["host"] = config.host if host is None else host
        captured["port"] = config.port if port is None else port

    with (
        patch("scholar_mcp.cli.run_http", side_effect=fake_run_http),
        patch("scholar_mcp.server.make_server", return_value=MagicMock()),
        patch("scholar_mcp.cli.build_event_store"),
    ):
        result = CliRunner().invoke(
            app, ["serve", "--transport", "http", *(extra_args or [])]
        )
    return result, captured


def test_serve_http_binds_env_host_over_loopback_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The http transport resolves host/port from flags, env, then defaults.

    With no ``--host`` the server binds ``SCHOLAR_MCP_HOST``, falling back to
    core's loopback default; an operator widens the bind through the env file.
    """
    monkeypatch.setenv("SCHOLAR_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("SCHOLAR_MCP_PORT", "9137")
    result, captured = _invoke_http_serve()
    assert result.exit_code == 0, result.output
    assert captured == {"host": "0.0.0.0", "port": 9137}


def test_serve_http_explicit_host_flag_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit ``--host``/``--port`` overrides the env-derived config."""
    monkeypatch.setenv("SCHOLAR_MCP_HOST", "0.0.0.0")
    result, captured = _invoke_http_serve(["--host", "127.0.0.1", "--port", "8123"])
    assert result.exit_code == 0, result.output
    assert captured == {"host": "127.0.0.1", "port": 8123}


def test_help_exits_zero() -> None:
    """`scholar-mcp --help` lists the serve command."""
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output


def test_no_args_shows_help() -> None:
    """Bare invocation shows help text via ``no_args_is_help=True``.

    Typer/Click exits with code 2 (missing command) but still prints the
    help output.
    """
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 2
    assert "serve" in result.output
