"""Patterns that read outside input stay linear on hostile input (#680).

Each input below took the old pattern minutes (quadratic or cubic
backtracking), well past the suite's 60 s phase limit, so a pattern that
regresses fails here rather than slowing a request. The assertions are on
results, not timings.
"""

from __future__ import annotations

import pytest

from scholar_mcp._access_links import _page_range
from scholar_mcp._epo_xml import _DOI_RE
from scholar_mcp._standards_client import resolve_identifier_local
from scholar_mcp._sync_cen import _normalise_en_identifier

_RUN = 200_000


def test_a_page_value_of_dashes_is_not_a_page_range() -> None:
    """S2 and CrossRef supply ``pages``; 2,000 dashes took the old regex 9 s."""
    assert _page_range("1" + "-" * 20_000 + " ") == (None, None)


def test_a_page_range_still_splits() -> None:
    assert _page_range("S-12 - S-20") == ("S-12", "S-20")


@pytest.mark.parametrize(
    "raw",
    [
        "iso 9001" + " " * _RUN + "x",
        "EN ISO 13849-1" + " " * _RUN + "x",
        "etsi en 303" + " " * _RUN + "x",
    ],
    ids=["iso", "en-iso", "etsi"],
)
def test_a_long_run_of_spaces_does_not_resolve(raw: str) -> None:
    assert resolve_identifier_local(raw) is None


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("ISO 9001 2015", "ISO 9001:2015"),
        ("ISO 9001 - 2015", "ISO 9001:2015"),
        ("ISO 9001 : 2015", "ISO 9001:2015"),
        ("etsi en 303 - 645", "ETSI EN 303 645"),
    ],
)
def test_every_separator_still_resolves(raw: str, canonical: str) -> None:
    result = resolve_identifier_local(raw)
    assert result is not None
    assert result[0] == canonical


def test_a_doi_label_followed_by_spaces_finds_nothing() -> None:
    assert _DOI_RE.search("doi" + " " * _RUN + "x") is None


def test_the_cen_normaliser_keeps_a_long_run_of_spaces() -> None:
    raw = "EN 1 V1" + " " * _RUN + "x"
    assert _normalise_en_identifier(raw) == raw.strip()
