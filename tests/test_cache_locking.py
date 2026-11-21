"""The cache shares its file with sync-standards running beside it (#692).

In production, a lookup made while ``sync-standards`` ran failed with
"database is locked". The failed write then left its transaction open, so
the server held the database's write lock until it restarted and every
later sync failed too. These tests hold a write in a second connection, the
way the sync process does.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from typing import TYPE_CHECKING

import pytest

from scholar_mcp._cache import ScholarCache
from scholar_mcp._record_types import StandardRecord

if TYPE_CHECKING:
    from pathlib import Path

_RECORD = StandardRecord(identifier="RFC 791", body="IETF", title="Internet Protocol")


async def _cache(path: Path, timeout: float) -> ScholarCache:
    cache = ScholarCache(path, busy_timeout_s=timeout)
    await cache.open()
    return cache


def _hold_write_lock(path: Path) -> sqlite3.Connection:
    """Open a second connection and take the write lock, as a sync does."""
    other = sqlite3.connect(
        path, timeout=0, isolation_level=None, check_same_thread=False
    )
    other.execute("BEGIN IMMEDIATE")
    other.execute("DELETE FROM standards WHERE identifier = 'nothing'")
    return other


async def test_the_cache_opens_in_wal_mode(tmp_path: Path) -> None:
    """A reader then never waits for the sync's writer."""
    cache = await _cache(tmp_path / "cache.db", timeout=1)
    try:
        check = sqlite3.connect(tmp_path / "cache.db")
        mode = check.execute("PRAGMA journal_mode").fetchone()[0]
        check.close()
        assert mode == "wal"
    finally:
        await cache.close()


async def test_a_reader_is_not_blocked_by_another_process_writing(
    tmp_path: Path,
) -> None:
    cache = await _cache(tmp_path / "cache.db", timeout=1)
    try:
        await cache.set_standard("RFC 791", _RECORD)
        other = _hold_write_lock(tmp_path / "cache.db")
        try:
            assert await cache.get_standard("RFC 791") is not None
        finally:
            other.rollback()
            other.close()
    finally:
        await cache.close()


async def test_a_write_waits_for_another_process_write(tmp_path: Path) -> None:
    """The write succeeds once the other process commits, within the timeout."""
    cache = await _cache(tmp_path / "cache.db", timeout=5)
    other = _hold_write_lock(tmp_path / "cache.db")
    release = threading.Timer(0.3, lambda: (other.commit(), other.close()))
    release.start()
    try:
        started = time.monotonic()
        await cache.set_standard("RFC 791", _RECORD)
        assert time.monotonic() - started >= 0.2
        assert await cache.get_standard("RFC 791") is not None
    finally:
        release.join()
        await cache.close()


async def test_a_failed_write_leaves_no_lock_behind(tmp_path: Path) -> None:
    """After a write times out, another process can write at once."""
    cache = await _cache(tmp_path / "cache.db", timeout=0.1)
    try:
        other = _hold_write_lock(tmp_path / "cache.db")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            await cache.set_standard("RFC 791", _RECORD)
        other.rollback()
        other.close()

        assert cache._db is not None
        assert not cache._db.in_transaction
        third = sqlite3.connect(tmp_path / "cache.db", timeout=0)
        third.execute("BEGIN IMMEDIATE")
        third.rollback()
        third.close()
    finally:
        await cache.close()


async def test_concurrent_writes_on_one_connection_all_land(tmp_path: Path) -> None:
    """Write units do not interleave, so one cannot commit or discard another."""
    cache = await _cache(tmp_path / "cache.db", timeout=1)
    try:
        await asyncio.gather(
            *(
                cache.set_standard(
                    f"RFC {n}", StandardRecord(identifier=f"RFC {n}", body="IETF")
                )
                for n in range(50)
            )
        )
        found = [await cache.get_standard(f"RFC {n}") for n in range(50)]
        assert all(r is not None for r in found)
    finally:
        await cache.close()
