import time
import pytest
from scholar_mcp._cache import ScholarCache

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
    async with aiosqlite.connect(cache._db_path) as db:
        async with db.execute(
            "SELECT s2_paper_id FROM id_aliases WHERE raw_id = ?", ("ARXIV:2401.0001",)
        ) as cur:
            row = await cur.fetchone()
    assert row is not None
    assert row[0] == "s2abc"

async def test_stats(cache):
    await cache.set_paper("p1", {"paperId": "p1"})
    await cache.set_author("a1", {"authorId": "a1"})
    stats = await cache.stats()
    assert stats["papers"] == 1
    assert stats["authors"] == 1
    assert stats["citation_counts"] == 0
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
