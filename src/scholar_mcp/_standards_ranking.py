"""Order standards search results so the current edition comes first (#487).

Every search source matches by substring and used to return its first
matches in storage order, so a query naming a standard without its revision
or year could list replaced editions and companion documents ahead of the
current one, or leave the current one out at a small ``limit``.

The order, most significant first:

1. An identifier equal to the query. A caller who names an edition exactly,
   replaced or not, gets that edition.
2. A match in the identifier before a match in the title only. Status alone
   would put any published document that names the standard in its title
   (ISO/IEC 27013, an integration guide for ISO/IEC 27001) above the
   standard's own replaced editions.
3. Status: published, then draft, then superseded, then withdrawn.
4. How the query sits in the identifier: as the whole document number before
   part of a longer one (``800-53`` in ``800-53A``) or of an amendment,
   corrigendum or consolidated version (anything after a ``/`` or ``+``).
5. Publication date, newest first, undated last.
6. Identifier, for a deterministic order.

Where each source applies it: ``docs/design/standards-search-ranking.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ._record_types import StandardRecord

# Statuses the normalisers emit; anything else sits with draft.
_STATUS_RANK = {"published": 0, "draft": 1, "superseded": 2, "withdrawn": 3}
_UNKNOWN_STATUS_RANK = 1

# Match ranks, see the module docstring.
_WHOLE_NUMBER = 0
_PART_OF_IDENTIFIER = 1
_TITLE_ONLY = 2


def _status_rank(status: str | None) -> int:
    """Return where a status sorts: lower means more current.

    Args:
        status: A record's ``status``.

    Returns:
        0 for published, 1 for draft or unknown, 2 for superseded and 3 for
        withdrawn.
    """
    return _STATUS_RANK.get(status or "", _UNKNOWN_STATUS_RANK)


def _match_rank(identifier: str, query: str) -> int:
    """Rate how the query sits in an identifier, both lower-cased.

    Args:
        identifier: The record's identifier.
        query: The search query.

    Returns:
        One of the module's match ranks.
    """
    position = identifier.find(query)
    if position < 0:
        return _TITLE_ONLY
    before = identifier[position - 1] if position else " "
    rest = identifier[position + len(query) :]
    inside_a_longer_number = before.isalnum() or (rest[:1].isalnum())
    if inside_a_longer_number or "/" in rest or "+" in rest:
        return _PART_OF_IDENTIFIER
    return _WHOLE_NUMBER


def rank_standards(
    records: Iterable[StandardRecord], query: str
) -> list[StandardRecord]:
    """Return search results in ranked order, the current edition first.

    Args:
        records: The matches, in any order.
        query: The query they matched.

    Returns:
        The same records, ordered as the module docstring describes.
    """
    wanted = query.strip().lower()

    def key(record: StandardRecord) -> tuple[bool, bool, int, int]:
        identifier = (record.get("identifier") or "").lower()
        match = _match_rank(identifier, wanted)
        return (
            identifier != wanted,
            match == _TITLE_ONLY,
            _status_rank(record.get("status")),
            match,
        )

    # Python's sort is stable, so sorting by the least significant key first
    # leaves each earlier order in place among records the later keys tie.
    ranked = sorted(records, key=lambda r: r.get("identifier") or "")
    ranked.sort(key=lambda r: r.get("published_date") or "", reverse=True)
    ranked.sort(key=key)
    return ranked
