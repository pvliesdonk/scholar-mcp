"""Tests for patent citation entries (_patent_citation.py)."""

from __future__ import annotations

import json

import pytest

from scholar_mcp._citation_formatter import (
    format_bibtex,
    format_csl_json,
    format_ris,
    is_patent_record,
)
from scholar_mcp._patent_citation import (
    patent_bibtex_entry,
    patent_csl_entry,
    patent_key,
    patent_ris_record,
    person_name,
    publication_status,
)
from tests.fixtures.patent_records import ep3491801b1

_SOURCED: list[tuple[str, str, str]] = [
    *[("EP", k, "application") for k in ("A1", "A2", "A3", "A8", "A9")],
    *[("EP", k, "grant") for k in ("B1", "B2", "B3", "B8", "B9")],
    *[("WO", k, "application") for k in ("A1", "A2", "A3", "A4", "A8", "A9")],
    *[("US", k, "application") for k in ("A1", "A2", "A9", "P1", "P4", "P9")],
    *[("US", k, "grant") for k in ("B1", "B2", "B9", "E", "S", "P2", "P3", "A")],
    *[("DE", k, "application") for k in ("A1", "A8", "A9")],
    *[("DE", k, "grant") for k in ("B3", "B4", "B8", "B9", "C5")],
]
_UNKNOWN: list[tuple[str, str, str]] = [
    ("US", "H1", "unknown"),
    ("US", "E1", "unknown"),
    ("EP", "", "unknown"),
    ("EP", "C1", "unknown"),
    ("DE", "B1", "unknown"),
    ("GB", "A", "unknown"),
    ("FR", "B1", "unknown"),
    ("JP", "A", "unknown"),
]


@pytest.mark.parametrize(("country", "kind", "expected"), _SOURCED + _UNKNOWN)
def test_publication_status(country: str, kind: str, expected: str) -> None:
    assert publication_status(country, kind) == expected


def test_publication_status_ignores_case() -> None:
    assert publication_status("ep", "b1") == "grant"


def test_person_name_joins_given_names() -> None:
    assert person_name("VAN LIESDONK, Peter, Petrus") == (
        "VAN LIESDONK",
        "Peter Petrus",
    )
    assert person_name("PLETEA, Daniel") == ("PLETEA", "Daniel")
    assert person_name("SMITH,") == ("SMITH", "")
    assert person_name("PLETEA DANIEL") is None
    assert person_name(", Daniel") is None


def test_bibtex_holders_are_braced() -> None:
    record = ep3491801b1()
    record["applicants"]["original"].append("Acme & Co")
    entry = patent_bibtex_entry(record, set())
    assert "  holder = {{Koninklijke Philips N.V.} and {Acme \\& Co}}," in entry
    assert "  author = {PLETEA, Daniel and VAN LIESDONK, Peter Petrus}," in entry


def test_bibtex_type_key() -> None:
    cases = {
        "EP.3491801.B1": "patenteu",
        "EP.3491801.A1": "patreqeu",
        "EP.3491801.A3": "patreqeu",
        "US.11234567.B2": "patentus",
        "US.20200012345.A1": "patrequs",
        "DE.102016000001.A1": "patreqde",
        "DE.102016000001.B4": "patentde",
    }
    for number, key in cases.items():
        record = ep3491801b1()
        record["publication_number"] = number
        entry = patent_bibtex_entry(record, set())
        assert f"  type = {{{key}}}," in entry
        assert "location" not in entry
    record = ep3491801b1()
    record["publication_number"] = "WO.2018019745.A1"
    entry = patent_bibtex_entry(record, set())
    assert "  type = {patreq}," in entry
    assert "  location = {WO}," in entry


def test_bibtex_unknown_status_uses_location() -> None:
    record = ep3491801b1()
    record["publication_number"] = "GB.2550000.A"
    entry = patent_bibtex_entry(record, set())
    assert "type =" not in entry
    assert "  location = {GB}," in entry
    assert "  number = {GB 2550000 A}," in entry


def test_bibtex_full_entry() -> None:
    entry = patent_bibtex_entry(ep3491801b1(), set())
    assert entry.startswith("@patent{ep3491801b1,\n")
    assert "  title = {{Method and system for secure key management}}," in entry
    assert "  number = {EP 3491801 B1}," in entry
    assert "  date = {2020-09-02}," in entry
    assert "  abstract = {A key is derived \\& stored.}," in entry
    assert "  url = {https://worldwide.espacenet.com/" in entry
    assert entry.endswith("\n}")


def test_bibtex_standardised_fallback_strips_tag() -> None:
    record = ep3491801b1()
    record["applicants"]["original"] = []
    record["inventors"]["original"] = []
    entry = patent_bibtex_entry(record, set())
    assert "  author = {{PLETEA DANIEL}}," in entry
    assert "  holder = {{KONINKLIJKE PHILIPS NV}}," in entry


