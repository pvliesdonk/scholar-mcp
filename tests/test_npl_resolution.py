"""The NPL resolution pipeline's identifier batch (#710)."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import httpx
import pytest

from scholar_mcp._npl_resolution import resolve_npl_refs
from scholar_mcp._rate_limiter import RateLimitedError

_REFS = [
    {"raw": "LECUN: Deep learning. https://doi.org/10.1038/nature14539"},
    {"raw": "A book, 1990"},
]


def _s2(**batch: object) -> AsyncMock:
    s2 = AsyncMock()
    s2.batch_resolve = AsyncMock(**batch)
    s2.match_title = AsyncMock(return_value=None)
    return s2


async def test_failed_batch_leaves_references_unresolved(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing S2 batch is best-effort: entries keep their DOI, no paper."""
    s2 = _s2(side_effect=httpx.ConnectError("down"))
    with caplog.at_level(logging.WARNING):
        entries = await resolve_npl_refs(
            _REFS, s2=s2, resolve_book=None, patent_id="EP.1.A1"
        )
    assert entries[0] == {
        "raw": _REFS[0]["raw"],
        "doi": "10.1038/nature14539",
        "confidence": None,
    }
    assert "paper" not in entries[1]
    assert "npl_resolution_failed patent=EP.1.A1" in caplog.messages


async def test_throttled_batch_propagates() -> None:
    """A throttle reaches the tool, which defers the whole call."""
    s2 = _s2(side_effect=RateLimitedError())
    with pytest.raises(RateLimitedError):
        await resolve_npl_refs(_REFS, s2=s2, resolve_book=None, patent_id="EP.1.A1")


async def test_without_s2_no_identifier_is_kept() -> None:
    entries = await resolve_npl_refs(
        _REFS, s2=None, resolve_book=None, patent_id="EP.1.A1"
    )
    assert entries[0] == {"raw": _REFS[0]["raw"], "confidence": None}
