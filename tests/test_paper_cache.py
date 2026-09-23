"""Tests for shared paper read-through caching."""

from unittest.mock import AsyncMock

from scholar_mcp._paper_cache import resolve_paper
from scholar_mcp.domain import Service


async def test_resolve_paper_reads_an_alias_from_cache(service: Service) -> None:
    """An alias resolves a cached paper without calling the upstream fetcher."""
    paper = {"paperId": "canonical", "title": "Cached"}
    await service.cache.set_paper("canonical", paper)
    await service.cache.set_alias("DOI:10.1/example", "canonical")
    fetch_paper = AsyncMock()

    result = await resolve_paper(service.cache, fetch_paper, "DOI:10.1/example")

    assert result == paper
    fetch_paper.assert_not_awaited()


async def test_resolve_paper_caches_record_and_alias(service: Service) -> None:
    """A cache miss stores the canonical row and the caller's alias."""
    paper = {"paperId": "canonical", "title": "Fetched"}
    fetch_paper = AsyncMock(return_value=paper)

    result = await resolve_paper(service.cache, fetch_paper, "ARXIV:2401.00001")

    assert result == paper
    fetch_paper.assert_awaited_once_with("ARXIV:2401.00001")
    assert await service.cache.get_paper("canonical") == paper
    assert await service.cache.get_alias("ARXIV:2401.00001") == "canonical"


async def test_resolve_paper_does_not_alias_canonical_id(
    service: Service,
) -> None:
    """A canonical lookup stores only the paper row."""
    identifier = "canonical"
    paper = {"paperId": identifier, "title": "Fetched"}

    await resolve_paper(service.cache, AsyncMock(return_value=paper), identifier)

    assert await service.cache.get_paper(identifier) == paper
    assert await service.cache.get_alias(identifier) is None


async def test_resolve_paper_does_not_cache_record_without_id(
    service: Service,
) -> None:
    """A record without a canonical paper ID remains usable but uncached."""
    paper = {"title": "No ID"}

    result = await resolve_paper(
        service.cache, AsyncMock(return_value=paper), "unknown"
    )

    assert result == paper
    assert await service.cache.get_paper("unknown") is None
