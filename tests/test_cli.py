"""CLI tests."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from scholar_mcp.cli import cli


def test_cache_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "--help"])
    assert result.exit_code == 0
    assert "stats" in result.output
    assert "clear" in result.output


def test_cache_stats_no_db() -> None:
    """With no real DB, stats should exit gracefully."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["cache", "stats"])
    assert result.exit_code in (0, 1)


def test_cache_stats_with_db(tmp_path) -> None:
    """Stats on a real (empty) database."""
    import asyncio
    from scholar_mcp._cache import ScholarCache
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "stats", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "papers:" in result.output


async def _init_db(path):
    from scholar_mcp._cache import ScholarCache
    c = ScholarCache(path)
    await c.open()
    await c.close()


def test_cache_clear_no_db() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["cache", "clear"])
    assert result.exit_code in (0, 1)


def test_cache_clear_with_db(tmp_path) -> None:
    import asyncio
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "clear", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "cleared" in result.output.lower()


def test_cache_clear_older_than(tmp_path) -> None:
    import asyncio
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "clear", "--older-than", "30", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "30" in result.output


def test_serve_help() -> None:
    """Existing serve command still works."""
    runner = CliRunner()
    result = runner.invoke(cli, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--transport" in result.output
