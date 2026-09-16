import time

import pytest

from scholar_mcp._cache import _REPAIRS, ScholarCache


@pytest.fixture
async def cache(tmp_path):
    c = ScholarCache(tmp_path / "test.db")
    await c.open()
    yield c
    await c.close()


async def test_paper_roundtrip(cache):
    data = {"paperId": "abc123", "title": "Test Paper", "year": 2024}
    await cache.set_paper("abc123", data)
    result = await cache.get_paper("abc123")
    assert result == data


async def test_paper_miss(cache):
    assert await cache.get_paper("nonexistent") is None


async def test_paper_ttl_expired(cache):
    data = {"paperId": "xyz", "title": "Old"}
    await cache.set_paper("xyz", data)
    import aiosqlite

    async with aiosqlite.connect(cache._db_path) as db:
        await db.execute(
            "UPDATE papers SET cached_at = ? WHERE paper_id = ?",
            (time.time() - 31 * 86400, "xyz"),
        )
        await db.commit()
    assert await cache.get_paper("xyz") is None


async def test_citations_roundtrip(cache):
    ids = ["p1", "p2", "p3"]
    await cache.set_citations("paper1", ids)
    assert await cache.get_citations("paper1") == ids


async def test_references_roundtrip(cache):
    ids = ["r1", "r2"]
    await cache.set_references("paper1", ids)
    assert await cache.get_references("paper1") == ids


async def test_author_roundtrip(cache):
    data = {"authorId": "auth1", "name": "Ada Lovelace"}
    await cache.set_author("auth1", data)
    assert await cache.get_author("auth1") == data


async def test_openalex_roundtrip(cache):
    data = {"doi": "10.1/test", "affiliations": []}
    await cache.set_openalex("10.1/test", data)
    assert await cache.get_openalex("10.1/test") == data


async def test_alias_roundtrip(cache):
    await cache.set_alias("DOI:10.1/test", "s2id123")
    assert await cache.get_alias("DOI:10.1/test") == "s2id123"


async def test_alias_no_ttl(cache):
    """Aliases never expire."""
    await cache.set_alias("ARXIV:2401.0001", "s2abc")
    import aiosqlite

    async with (
        aiosqlite.connect(cache._db_path) as db,
        db.execute(
            "SELECT s2_paper_id FROM id_aliases WHERE raw_id = ?", ("ARXIV:2401.0001",)
        ) as cur,
    ):
        row = await cur.fetchone()
    assert row is not None
    assert row[0] == "s2abc"


async def test_stats(cache):
    await cache.set_paper("p1", {"paperId": "p1"})
    await cache.set_author("a1", {"authorId": "a1"})
    stats = await cache.stats()
    assert stats["papers"] == 1
    assert stats["authors"] == 1
    assert stats["citations"] == 0
    assert stats["refs"] == 0
    assert stats["openalex"] == 0
    assert "db_size_bytes" in stats
    assert isinstance(stats["db_size_bytes"], int)


async def test_clear_all(cache):
    await cache.set_paper("p1", {"paperId": "p1"})
    await cache.set_alias("DOI:10.1/keep", "s2preserved")
    await cache.clear()
    assert await cache.get_paper("p1") is None
    # id_aliases must survive a full clear
    assert await cache.get_alias("DOI:10.1/keep") == "s2preserved"


async def test_clear_older_than(cache):
    await cache.set_paper("old", {"paperId": "old"})
    await cache.set_paper("new", {"paperId": "new"})
    import aiosqlite

    async with aiosqlite.connect(cache._db_path) as db:
        await db.execute(
            "UPDATE papers SET cached_at = ? WHERE paper_id = ?",
            (time.time() - 10 * 86400, "old"),
        )
        await db.commit()
    await cache.clear(older_than_days=7)
    assert await cache.get_paper("old") is None
    assert await cache.get_paper("new") is not None


class TestPatentCache:
    async def test_patent_roundtrip(self, cache) -> None:
        data = {"title": "Test Patent", "publication_number": "EP.1234567.A1"}
        await cache.set_patent("EP.1234567.A1", data)
        result = await cache.get_patent("EP.1234567.A1")
        assert result == data

    async def test_patent_not_found(self, cache) -> None:
        assert await cache.get_patent("EP.9999999.A1") is None

    async def test_patent_search_roundtrip(self, cache) -> None:
        data = {"total_count": 5, "references": [{"country": "EP"}]}
        await cache.set_patent_search("ta=solar", data)
        result = await cache.get_patent_search("ta=solar")
        assert result == data

    async def test_patent_claims_roundtrip(self, cache) -> None:
        await cache.set_patent_claims("EP.1234567.A1", "Claim 1: A method...")
        result = await cache.get_patent_claims("EP.1234567.A1")
        assert result == "Claim 1: A method..."

    async def test_patent_description_roundtrip(self, cache) -> None:
        await cache.set_patent_description("EP.1234567.A1", "Description text")
        result = await cache.get_patent_description("EP.1234567.A1")
        assert result == "Description text"

    async def test_patent_family_roundtrip(self, cache) -> None:
        data = [{"country": "US", "number": "11234567"}]
        await cache.set_patent_family("EP.1234567.A1", data)
        result = await cache.get_patent_family("EP.1234567.A1")
        assert result == data

    async def test_patent_legal_roundtrip(self, cache) -> None:
        data = [{"event": "grant", "date": "2020-01-15"}]
        await cache.set_patent_legal("EP.1234567.A1", data)
        result = await cache.get_patent_legal("EP.1234567.A1")
        assert result == data

    async def test_patent_stats(self, cache) -> None:
        await cache.set_patent("EP.1234567.A1", {"title": "Test"})
        stats = await cache.stats()
        assert stats["patents"] >= 1


