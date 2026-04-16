"""Tests for _sync_cc — Common Criteria framework + Protection Profile loader."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx


def test_framework_to_records_dual_publication_yields_two_records() -> None:
    """A CC framework entry with iso_identifier yields CC + ISO records."""
    from scholar_mcp._sync_cc import CCFrameworkEntry, _framework_to_records

    entry = CCFrameworkEntry(
        cc_identifier="CC:2022 Part 1",
        iso_identifier="ISO/IEC 15408-1:2022",
        title="Information security, cybersecurity and privacy protection — "
        "Evaluation criteria for IT security — Part 1: Introduction and general model",
        cc_pdf_url="https://www.commoncriteriaportal.org/files/ccfiles/CC2022PART1R1.pdf",
        published_date="2022-11-01",
        cc_version="2022",
    )

    records = _framework_to_records(entry)

    assert len(records) == 2
    cc, iso = records[0], records[1]

    assert cc["identifier"] == "CC:2022 Part 1"
    assert cc["body"] == "CC"
    assert cc["full_text_url"] == entry.cc_pdf_url
    assert cc["full_text_available"] is True
    assert cc["status"] == "published"
    assert cc["related"] == ["ISO/IEC 15408-1:2022"]
    assert cc["published_date"] == "2022-11-01"

    assert iso["identifier"] == "ISO/IEC 15408-1:2022"
    assert iso["body"] == "ISO/IEC"
    assert iso["full_text_url"] == entry.cc_pdf_url
    assert iso["full_text_available"] is True
    assert iso["related"] == ["CC:2022 Part 1"]


def test_framework_to_records_cc_only_yields_one_record() -> None:
    """When iso_identifier is None (CC:2022 Parts 4-5), only one record."""
    from scholar_mcp._sync_cc import CCFrameworkEntry, _framework_to_records

    entry = CCFrameworkEntry(
        cc_identifier="CC:2022 Part 4",
        iso_identifier=None,
        title="Framework for the specification of evaluation methods and activities",
        cc_pdf_url="https://www.commoncriteriaportal.org/files/ccfiles/CC2022PART4R1.pdf",
        published_date="2022-11-01",
        cc_version="2022",
    )

    records = _framework_to_records(entry)
    assert len(records) == 1
    assert records[0]["identifier"] == "CC:2022 Part 4"
    assert records[0]["body"] == "CC"
    assert records[0].get("related", []) == []


def test_framework_aliases_include_fuzzy_forms() -> None:
    """Aliases cover 'Common Criteria 2022 Part 1', 'CC 2022 Part 1', etc."""
    from scholar_mcp._sync_cc import CCFrameworkEntry, _framework_aliases

    entry = CCFrameworkEntry(
        cc_identifier="CC:2022 Part 1",
        iso_identifier="ISO/IEC 15408-1:2022",
        title="...",
        cc_pdf_url="...",
        published_date="2022-11-01",
        cc_version="2022",
    )

    aliases = _framework_aliases(entry)
    assert "Common Criteria 2022 Part 1" in aliases
    assert "CC 2022 Part 1" in aliases
    assert "Common Criteria:2022 Part 1" in aliases


def test_framework_docs_contains_cc_2022_parts_1_through_5() -> None:
    """The hard-coded table includes the five CC:2022 parts."""
    from scholar_mcp._sync_cc import _FRAMEWORK_DOCS

    cc_2022_parts = {
        e.cc_identifier
        for e in _FRAMEWORK_DOCS
        if e.cc_identifier.startswith("CC:2022 Part")
    }
    assert cc_2022_parts == {
        "CC:2022 Part 1",
        "CC:2022 Part 2",
        "CC:2022 Part 3",
        "CC:2022 Part 4",
        "CC:2022 Part 5",
    }


def test_framework_docs_dual_publication_iso_mappings() -> None:
    """Parts 1-3 of CC:2022 are dual-published as ISO/IEC 15408-1/2/3:2022."""
    from scholar_mcp._sync_cc import _FRAMEWORK_DOCS

    by_cc = {e.cc_identifier: e for e in _FRAMEWORK_DOCS}
    assert by_cc["CC:2022 Part 1"].iso_identifier == "ISO/IEC 15408-1:2022"
    assert by_cc["CC:2022 Part 2"].iso_identifier == "ISO/IEC 15408-2:2022"
    assert by_cc["CC:2022 Part 3"].iso_identifier == "ISO/IEC 15408-3:2022"
    assert by_cc["CC:2022 Part 4"].iso_identifier is None
    assert by_cc["CC:2022 Part 5"].iso_identifier is None


def test_framework_docs_includes_cem_2022() -> None:
    """CEM:2022 + ISO/IEC 18045:2022 dual entry is present."""
    from scholar_mcp._sync_cc import _FRAMEWORK_DOCS

    cem = next((e for e in _FRAMEWORK_DOCS if e.cc_identifier == "CEM:2022"), None)
    assert cem is not None
    assert cem.iso_identifier == "ISO/IEC 18045:2022"


def test_framework_docs_includes_cc_2017_three_parts() -> None:
    """CC:2017 (CC 3.1 Rev 5) Parts 1-3 present, dual-mapped to 15408:2009/8."""
    from scholar_mcp._sync_cc import _FRAMEWORK_DOCS

    by_cc = {e.cc_identifier: e for e in _FRAMEWORK_DOCS}
    assert by_cc["CC:2017 Part 1"].iso_identifier == "ISO/IEC 15408-1:2009"
    assert by_cc["CC:2017 Part 2"].iso_identifier == "ISO/IEC 15408-2:2008"
    assert by_cc["CC:2017 Part 3"].iso_identifier == "ISO/IEC 15408-3:2008"


@pytest.fixture
def pp_csv_path() -> Path:
    return Path(__file__).parent / "fixtures" / "standards" / "cc_sample" / "pps.csv"


def test_extract_pp_id_kecs() -> None:
    """KECS scheme: KECS-PP-NNNN-YYYY extracted from URL filename."""
    from scholar_mcp._sync_cc import _extract_pp_id

    url = (
        "http://www.commoncriteriaportal.org:443/files/epfiles/"
        "KECS-PP-0822-2017 Korean National PP for Single Sign On V1.0(eng).pdf"
    )
    assert _extract_pp_id("KR", url, "Korean National PP …") == "KECS-PP-0822-2017"


def test_extract_pp_id_bsi() -> None:
    """BSI: BSI-CC-PP-NNNN[-VN]-YYYY extracted."""
    from scholar_mcp._sync_cc import _extract_pp_id

    url = (
        "http://www.commoncriteriaportal.org:443/files/epfiles/"
        "BSI-CC-PP-0099-V2-2017.pdf"
    )
    assert (
        _extract_pp_id("DE", url, "PP for Hardcopy Devices") == "BSI-CC-PP-0099-V2-2017"
    )


def test_extract_pp_id_anssi() -> None:
    """ANSSI: ANSSI-CC-PP-YYYY_NN canonicalises underscore to slash."""
    from scholar_mcp._sync_cc import _extract_pp_id

    url = (
        "http://www.commoncriteriaportal.org:443/files/epfiles/ANSSI-CC-PP-2014_01.pdf"
    )
    assert _extract_pp_id("FR", url, "French PP for OS") == "ANSSI-CC-PP-2014/01"


def test_extract_pp_id_ccn() -> None:
    """CCN (Spanish): CCN-PP-NNNN-YYYY extracted."""
    from scholar_mcp._sync_cc import _extract_pp_id

    url = "http://www.commoncriteriaportal.org:443/files/epfiles/CCN-PP-0058-2021.pdf"
    assert _extract_pp_id("ES", url, "Spanish PP for SE") == "CCN-PP-0058-2021"


def test_extract_pp_id_unknown_scheme_falls_back_to_composite() -> None:
    """Unknown scheme → composite form 'CC PP {scheme}-{name}'."""
    from scholar_mcp._sync_cc import _extract_pp_id

    url = "http://example.com/random-pp.pdf"
    result = _extract_pp_id("XX", url, "Strange Unknown Scheme PP")
    assert result == "CC PP XX-Strange Unknown Scheme PP"


def test_pp_row_to_record_happy_path(pp_csv_path: Path) -> None:
    """A complete CSV row maps to a populated StandardRecord."""
    import csv

    from scholar_mcp._sync_cc import _pp_row_to_record

    with pp_csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    record = _pp_row_to_record(rows[0])

    assert record is not None
    assert record["identifier"] == "KECS-PP-0822-2017"
    assert record["body"] == "CC"
    assert record["status"] == "published"
    assert record["title"].startswith("Korean National Protection Profile")
    assert record["full_text_url"] is not None
    assert record["full_text_available"] is True
    assert record["published_date"] == "2017-08-18"


def test_pp_row_to_record_archived_status(pp_csv_path: Path) -> None:
    """A row with a non-empty Archived Date → status='archived'."""
    import csv

    from scholar_mcp._sync_cc import _pp_row_to_record

    with pp_csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    record = _pp_row_to_record(rows[1])
    assert record is not None
    assert record["status"] == "archived"


def test_pp_row_to_record_returns_none_on_missing_pp_url() -> None:
    """A row with no Protection Profile URL is unusable → None."""
    from scholar_mcp._sync_cc import _pp_row_to_record

    bad_row = {
        "Category": "Anything",
        "Name": "Some PP",
        "Version": "V1.0",
        "Assurance Level": "EAL1",
        "Certification Date": "01/01/2024",
        "Archived Date": "",
        "Certification Report URL": "",
        "Protection Profile": "",
        "Maintenance Date": "",
        "Maintenance Title": "",
        "Maintenance Report": "",
        "Scheme": "DE",
    }
    assert _pp_row_to_record(bad_row) is None


def test_pp_row_to_record_published_date_iso_format(pp_csv_path: Path) -> None:
    """MM/DD/YYYY upstream date is normalised to YYYY-MM-DD."""
    import csv

    from scholar_mcp._sync_cc import _pp_row_to_record

    with pp_csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    record = _pp_row_to_record(rows[0])
    assert record is not None
    assert record["published_date"] == "2017-08-18"


@pytest.fixture
def pps_csv_bytes(pp_csv_path: Path) -> bytes:
    return pp_csv_path.read_bytes()


def _mock_pps(router: respx.Router, body: bytes, status: int = 200) -> None:
    router.get("https://www.commoncriteriaportal.org/pps/pps.csv").mock(
        return_value=httpx.Response(
            status,
            content=body,
            headers={"Content-Type": "text/csv"},
        )
    )


@pytest.mark.asyncio
async def test_cc_loader_cold_sync_writes_framework_and_pps(
    tmp_path: Path, pps_csv_bytes: bytes
) -> None:
    """Cold sync writes all framework records + every PP row from the CSV."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_cc import _FRAMEWORK_DOCS, CCLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        with respx.mock(assert_all_called=False) as router:
            _mock_pps(router, pps_csv_bytes)

            async with httpx.AsyncClient() as http:
                report = await CCLoader(http=http).sync(cache)

        framework_records = sum(2 if e.iso_identifier else 1 for e in _FRAMEWORK_DOCS)
        assert report.added == framework_records + 6
        assert report.body == "CC"
        cc_p1 = await cache.get_standard("CC:2022 Part 1")
        iso_p1 = await cache.get_standard("ISO/IEC 15408-1:2022")
        assert cc_p1 is not None and cc_p1["body"] == "CC"
        assert iso_p1 is not None and iso_p1["body"] == "ISO/IEC"
        assert iso_p1["full_text_url"] == cc_p1["full_text_url"]
        bsi = await cache.get_standard("BSI-CC-PP-0099-V2-2017")
        assert bsi is not None
        assert bsi["status"] == "archived"
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cc_loader_resync_unchanged_csv_short_circuits(
    tmp_path: Path, pps_csv_bytes: bytes
) -> None:
    """Re-sync with same CSV content hash returns unchanged report."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_cc import CCLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        with respx.mock(assert_all_called=False) as router:
            _mock_pps(router, pps_csv_bytes)

            async with httpx.AsyncClient() as http:
                first = await CCLoader(http=http).sync(cache)
                second = await CCLoader(http=http).sync(cache)

        assert first.added > 0
        assert second.added == 0
        assert second.unchanged > 0
        assert second.upstream_ref == first.upstream_ref
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cc_loader_resync_changed_csv_detects_updates(
    tmp_path: Path, pps_csv_bytes: bytes
) -> None:
    """Modified CSV → updated counter increments for the changed row."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_cc import CCLoader

    modified = pps_csv_bytes.replace(
        b"Korean National Protection Profile for Single Sign On V1.0",
        b"Korean National Protection Profile for Single Sign On V1.0 (REVISED)",
    )

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        with respx.mock(assert_all_called=False) as router:
            _mock_pps(router, pps_csv_bytes)

            async with httpx.AsyncClient() as http:
                first = await CCLoader(http=http).sync(cache)

        with respx.mock(assert_all_called=False) as router:
            _mock_pps(router, modified)

            async with httpx.AsyncClient() as http:
                second = await CCLoader(http=http).sync(cache)

        assert first.added > 0
        assert second.updated >= 1
        assert second.upstream_ref != first.upstream_ref
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cc_loader_withdrawal_detection(
    tmp_path: Path, pps_csv_bytes: bytes
) -> None:
    """A PP that disappears in second sync gets status='withdrawn'."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_cc import CCLoader

    lines = pps_csv_bytes.splitlines(keepends=True)
    reduced = b"".join(lines[:2] + lines[3:])  # header + KECS + ANSSI + ...

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        with respx.mock(assert_all_called=False) as router:
            _mock_pps(router, pps_csv_bytes)
            async with httpx.AsyncClient() as http:
                await CCLoader(http=http).sync(cache)

        with respx.mock(assert_all_called=False) as router:
            _mock_pps(router, reduced)
            async with httpx.AsyncClient() as http:
                second = await CCLoader(http=http).sync(cache)

        assert second.withdrawn == 1
        bsi = await cache.get_standard("BSI-CC-PP-0099-V2-2017")
        assert bsi is not None
        assert bsi["status"] == "withdrawn"
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cc_loader_withdrawal_aborts_on_majority_missing(
    tmp_path: Path, pps_csv_bytes: bytes
) -> None:
    """If >50% of synced PPs disappear, withdrawal pass aborts."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_cc import CCLoader

    lines = pps_csv_bytes.splitlines(keepends=True)
    reduced = b"".join(lines[:2])  # header + KECS row

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        with respx.mock(assert_all_called=False) as router:
            _mock_pps(router, pps_csv_bytes)
            async with httpx.AsyncClient() as http:
                await CCLoader(http=http).sync(cache)

        with respx.mock(assert_all_called=False) as router:
            _mock_pps(router, reduced)
            async with httpx.AsyncClient() as http:
                second = await CCLoader(http=http).sync(cache)

        assert second.withdrawn == 0
        assert any("withdrawal" in e.lower() for e in second.errors)
        bsi = await cache.get_standard("BSI-CC-PP-0099-V2-2017")
        assert bsi is not None
        assert bsi["status"] == "archived"
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cc_loader_csv_fetch_404_returns_degraded_report(
    tmp_path: Path,
) -> None:
    """HTTP 404 on pps.csv → framework records still loaded, error logged."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_cc import _FRAMEWORK_DOCS, CCLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        with respx.mock(assert_all_called=False) as router:
            _mock_pps(router, b"", status=404)

            async with httpx.AsyncClient() as http:
                report = await CCLoader(http=http).sync(cache)

        framework_records = sum(2 if e.iso_identifier else 1 for e in _FRAMEWORK_DOCS)
        assert report.added == framework_records
        assert any("pp" in e.lower() or "csv" in e.lower() for e in report.errors)
        cc_p1 = await cache.get_standard("CC:2022 Part 1")
        assert cc_p1 is not None
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cc_loader_owns_iso_15408_records(
    tmp_path: Path, pps_csv_bytes: bytes
) -> None:
    """The CC dual record overrides any prior ISO loader entry for 15408.

    With Task 1's denylist in place the ISO loader never writes
    iso-iec-15408-* slugs at all, so this test simulates the
    cross-loader scenario by writing a placeholder record manually,
    then asserting CCLoader replaces it with the CC-sourced version
    (free PDF, related cross-link, source='CC').
    """
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._record_types import StandardRecord
    from scholar_mcp._sync_cc import CCLoader

    placeholder: StandardRecord = {
        "identifier": "ISO/IEC 15408-1:2022",
        "title": "Placeholder from a hypothetical ISO loader run",
        "body": "ISO/IEC",
        "status": "published",
        "full_text_url": None,
        "full_text_available": False,
    }
    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        await cache.set_standard(
            "ISO/IEC 15408-1:2022", placeholder, source="ISO", synced=True
        )

        with respx.mock(assert_all_called=False) as router:
            _mock_pps(router, pps_csv_bytes)
            async with httpx.AsyncClient() as http:
                await CCLoader(http=http).sync(cache)

        rec = await cache.get_standard("ISO/IEC 15408-1:2022")
        assert rec is not None
        assert rec["full_text_available"] is True
        assert rec["full_text_url"] is not None
        assert rec["full_text_url"].startswith("https://www.commoncriteriaportal.org/")
        assert rec.get("related") == ["CC:2022 Part 1"]
    finally:
        await cache.close()


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_fetch_cc_pps_csv_real() -> None:
    """Smoke: real pps.csv parses into >=100 records with >=5 distinct schemes.

    Catches schema drift / portal layout changes early. Opt-in via
    ``pytest -m live``; not run in CI by default.
    """
    import csv as _csv
    import io as _io

    async with httpx.AsyncClient(timeout=30.0) as http:
        response = await http.get(
            "https://www.commoncriteriaportal.org/pps/pps.csv",
            follow_redirects=True,
        )
        response.raise_for_status()

    rows = list(_csv.DictReader(_io.StringIO(response.text)))
    assert len(rows) >= 100, f"only {len(rows)} rows in pps.csv"
    schemes = {r.get("Scheme", "").strip() for r in rows if r.get("Scheme")}
    assert len(schemes) >= 5, f"only {len(schemes)} distinct schemes: {schemes}"


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_framework_pdf_urls_resolve_real() -> None:
    """Smoke: every _FRAMEWORK_DOCS PDF URL responds 200 to HEAD.

    Catches PDF URL rot — CCRA occasionally moves PDFs after a release.
    """
    from scholar_mcp._sync_cc import _FRAMEWORK_DOCS

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http:
        for entry in _FRAMEWORK_DOCS:
            response = await http.head(entry.cc_pdf_url)
            assert response.status_code == 200, (
                f"{entry.cc_identifier} → {entry.cc_pdf_url} returned "
                f"{response.status_code}"
            )
