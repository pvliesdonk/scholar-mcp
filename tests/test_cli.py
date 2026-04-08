"""CLI tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

from click.testing import CliRunner

from scholar_mcp.cli import cli


async def _init_db(path: Path) -> None:
    from scholar_mcp._cache import ScholarCache

    c = ScholarCache(path)
    await c.open()
    await c.close()


def test_cache_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "--help"])
    assert result.exit_code == 0
    assert "stats" in result.output
    assert "clear" in result.output


def test_cache_stats_no_db() -> None:
    """With no real DB, stats should exit gracefully with code 0."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["cache", "stats"])
    assert result.exit_code == 0
    assert "No cache database found" in result.output


def test_cache_stats_with_db(tmp_path: Path) -> None:
    """Stats on a real (empty) database."""
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "stats", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "papers:" in result.output


def test_cache_clear_no_db() -> None:
    """With no real DB, clear should exit gracefully with code 0."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["cache", "clear"])
    assert result.exit_code == 0
    assert "No cache database found" in result.output


def test_cache_clear_with_db(tmp_path: Path) -> None:
    """Clear all cache entries."""
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "clear", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "cleared" in result.output.lower()


def test_cache_clear_older_than(tmp_path: Path) -> None:
    """Clear entries older than N days."""
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    runner = CliRunner()
    result = runner.invoke(
        cli, ["cache", "clear", "--older-than", "30", "--cache-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "30" in result.output


def test_verbose_sets_fastmcp_log_level(monkeypatch) -> None:
    """The -v flag sets FASTMCP_LOG_LEVEL to DEBUG."""
    monkeypatch.delenv("FASTMCP_LOG_LEVEL", raising=False)
    runner = CliRunner()
    runner.invoke(cli, ["-v", "serve", "--help"])
    import os

    assert os.environ.get("FASTMCP_LOG_LEVEL") == "DEBUG"


def test_verbose_overrides_fastmcp_log_level(monkeypatch) -> None:
    """The -v flag overrides an explicit FASTMCP_LOG_LEVEL."""
    monkeypatch.setenv("FASTMCP_LOG_LEVEL", "WARNING")
    runner = CliRunner()
    runner.invoke(cli, ["-v", "serve", "--help"])
    import os

    assert os.environ.get("FASTMCP_LOG_LEVEL") == "DEBUG"


def test_serve_help() -> None:
    """Existing serve command still works."""
    runner = CliRunner()
    result = runner.invoke(cli, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--transport" in result.output
