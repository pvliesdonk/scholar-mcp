"""Tests for bounded document text responses."""

from scholar_mcp._text_window import DEFAULT_MAX_TEXT_CHARS, page_text


def test_page_text_bounds_default_response_and_points_to_next_page() -> None:
    text = "x" * (DEFAULT_MAX_TEXT_CHARS + 17)

    result = page_text(
        {"markdown": text},
        "markdown",
        text_offset=0,
        max_chars=DEFAULT_MAX_TEXT_CHARS + 1_000,
    )

    assert len(result["markdown"]) == DEFAULT_MAX_TEXT_CHARS
    assert result["text_offset"] == 0
    assert result["text_returned_chars"] == DEFAULT_MAX_TEXT_CHARS
    assert result["text_total_chars"] == len(text)
    assert result["text_truncated"] is True
    assert result["next_offset"] == DEFAULT_MAX_TEXT_CHARS


def test_page_text_returns_final_page_without_next_offset() -> None:
    text = "abcdefgh"

    result = page_text({"full_text": text}, "full_text", text_offset=3, max_chars=100)

    assert result["full_text"] == "defgh"
    assert result["text_offset"] == 3
    assert result["text_returned_chars"] == 5
    assert result["text_total_chars"] == 8
    assert result["text_truncated"] is True
    assert "next_offset" not in result


def test_page_text_null_limit_preserves_complete_response() -> None:
    result = page_text(
        {"markdown": "complete"}, "markdown", text_offset=-10, max_chars=None
    )

    assert result["markdown"] == "complete"
    assert result["text_offset"] == 0
    assert result["text_truncated"] is False
    assert "next_offset" not in result


def test_page_text_leaves_results_without_text_unchanged() -> None:
    result = {"error": "conversion_failed"}

    assert page_text(result, "markdown", text_offset=0, max_chars=10) is result
