"""Tests for _sync_cc — Common Criteria framework + Protection Profile loader."""

from __future__ import annotations

from pathlib import Path

import pytest


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
