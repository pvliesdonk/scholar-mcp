"""Tests for chapter citation parser."""

from __future__ import annotations

from scholar_mcp._chapter_parser import ChapterHint, hint_to_dict, parse_chapter_hint


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


class TestIsbnRequiresCheckDigit:
    """Only a number with a valid check digit is an ISBN (#737)."""

    # Real NPL strings from the issue: a page range and a Wikipedia revision id.
    PAGE_RANGE = (
        "OUBBATI, Omar Sami [et al.]: A survey. In: IEEE Access, Vol. 7, 2019,"
        " S. 81057-81105."
    )
    REVISION_ID = (
        "Bump mapping. In: Wikipedia, https://en.wikipedia.org/w/"
        "index.php?title=Bump_mapping&amp;oldid=1195304739"
    )

    def test_page_range_is_not_an_isbn(self) -> None:
        hint = parse_chapter_hint(self.PAGE_RANGE)
        assert hint.isbn is None
        assert "isbn" not in hint_to_dict(hint)

    def test_revision_id_is_not_an_isbn(self) -> None:
        hint = parse_chapter_hint(self.REVISION_ID)
        assert hint.isbn is None
        assert hint.has_chapter_info is False

    def test_isbn10_with_marker_and_hyphens(self) -> None:
        hint = parse_chapter_hint("Proc. IEEE, 1998, ISBN 0-7803-4455-3")
        assert hint.isbn == "0780344553"

    def test_isbn10_without_marker(self) -> None:
        hint = parse_chapter_hint("Proc. IEEE, 1998, 0-7803-4455-3")
        assert hint.isbn == "0780344553"

    def test_isbn13_with_marker_and_hyphens(self) -> None:
        hint = parse_chapter_hint("Kap. 1, S. 1-44. ISBN 978-3-540-52155-6")
        assert hint.isbn == "9783540521556"

    def test_isbn13_without_marker(self) -> None:
        hint = parse_chapter_hint("Kap. 1, S. 1-44. 978-3-540-52155-6")
        assert hint.isbn == "9783540521556"

    def test_isbn10_with_bad_check_digit_is_rejected(self) -> None:
        hint = parse_chapter_hint("Some Book, ISBN 0-7803-4455-4")
        assert hint.isbn is None

    def test_isbn13_with_bad_check_digit_is_rejected(self) -> None:
        hint = parse_chapter_hint("Some Book, ISBN 978-3-540-52155-7")
        assert hint.isbn is None

    def test_valid_isbn_after_a_false_match_is_found(self) -> None:
        hint = parse_chapter_hint(
            "In: IEEE Access, 2019, S. 81057-81105, ISBN 0-7803-4455-3"
        )
        assert hint.isbn == "0780344553"

    def test_valid_isbn13_after_a_false_isbn13_is_found(self) -> None:
        hint = parse_chapter_hint("Ref 978-1-234-56789-0, ISBN 978-3-540-52155-6")
        assert hint.isbn == "9783540521556"

    def test_tail_of_an_invalid_isbn13_is_not_an_isbn10(self) -> None:
        # 978-0-7803-4455-3 fails the ISBN-13 check; its tail
        # 0-7803-4455-3 is a valid ISBN-10 but not a separate number.
        hint = parse_chapter_hint("Some Book, ISBN 978-0-7803-4455-3")
        assert hint.isbn is None

    def test_tail_of_an_invalid_spaced_isbn13_is_not_an_isbn10(self) -> None:
        hint = parse_chapter_hint("Some Book, ISBN 978 0 7803 4455 3")
        assert hint.isbn is None


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


class TestHintToDict:
    def test_hint_to_dict(self) -> None:
        hint = ChapterHint(
            chapter_number=3,
            page_start=45,
            page_end=67,
            parent_title="Deep Learning",
            isbn="9780262035613",
        )
        info = hint_to_dict(hint)
        assert info == {
            "citation_source": "parsed",
            "chapter_number": 3,
            "page_start": 45,
            "page_end": 67,
            "parent_title": "Deep Learning",
            "isbn": "9780262035613",
        }

    def test_hint_to_dict_partial(self) -> None:
        hint = ChapterHint(page_start=100)
        info = hint_to_dict(hint)
        assert info == {"citation_source": "parsed", "page_start": 100}

    def test_hint_to_dict_includes_isbn_when_present(self) -> None:
        hint = ChapterHint(page_start=100, isbn="9780262035613")
        info = hint_to_dict(hint)
        assert info["isbn"] == "9780262035613"
