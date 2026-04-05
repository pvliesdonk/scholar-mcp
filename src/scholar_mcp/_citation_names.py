"""Author name parsing for citation formatting."""

from __future__ import annotations

from typing import NamedTuple

_PREFIXES = frozenset(
    {
        "van",
        "von",
        "de",
        "del",
        "della",
        "di",
        "du",
        "el",
        "la",
        "le",
        "den",
        "der",
        "het",
        "ten",
        "ter",
        "dos",
        "das",
        "al",
    }
)

_SUFFIXES = frozenset(
    {
        "jr",
        "jr.",
        "sr",
        "sr.",
        "ii",
        "iii",
        "iv",
        "v",
    }
)


class AuthorName(NamedTuple):
    """Parsed author name components."""

    first: str
    last: str
    prefix: str
    suffix: str


def parse_author_name(name: str) -> AuthorName:
    """Parse an author name string into structured components.

    Handles prefixes (van, de, von, ...), suffixes (Jr., III, ...),
    hyphenated first names, and single-word names.

    Args:
        name: Full author name as a single string (e.g. "Jan van Houten").

    Returns:
        Parsed AuthorName with first, last, prefix, and suffix fields.
    """
    if not name or not name.strip():
        return AuthorName(first="", last="", prefix="", suffix="")

    parts = name.strip().split()

    if len(parts) == 1:
        return AuthorName(first="", last=parts[0], prefix="", suffix="")

    # Extract suffix from the end.
    suffix = ""
    if parts[-1].lower().rstrip(".") in {s.rstrip(".") for s in _SUFFIXES}:
        suffix = parts.pop()

    if len(parts) == 1:
        return AuthorName(first="", last=parts[0], prefix="", suffix=suffix)

    # The last remaining token is the surname.
    last = parts.pop()

    # Scan remaining tokens for prefix particles.
    first_parts: list[str] = []
    prefix_parts: list[str] = []

    # Walk from the end of remaining parts backward to find prefix.
    i = len(parts) - 1
    while i >= 0 and parts[i].lower() in _PREFIXES:
        prefix_parts.insert(0, parts[i])
        i -= 1

    first_parts = parts[: i + 1]

    # If everything got consumed as prefix, the first prefix token is
    # actually part of the given name.
    if not first_parts and prefix_parts:
        first_parts = [prefix_parts.pop(0)]

    return AuthorName(
        first=" ".join(first_parts),
        last=last,
        prefix=" ".join(prefix_parts),
        suffix=suffix,
    )
