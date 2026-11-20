"""Standards search ranks the current edition first (#487)."""

from __future__ import annotations

import httpx
import pytest

from scholar_mcp import _cache
from scholar_mcp._cache import ScholarCache
from scholar_mcp._record_types import StandardRecord
from scholar_mcp._standards_client import StandardsClient
from scholar_mcp._standards_ranking import rank_standards


def _std(
    identifier: str,
    status: str = "published",
    published_date: str | None = None,
    title: str = "",
) -> StandardRecord:
    return StandardRecord(
        identifier=identifier,
        title=title or identifier,
        body="ISO",
        status=status,
        published_date=published_date,
        superseded_by=[],
    )


def _ids(records: list[StandardRecord]) -> list[str]:
    return [r["identifier"] for r in records]


# The order the issue observed for "27001", with the 2022 edition last.
_STORAGE_ORDER = [
    _std("ISO/IEC 27001:2005", "superseded", "2005-10-14"),
    _std("ISO/IEC 27001:2013/Cor 1:2014", "superseded", "2014-09-18"),
    _std("ISO/IEC 27013:2021", "published", "2021-11-25", "Guidance on ISO/IEC 27001"),
    _std("ISO/IEC 27001:2013", "superseded", "2013-09-25"),
    _std("ISO/IEC 27001:2022/Amd 1:2024", "published", "2024-02-23"),
    _std("ISO/IEC 27001:2022", "published", "2022-10-25"),
]


def test_a_yearless_query_puts_the_current_edition_first() -> None:
    """Published before replaced, the edition before its amendments, the
    standard's own editions before a document that only names it in its title."""
    assert _ids(rank_standards(_STORAGE_ORDER, "27001")) == [
        "ISO/IEC 27001:2022",
        "ISO/IEC 27001:2022/Amd 1:2024",
        "ISO/IEC 27001:2013",
        "ISO/IEC 27001:2005",
        "ISO/IEC 27001:2013/Cor 1:2014",
        "ISO/IEC 27013:2021",
    ]


def test_a_query_naming_a_replaced_edition_returns_it_first() -> None:
    """An exact identifier beats a current document that also matches it."""
    records = [
        _std("EN ISO/IEC 27001:2013", "published", "2017-02-01"),
        _std("ISO/IEC 27001:2013/Cor 1:2014", "superseded", "2014-09-18"),
        _std("ISO/IEC 27001:2013", "superseded", "2013-09-25"),
    ]
    ranked = rank_standards(records, " iso/iec 27001:2013 ")
    assert _ids(ranked)[0] == "ISO/IEC 27001:2013"


def test_a_companion_document_ranks_below_the_document_itself() -> None:
    """800-53A and 800-53B are other documents than 800-53."""
    records = [
        _std("NIST SP 800-53A Rev. 5", "published", "2022"),
        _std("NIST SP 800-53B", "published", "2020"),
        _std("NIST SP 800-53 Rev. 5", "published", "2020"),
    ]
    assert _ids(rank_standards(records, "SP 800-53"))[0] == "NIST SP 800-53 Rev. 5"


def test_another_document_ranks_below_the_standards_replaced_editions() -> None:
    """A published document whose number contains the query is another
    document, as a handbook is (#674): it follows ISO 9001's own editions."""
    records = [
        _std("ISO 29001:2020", "published", "2020-11"),
        _std("ISO/IEC 9001-HBK:2024", "published", "2024-05-03"),
        _std("ISO 9001:2008", "withdrawn", "2008-11"),
        _std("ISO 9001:2015", "published", "2015-09"),
        _std("ISO 9001:2015/Amd 1:2024", "published", "2024-02"),
    ]
    assert _ids(rank_standards(records, "9001")) == [
        "ISO 9001:2015",
        "ISO 9001:2015/Amd 1:2024",
        "ISO 9001:2008",
        "ISO/IEC 9001-HBK:2024",
        "ISO 29001:2020",
    ]


@pytest.mark.parametrize(
    ("current", "other", "query"),
    [
        # A dash and digits is an edition, a part or a year of the same number.
        ("FIPS 140-3", "FIPS 1400", "FIPS 140"),
        ("IEEE Std 1588-2019", "IEEE Std 1588c-2024", "1588"),
        # A dot and more of a number is another document.
        ("IEEE Std 802-2014", "IEEE Std 802.11-2024", "802"),
    ],
)
def test_an_edition_suffix_names_the_same_document(
    current: str, other: str, query: str
) -> None:
    """The standard's replaced edition still outranks the other document."""
    records = [
        _std(other, "published", "2024"),
        _std(current, "superseded", "2019"),
    ]
    assert _ids(rank_standards(records, query)) == [current, other]


def test_statuses_rank_published_draft_superseded_withdrawn() -> None:
    """An unknown status sits with draft."""
    records = [
        _std("X 1:2001", "withdrawn"),
        _std("X 1:2002", "superseded"),
        _std("X 1:2003", "draft"),
        _std("X 1:2004", "unheard-of"),
        _std("X 1:2005", "published"),
    ]
    assert _ids(rank_standards(records, "X 1")) == [
        "X 1:2005",
        "X 1:2003",
        "X 1:2004",
        "X 1:2002",
        "X 1:2001",
    ]


