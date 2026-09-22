"""Bound large text fields for MCP responses."""

from __future__ import annotations

from typing import Any

DEFAULT_MAX_TEXT_CHARS = 20_000
"""Default and largest bounded page returned from a document tool."""


def page_text(
    result: dict[str, Any],
    field: str,
    *,
    text_offset: int,
    max_chars: int | None,
) -> dict[str, Any]:
    """Return one page of a text field plus navigation metadata.

    A ``None`` limit explicitly preserves the complete-response behavior for
    clients that can accept it. Integer limits are clamped to the server's
    safe page size, and negative offsets start at the beginning.

    Args:
        result: Tool result that may contain a text field.
        field: Name of the text field to page.
        text_offset: Character offset at which the page starts.
        max_chars: Requested page size, or ``None`` for the complete tail.

    Returns:
        A copy containing the requested text page and pagination metadata, or
        the original mapping when *field* is absent or is not text.
    """
    text = result.get(field)
    if not isinstance(text, str):
        return result

    total = len(text)
    offset = min(max(text_offset, 0), total)
    if max_chars is None:
        end = total
    else:
        limit = max(1, min(max_chars, DEFAULT_MAX_TEXT_CHARS))
        end = min(offset + limit, total)

    paged = {
        **result,
        field: text[offset:end],
        "text_offset": offset,
        "text_returned_chars": end - offset,
        "text_total_chars": total,
        "text_truncated": offset > 0 or end < total,
    }
    if end < total:
        paged["next_offset"] = end
    return paged
