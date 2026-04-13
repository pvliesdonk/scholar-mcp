"""Tests for the scholar-mcp sync-standards CLI subcommand."""

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


def test_sync_standards_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["sync-standards", "--help"])
    assert result.exit_code == 0
    assert "--body" in result.output
    assert "--force" in result.output


def test_sync_standards_no_loaders_registered(tmp_path: Path) -> None:
    """Zero loaders registered → exits 0 with a clear message."""
    db_path = tmp_path / "cache.db"
    asyncio.run(_init_db(db_path))

    runner = CliRunner()
    result = runner.invoke(cli, ["sync-standards", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "no loaders registered" in result.output


def test_sync_standards_unknown_body(tmp_path: Path) -> None:
    """Invalid --body value exits 2 (click's usage error)."""
    runner = CliRunner()
    result = runner.invoke(
        cli, ["sync-standards", "--body", "XYZ", "--cache-dir", str(tmp_path)]
    )
    assert result.exit_code == 2
    assert "XYZ" in result.output or "Invalid value" in result.output