class TestCrossRefCache:
    async def test_crossref_roundtrip(self, cache) -> None:
        data = {"DOI": "10.1234/test", "title": ["Test Paper"]}
        await cache.set_crossref("10.1234/test", data)
        result = await cache.get_crossref("10.1234/test")
        assert result == data

    async def test_crossref_not_found(self, cache) -> None:
        assert await cache.get_crossref("10.0/missing") is None

    async def test_crossref_ttl_expired(self, cache) -> None:
        import aiosqlite

        data = {"DOI": "10.1234/old", "title": ["Old"]}
        await cache.set_crossref("10.1234/old", data)
        async with aiosqlite.connect(cache._db_path) as db:
            await db.execute(
                "UPDATE crossref SET cached_at = ? WHERE doi = ?",
                (time.time() - 31 * 86400, "10.1234/old"),
            )
            await db.commit()
        assert await cache.get_crossref("10.1234/old") is None


# ---------------------------------------------------------------------
# One-shot row repairs (#440)
# ---------------------------------------------------------------------

_TEST_REPAIR = "DELETE FROM patents WHERE json_extract(data, '$.abstract') = ''"


async def test_repair_deletes_only_matching_rows(tmp_path, monkeypatch):
    """A registered repair runs at open() and spares rows it does not match."""
    db_path = tmp_path / "repair.db"
    seed = ScholarCache(db_path)
    await seed.open()
    await seed.set_patent("EP1.A1", {"title": "broken", "abstract": ""})
    await seed.set_patent("EP2.A1", {"title": "fine", "abstract": "real text"})
    await seed.close()

    monkeypatch.setitem(_REPAIRS, "test_empty_abstract", _TEST_REPAIR)
    cache = ScholarCache(db_path)
    await cache.open()
    try:
        assert await cache.get_patent("EP1.A1") is None
        assert await cache.get_patent("EP2.A1") is not None
    finally:
        await cache.close()


async def test_repair_runs_once_and_is_recorded(tmp_path, monkeypatch):
    """A repair is one-shot: rows cached after it ran are left alone."""
    import aiosqlite

    db_path = tmp_path / "once.db"
    monkeypatch.setitem(_REPAIRS, "test_empty_abstract", _TEST_REPAIR)

    first = ScholarCache(db_path)
    await first.open()
    await first.close()

    second = ScholarCache(db_path)
    await second.open()
    await second.set_patent("EP3.A1", {"title": "new", "abstract": ""})
    await second.close()

    third = ScholarCache(db_path)
    await third.open()
    try:
        # The repair already ran, so it must not act as a standing filter.
        assert await third.get_patent("EP3.A1") is not None
    finally:
        await third.close()

    async with (
        aiosqlite.connect(db_path) as db,
        db.execute(
            "SELECT count(*) FROM repairs WHERE name = ?", ("test_empty_abstract",)
        ) as cur,
    ):
        row = await cur.fetchone()
    assert row is not None
    assert row[0] == 1


async def test_registered_repairs_drop_what_their_bugs_cached(tmp_path):
    """The #399 and #405 predicates fire on a database written before the fix.

    A fresh database records both repairs on its first open with nothing to
    delete, so the upgrade path is what needs asserting: clear the ledger to
    stand in for a cache written by an older build, then reopen.
    """
    import aiosqlite

    db_path = tmp_path / "upgrade.db"
    old = ScholarCache(db_path)
    await old.open()
    await old.set_patent("EP1.A1", {"title": "broken", "abstract": ""})
    await old.set_patent("EP2.A1", {"title": "fine", "abstract": "real text"})
    await old.set_patent_legal(
        "EP1.A1", [{"date": "2021-07-30", "code": "PG25", "description": "LAPSED"}]
    )
    await old.close()

    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM repairs")
        await db.commit()

    upgraded = ScholarCache(db_path)
    await upgraded.open()
    try:
        assert await upgraded.get_patent("EP1.A1") is None
        assert await upgraded.get_patent("EP2.A1") is not None
        assert await upgraded.get_patent_legal("EP1.A1") is None
    finally:
        await upgraded.close()


async def test_every_registered_repair_is_valid_sql(cache):
    """A malformed statement would otherwise only surface on a user's upgrade."""
    assert set(_REPAIRS) == {
        "399_empty_patent_abstract",
        "405_legal_events_without_country",
    }
    for statement in _REPAIRS.values():
        await cache._db.execute(f"EXPLAIN {statement}")


async def test_open_provisions_the_repairs_ledger(cache):
    """With no repairs registered, open() still provisions the ledger."""
    async with cache._db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='repairs'"
    ) as cur:
        assert await cur.fetchone() is not None
