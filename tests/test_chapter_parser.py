"""Tests for chapter citation parser."""

from __future__ import annotations

from scholar_mcp._chapter_parser import parse_chapter_hint


class TestChapterNumber:
    def test_chapter_number_pattern(self) -> None:
        hint = parse_chapter_hint("Goodfellow et al., Deep Learning, Chapter 3")
        assert hint.chapter_number == 3

    def test_ch_abbreviation(self) -> None:
        hint = parse_chapter_hint("Neural Networks, Ch. 12, pp. 200-220")
        assert hint.chapter_number == 12

    def test_chap_abbreviation(self) -> None:
        hint = parse_chapter_hint("Introduction to ML, Chap. 5")
        assert hint.chapter_number == 5


class TestPageRanges:
    def test_page_range_pp(self) -> None:
        hint = parse_chapter_hint("Some Book, pp. 45-67")
        assert hint.page_start == 45
        assert hint.page_end == 67

    def test_single_page(self) -> None:
        hint = parse_chapter_hint("A paper, p. 123")
        assert hint.page_start == 123
        assert hint.page_end is None

    def test_pages_keyword(self) -> None:
        # en-dash U+2013
        hint = parse_chapter_hint("A chapter, pages 100\u2013150")
        assert hint.page_start == 100
        assert hint.page_end == 150

    def test_pages_with_em_dash(self) -> None:
        # em-dash U+2014
        hint = parse_chapter_hint("A chapter, pages 200\u2014250")
        assert hint.page_start == 200
        assert hint.page_end == 250


class TestParentTitle:
    def test_in_book_title(self) -> None:
        hint = parse_chapter_hint("Smith, 'Neural Networks', In: Handbook of AI, 2020")
        assert hint.parent_title == "Handbook of AI"

    def test_in_book_title_no_year(self) -> None:
        hint = parse_chapter_hint("In: Encyclopedia of Computer Science")
        assert hint.parent_title == "Encyclopedia of Computer Science"


class TestIsbn:
    def test_isbn_extraction(self) -> None:
        hint = parse_chapter_hint(
            "Goodfellow et al., Deep Learning, Ch. 3, pp. 45-67, ISBN 978-0-262-03561-3"
        )
        assert hint.isbn == "9780262035613"

    def test_isbn10_extraction(self) -> None:
        hint = parse_chapter_hint("Some Book, ISBN 0-262-03561-8")
        assert hint.isbn is not None

    def test_isbn13_no_hyphens(self) -> None:
        hint = parse_chapter_hint("A Book ISBN 9780262035613")
        assert hint.isbn == "9780262035613"


class TestEmptyAndProperties:
    def test_no_match_returns_empty_hint(self) -> None:
        hint = parse_chapter_hint("Goodfellow et al., 2016")
        assert hint.chapter_number is None
        assert hint.page_start is None
        assert hint.page_end is None
        assert hint.parent_title is None
        assert hint.isbn is None

    def test_has_chapter_info_empty(self) -> None:
        hint = parse_chapter_hint("Goodfellow et al., 2016")
        assert hint.has_chapter_info is False

    def test_has_chapter_info_with_chapter(self) -> None:
        hint = parse_chapter_hint("Deep Learning, Chapter 3")
        assert hint.has_chapter_info is True

    def test_has_chapter_info_with_pages(self) -> None:
        hint = parse_chapter_hint("Some Book, pp. 45-67")
        assert hint.has_chapter_info is True

    def test_has_chapter_info_with_isbn(self) -> None:
        hint = parse_chapter_hint("Some Book, ISBN 978-0-262-03561-3")
        assert hint.has_chapter_info is True
