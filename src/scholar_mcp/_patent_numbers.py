"""Patent number normalization and detection.

Converts various patent number formats to DOCDB format (CC.number.kind)
for use as EPO OPS API inputs and cache keys.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATENT_RE = re.compile(
    r"^(?P<country>[A-Za-z]{2})"
    r"[\s.]*"
    r"(?P<number>[\d,/]+)"
    r"[\s.]*"
    r"(?P<kind>[A-Za-z]\d{0,2})?$"
)

_PATENT_COUNTRIES = frozenset(
    {
        "EP",
        "WO",
        "US",
        "JP",
        "CN",
        "KR",
        "DE",
        "FR",
        "GB",
        "CA",
        "AU",
        "IN",
        "BR",
        "RU",
        "TW",
        "IL",
        "NZ",
        "SG",
        "HK",
        "AT",
        "BE",
        "CH",
        "CZ",
        "DK",
        "ES",
        "FI",
        "GR",
        "HU",
        "IE",
        "IT",
        "LU",
        "NL",
        "NO",
        "PL",
        "PT",
        "SE",
        "SK",
        "TR",
    }
)


@dataclass(frozen=True)
class DocdbNumber:
    """A patent number in DOCDB format (country.number.kind).

    Attributes:
        country: Two-letter country/authority code (e.g. "EP", "US").
        number:  Numeric portion of the patent number, no punctuation.
        kind:    Kind code (e.g. "A1", "B2"); empty string when absent.
    """

    country: str
    number: str
    kind: str

    @property
    def docdb(self) -> str:
        """Return the DOCDB-formatted string ``CC.number.kind``.

        Returns:
            Dotted DOCDB representation. When kind is absent the trailing
            segment is still included as an empty field (``CC.number.``).
        """
        if self.kind:
            return f"{self.country}.{self.number}.{self.kind}"
        return f"{self.country}.{self.number}."

    def __str__(self) -> str:
        return self.docdb


def normalize(raw: str) -> DocdbNumber:
    """Parse a patent number string into DOCDB format.

    Accepts a variety of common input formats and normalises them to a
    ``DocdbNumber`` instance whose ``.docdb`` property renders as the
    canonical ``CC.number.kind`` string used by the EPO OPS API.

    Supported formats (non-exhaustive):
        - ``EP1234567A1``  — concatenated, no separators
        - ``EP 1234567 A1`` — space-separated
        - ``EP.1234567.A1`` — DOCDB dot-separated (pass-through)
        - ``WO2024/123456A1`` — WO slash notation (slash is stripped)
        - ``US11,234,567B2`` — US comma-grouped number (commas stripped)
        - ``ep1234567A1`` — lowercase country code (uppercased)
        - ``EP1234567`` — no kind code

    Args:
        raw: Raw patent number string in any supported format.

    Returns:
        Normalised ``DocdbNumber``.

    Raises:
        ValueError: If *raw* is empty or does not match any known format.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("Cannot parse empty string as patent number")
    m = _PATENT_RE.match(raw)
    if m is None:
        raise ValueError(f"Cannot parse patent number: {raw!r}")
    country = m.group("country").upper()
    number = m.group("number").replace(",", "").replace("/", "")
    if not number:
        raise ValueError(f"Patent number has no numeric portion: {raw!r}")
    kind = m.group("kind") or ""
    return DocdbNumber(country=country, number=number, kind=kind)


def is_patent_number(raw: str) -> bool:
    """Heuristic check for whether a string looks like a patent number.

    Used by ``batch_resolve`` to auto-detect patent numbers versus paper
    identifiers (DOIs, S2 IDs, arXiv IDs, etc.).

    The check is intentionally lightweight: the string must start with a
    recognised two-letter patent authority code followed immediately by a
    digit (after stripping a leading space or dot).

    Args:
        raw: Candidate identifier string.

    Returns:
        ``True`` if *raw* appears to be a patent number, ``False``
        otherwise.
    """
    raw = raw.strip()
    if len(raw) < 4:
        return False
    prefix = raw[:2].upper()
    if prefix not in _PATENT_COUNTRIES:
        return False
    rest = raw[2:].lstrip(" .")
    return len(rest) > 0 and rest[0].isdigit()
