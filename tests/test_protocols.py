"""Tests for protocol conformance."""

from __future__ import annotations

from scholar_mcp._cache import ScholarCache
from scholar_mcp._protocols import CacheProtocol


def test_scholar_cache_satisfies_cache_protocol() -> None:
    """ScholarCache must structurally satisfy CacheProtocol."""
    cache_instance: CacheProtocol = ScholarCache.__new__(ScholarCache)
    assert isinstance(cache_instance, object)
