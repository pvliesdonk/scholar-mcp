"""Tests for _sync_cc — Common Criteria framework + Protection Profile loader."""

from __future__ import annotations


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