def test_ties_go_to_the_newest_then_by_identifier() -> None:
    """An undated record goes last; equal dates fall back to the identifier."""
    records = [
        _std("B", published_date=None, title="topic"),
        _std("D", published_date="2019", title="topic"),
        _std("C", published_date="2021-03", title="topic"),
        _std("A", published_date="2019", title="topic"),
    ]
    assert _ids(rank_standards(records, "topic")) == ["C", "A", "D", "B"]


async def test_synced_search_returns_the_current_edition_at_limit_one(
    cache: ScholarCache,
) -> None:
    """The issue's limit=3 query left the 2022 edition out entirely."""
    for record in _STORAGE_ORDER:
        await cache.set_standard(
            record["identifier"], record, source="ISO", synced=True
        )
    found = await cache.search_synced_standards("27001", source="ISO", limit=1)
    assert _ids(found) == ["ISO/IEC 27001:2022"]


async def test_synced_search_keeps_identifier_matches_past_the_candidate_cap(
    cache: ScholarCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SQL orders the matches before the cap, so title matches cannot crowd
    out the standard itself."""
    monkeypatch.setattr(_cache, "_SYNCED_SEARCH_CANDIDATES", 2)
    for n in range(5):
        record = _std(f"ISO {n}:2020", "published", "2020", "Guide to ISO 27001")
        await cache.set_standard(
            record["identifier"], record, source="ISO", synced=True
        )
    own = _std("ISO 27001:2013", "withdrawn", "2013")
    await cache.set_standard(own["identifier"], own, source="ISO", synced=True)

    found = await cache.search_synced_standards("27001", source="ISO", limit=1)
    assert _ids(found) == ["ISO 27001:2013"]


class _FetcherA:
    def __init__(self, records: list[StandardRecord]) -> None:
        self.records = records

    async def search(self, query: str, *, limit: int = 10) -> list[StandardRecord]:  # noqa: ARG002 — the protocol's signature
        return self.records[:limit]

    async def get(self, identifier: str) -> StandardRecord | None:  # noqa: ARG002 — the protocol's signature
        return None


class _FetcherB(_FetcherA):
    """A second type: the client keeps one fetcher per type."""


@pytest.fixture
async def client():
    http = httpx.AsyncClient()
    client = StandardsClient(http)
    client._fetchers = {
        "A": _FetcherA([_std("A 1:2001", "withdrawn", "2001")]),
        "B": _FetcherB([_std("A 1:2020", "published", "2020")]),
    }
    yield client
    await http.aclose()


async def test_an_all_bodies_search_ranks_across_bodies(
    client: StandardsClient,
) -> None:
    """Results used to come body by body in fetcher order."""
    records, failures = await client.search_with_failures("A 1", limit=1)
    assert _ids(records) == ["A 1:2020"]
    assert failures == []


async def test_a_one_body_search_ranks_what_the_body_returned(
    client: StandardsClient,
) -> None:
    """IETF, W3C and ETSI return upstream's order; it is ranked here."""
    client._fetchers["A"] = _FetcherA(
        [_std("A 1:2001", "withdrawn", "2001"), _std("A 1:2020", "published", "2020")]
    )
    records, _ = await client.search_with_failures("A 1", body="A", limit=2)
    assert _ids(records) == ["A 1:2020", "A 1:2001"]


async def test_an_unresolved_identifier_lists_the_current_edition_first(
    client: StandardsClient,
) -> None:
    """resolve_standard_identifier's ambiguous candidates come from search."""
    candidates = await client.resolve("A 1")
    assert _ids(candidates) == ["A 1:2020", "A 1:2001"]


async def test_nist_search_ranks_the_whole_catalogue_before_the_limit(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The catalogue lists 800-53A Rev. 4 and old revisions before Rev. 5."""
    from unittest.mock import AsyncMock

    from scholar_mcp._rate_limiter import RateLimiter
    from scholar_mcp._standards_client import _NISTFetcher

    catalogue = [
        _std("NIST SP 800-53A Rev. 4", "superseded", "2013"),
        _std("NIST SP 800-53 Rev. 1", "superseded", "2006"),
        _std("NIST SP 800-53B", "published", "2020"),
        _std("NIST SP 800-53 Rev. 5", "published", "2020"),
    ]
    async with httpx.AsyncClient() as http:
        fetcher = _NISTFetcher(http, RateLimiter(delay=0.0), cache_dir=tmp_path)
        monkeypatch.setattr(fetcher, "_fetch_all", AsyncMock(return_value=catalogue))
        found = await fetcher.search("SP 800-53", limit=1)
    assert _ids(found) == ["NIST SP 800-53 Rev. 5"]


async def test_etsi_search_ranks_every_row_before_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ETSI answers with every match at once, so none is cut unranked."""
    from unittest.mock import AsyncMock

    from scholar_mcp import _standards_client
    from scholar_mcp._rate_limiter import RateLimiter
    from scholar_mcp._standards_client import _ETSIFetcher

    rows = [
        _std("ETSI EN 303 645 V2.1.1", "superseded", "2020-06"),
        _std("ETSI EN 303 645 V3.1.3", "published", "2024-09"),
    ]
    monkeypatch.setattr(_standards_client, "_normalize_etsi", lambda row: row)
    async with httpx.AsyncClient() as http:
        fetcher = _ETSIFetcher(http, RateLimiter(delay=0.0))
        monkeypatch.setattr(fetcher, "_rows", AsyncMock(return_value=rows))
        found = await fetcher.search("303 645", limit=1)
    assert _ids(found) == ["ETSI EN 303 645 V3.1.3"]