def test_bibtex_applicants_become_authors() -> None:
    record = ep3491801b1()
    del record["inventors"]
    entry = patent_bibtex_entry(record, set())
    assert "  author = {{Koninklijke Philips N.V.}}," in entry
    assert "holder" not in entry


def test_bibtex_bad_date_and_bare_record() -> None:
    record = ep3491801b1()
    record["publication_date"] = "20200902"
    assert "date =" not in patent_bibtex_entry(record, set())
    bare = patent_bibtex_entry({"publication_number": ""}, set())
    assert bare == "@patent{patent,\n}"


def test_patent_key_dedupes() -> None:
    seen: set[str] = {"ep3491801b1"}
    assert patent_key(ep3491801b1(), seen) == "ep3491801b1_2"
    assert patent_key(ep3491801b1(), seen) == "ep3491801b1_3"


def test_csl_patent_entry() -> None:
    entry = patent_csl_entry(ep3491801b1(), set())
    assert entry == {
        "id": "ep3491801b1",
        "type": "patent",
        "title": "Method and system for secure key management",
        "author": [
            {"family": "PLETEA", "given": "Daniel"},
            {"family": "VAN LIESDONK", "given": "Peter Petrus"},
        ],
        "authority": "EP",
        "number": "EP 3491801 B1",
        "issued": {"date-parts": [[2020, 9, 2]]},
        "submitted": {"date-parts": [[2017, 7, 20]]},
        "URL": "https://worldwide.espacenet.com/patent/search?q=pn%3DEP3491801B1",
        "abstract": "A key is derived & stored.",
    }


def test_csl_application_genre_and_literal_names() -> None:
    record = ep3491801b1()
    record["publication_number"] = "WO.2018019745.A1"
    record["inventors"] = {"original": ["ACME LAB", "DOE,"], "standardised": []}
    record["filing_date"] = ""
    entry = patent_csl_entry(record, set())
    assert entry["genre"] == "patent application"
    assert entry["author"] == [{"literal": "ACME LAB"}, {"family": "DOE"}]
    assert "submitted" not in entry
    assert "Koninklijke" not in json.dumps(entry)


def test_ris_patent_record() -> None:
    record = ep3491801b1()
    record["applicants"]["original"].append("Acme Co")
    assert patent_ris_record(record).splitlines() == [
        "TY  - PAT",
        "AU  - PLETEA, Daniel",
        "AU  - VAN LIESDONK, Peter Petrus",
        "TI  - Method and system for secure key management",
        "PY  - 2020///",
        "DA  - 2020/09/02",
        "PB  - Koninklijke Philips N.V.; Acme Co",
        "SN  - EP3491801B1",
        "UR  - https://worldwide.espacenet.com/patent/search?q=pn%3DEP3491801B1",
        "AB  - A key is derived & stored.",
        "ER  -",
    ]


def test_ris_names_without_comma_stay_as_is() -> None:
    record = ep3491801b1()
    record["inventors"] = {"original": ["ACME LAB", "DOE,"], "standardised": []}
    lines = patent_ris_record(record).splitlines()
    assert "AU  - ACME LAB" in lines
    assert "AU  - DOE" in lines


_PAPER = {
    "paperId": "abc",
    "title": "Attention Is All You Need",
    "year": 2017,
    "venue": "Journal",
    "authors": [{"name": "Ashish Vaswani"}],
}


def test_is_patent_record() -> None:
    assert is_patent_record(ep3491801b1())
    assert not is_patent_record(_PAPER)  # type: ignore[arg-type]


def test_formatters_keep_mixed_order() -> None:
    records = [ep3491801b1(), _PAPER, ep3491801b1()]
    errors = [{"identifier": "EP9", "reason": "rate_limited"}]

    bibtex = format_bibtex(records, errors)  # type: ignore[arg-type]
    assert bibtex.startswith("% Could not resolve: EP9 (rate_limited)")
    assert (
        bibtex.index("@patent{ep3491801b1,")
        < bibtex.index("@article{vaswani2017,")
        < bibtex.index("@patent{ep3491801b1_2,")
    )

    csl = json.loads(format_csl_json(records, errors))  # type: ignore[arg-type]
    assert [c["id"] for c in csl["citations"]] == [
        "ep3491801b1",
        "vaswani2017",
        "ep3491801b1_2",
    ]
    assert csl["errors"] == errors

    ris = format_ris(records, errors)  # type: ignore[arg-type]
    types = [line for line in ris.splitlines() if line.startswith("TY  - ")]
    assert types == ["TY  - PAT", "TY  - JOUR", "TY  - PAT"]


def test_family_only_name_and_missing_date() -> None:
    record = ep3491801b1()
    record["inventors"] = {"original": ["DOE,"], "standardised": []}
    del record["publication_date"]
    assert "  author = {DOE}," in patent_bibtex_entry(record, set())
    ris = patent_ris_record(record)
    assert "PY  -" not in ris
    assert "DA  -" not in ris
