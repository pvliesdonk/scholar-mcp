"""Book chapters in generate_citations output (#593).

Each record carries the ``chapter_info`` the CrossRef chapter enricher maps
from the fixtures in :mod:`tests.fixtures.crossref_chapters`.
"""

from __future__ import annotations

import json
from typing import Any

from scholar_mcp._citation_formatter import (
    format_bibtex,
    format_csl_json,
    format_ris,
    infer_entry_type,
)
from tests.fixtures.chapter_papers import (
    cambridge_paper,
    elsevier_paper,
    ieee_paper,
    lncs_paper,
    springer_paper,
    with_chapter_info,
)
from tests.fixtures.crossref_chapters import (
    cambridge_chapter,
    cambridge_parent,
    elsevier_chapter,
    ieee_chapter,
    springer_chapter,
    springer_parent,
)


def _springer() -> Any:
    return with_chapter_info(springer_paper(), springer_chapter(), springer_parent())


def _csl(paper: Any) -> dict[str, Any]:
    data = json.loads(format_csl_json([paper], []))
    return data["citations"][0]  # type: ignore[no-any-return]


class TestEntryType:
    def test_crossref_chapter_is_incollection(self) -> None:
        assert infer_entry_type(_springer()) == "incollection"

    def test_chapter_outranks_book_metadata(self) -> None:
        paper = _springer()
        paper["book_metadata"] = {"isbn_13": "9783031932748", "publisher": "X"}
        assert infer_entry_type(paper) == "incollection"

    def test_conference_paper_stays_inproceedings(self) -> None:
        """LNCS papers are CrossRef book-chapters; S2's conference flag wins."""
        paper = with_chapter_info(lncs_paper(), springer_chapter())
        assert infer_entry_type(paper) == "inproceedings"

    def test_chapter_without_book_title_is_not_a_chapter(self) -> None:
        paper = springer_paper()
        paper["chapter_info"] = {"citation_source": "crossref", "pages": "1-2"}
        assert infer_entry_type(paper) == "article"

    def test_parsed_chapter_info_is_not_used(self) -> None:
        paper = springer_paper()
        paper["chapter_info"] = {"citation_source": "parsed", "parent_title": "B"}
        assert infer_entry_type(paper) == "article"

    def test_without_enrichment_a_chapter_is_inferred_as_before(self) -> None:
        assert infer_entry_type(springer_paper()) == "article"


class TestBibtex:
    def test_full_chapter(self) -> None:
        result = format_bibtex([_springer()], [])
        assert result.startswith("@incollection{silva2025,\n")
        assert "  author = {Silva, Ana}" in result
        assert "  title = {{Heritage Trails and Local Economies}}" in result
        assert "  year = {2025}" in result
        assert (
            "  booktitle = {Cultural Heritage-Based Sustainable Tourism "
            "Approaches: Case Studies from the Mediterranean}"
        ) in result
        assert "  editor = {Rossi, Maria and de Vries, Jan}" in result
        assert "  pages = {15-32}" in result
        assert "  publisher = {Springer Nature Switzerland}" in result
        assert "  address = {Cham}" in result
        assert "  edition = {1}" in result
        assert "  isbn = {9783031932748}" in result
        assert "  doi = {10.1007/978-3-031-93275-5\\_2}" in result
        assert "journal" not in result

    def test_series_title_is_not_the_booktitle(self) -> None:
        result = format_bibtex([_springer()], [])
        assert "Advances in Science" not in result

    def test_no_author_no_editor_still_a_chapter(self) -> None:
        paper = with_chapter_info(ieee_paper(), ieee_chapter())
        result = format_bibtex([paper], [])
        assert result.startswith("@incollection{anon,\n")
        assert "author" not in result
        assert "editor" not in result
        assert "pages" not in result
        assert "year" not in result
        assert "  booktitle = {Wireless Systems Handbook}" in result
        assert "  publisher = {IEEE}" in result

    def test_editor_without_author(self) -> None:
        paper = with_chapter_info(
            cambridge_paper(), cambridge_chapter(), cambridge_parent()
        )
        result = format_bibtex([paper], [])
        assert "author" not in result
        assert "  editor = {Clark, Helen}" in result
        assert "  pages = {xiii-xiii}" in result
        assert "  edition = {2}" in result
        assert "address" not in result

    def test_nonnumeric_pages_kept_as_given(self) -> None:
        paper = with_chapter_info(elsevier_paper(), elsevier_chapter())
        result = format_bibtex([paper], [])
        assert "  pages = {639-650.e3}" in result
        assert "editor" not in result

    def test_booktitle_is_escaped(self) -> None:
        paper = _springer()
        paper["chapter_info"]["parent_title"] = "Law & Order"
        assert "  booktitle = {Law \\& Order}" in format_bibtex([paper], [])


