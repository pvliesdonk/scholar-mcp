"""CLI tests."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from scholar_mcp.cli import app


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


def test_cache_stats_no_db() -> None:
    """With no real DB, stats should exit gracefully with code 0."""
    runner = CliRunner()
    with runner.isolated_filesystem():
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


def test_cache_clear_no_db() -> None:
    """With no real DB, clear should exit gracefully with code 0."""
    runner = CliRunner()
    with runner.isolated_filesystem():
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


def test_verbose_sets_fastmcp_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """The -v flag sets FASTMCP_LOG_LEVEL to DEBUG."""
    monkeypatch.delenv("FASTMCP_LOG_LEVEL", raising=False)
    runner = CliRunner()
    runner.invoke(app, ["-v", "serve", "--help"])
    assert os.environ.get("FASTMCP_LOG_LEVEL") == "DEBUG"


def test_verbose_overrides_fastmcp_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """The -v flag overrides an explicit FASTMCP_LOG_LEVEL."""
    monkeypatch.setenv("FASTMCP_LOG_LEVEL", "WARNING")
    runner = CliRunner()
    runner.invoke(app, ["-v", "serve", "--help"])
    assert os.environ.get("FASTMCP_LOG_LEVEL") == "DEBUG"


def test_serve_help() -> None:
    """Existing serve command still works."""
    runner = CliRunner()
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--transport" in result.output


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
    mock_make_server.assert_called_once_with(transport="stdio")
    mock_server.run.assert_called_once_with(transport="stdio")


def test_serve_import_error_exits_1() -> None:
    """If fastmcp isn't installed (import fails), serve exits 1."""
    with patch.dict("sys.modules", {"scholar_mcp.server": None}):
        result = CliRunner().invoke(app, ["serve"])
    assert result.exit_code == 1