class TestCslJson:
    def test_full_chapter(self) -> None:
        entry = _csl(_springer())
        assert entry["type"] == "chapter"
        assert entry["title"] == "Heritage Trails and Local Economies"
        assert entry["container-title"] == (
            "Cultural Heritage-Based Sustainable Tourism Approaches: "
            "Case Studies from the Mediterranean"
        )
        assert entry["editor"] == [
            {"family": "Rossi", "given": "Maria"},
            {"family": "Vries", "given": "Jan", "non-dropping-particle": "de"},
        ]
        assert entry["page"] == "15-32"
        assert entry["publisher"] == "Springer Nature Switzerland"
        assert entry["publisher-place"] == "Cham"
        assert entry["edition"] == "1"
        assert entry["ISBN"] == "9783031932748"
        assert entry["DOI"] == "10.1007/978-3-031-93275-5_2"

    def test_no_author_no_editor(self) -> None:
        entry = _csl(with_chapter_info(ieee_paper(), ieee_chapter()))
        assert entry["type"] == "chapter"
        assert "author" not in entry
        assert "editor" not in entry
        assert "page" not in entry
        assert "issued" not in entry
        assert entry["container-title"] == "Wireless Systems Handbook"


class TestRis:
    def test_full_chapter(self) -> None:
        result = format_ris([_springer()], [])
        lines = result.splitlines()
        assert lines[0] == "TY  - CHAP"
        assert "AU  - Silva, Ana" in lines
        assert "TI  - Heritage Trails and Local Economies" in lines
        assert (
            "T2  - Cultural Heritage-Based Sustainable Tourism Approaches: "
            "Case Studies from the Mediterranean"
        ) in lines
        assert "A2  - Rossi, Maria" in lines
        assert "A2  - de Vries, Jan" in lines
        assert "SP  - 15" in lines
        assert "EP  - 32" in lines
        assert "PB  - Springer Nature Switzerland" in lines
        assert "CY  - Cham" in lines
        assert "ET  - 1" in lines
        assert "SN  - 9783031932748" in lines
        assert not any(line.startswith(("JO  -", "BT  -")) for line in lines)
        assert lines[-1] == "ER  -"

    def test_roman_range_is_split(self) -> None:
        paper = with_chapter_info(
            cambridge_paper(), cambridge_chapter(), cambridge_parent()
        )
        lines = format_ris([paper], []).splitlines()
        assert "SP  - xiii" in lines
        assert "EP  - xiii" in lines
        assert not any(line.startswith("AU  -") for line in lines)

    def test_two_part_range_with_suffix_is_split(self) -> None:
        paper = with_chapter_info(elsevier_paper(), elsevier_chapter())
        lines = format_ris([paper], []).splitlines()
        assert "SP  - 639" in lines
        assert "EP  - 650.e3" in lines

    def test_ambiguous_range_goes_whole_into_sp(self) -> None:
        paper = _springer()
        info = paper["chapter_info"]
        info["pages"] = "P3-660-P3-660"
        info.pop("page_start")
        info.pop("page_end")
        lines = format_ris([paper], []).splitlines()
        assert "SP  - P3-660-P3-660" in lines
        assert not any(line.startswith("EP  -") for line in lines)

    def test_no_pages_no_editor(self) -> None:
        paper = with_chapter_info(ieee_paper(), ieee_chapter())
        lines = format_ris([paper], []).splitlines()
        assert lines[0] == "TY  - CHAP"
        assert not any(line.startswith(("SP", "EP", "A2", "AU")) for line in lines)
        assert "T2  - Wireless Systems Handbook" in lines
