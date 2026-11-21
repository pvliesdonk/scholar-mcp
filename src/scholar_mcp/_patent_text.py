"""Markdown for a patent's claims and description (#44).

OPS sends full text as plain ``claim-text`` and ``p`` elements with no
numbering or heading markup of its own; how each office splits them is
recorded in ``docs/design/reference/epo-ops-fulltext.md``. These functions
turn that text into compact Markdown an agent can read and quote directly.
The choices are in ``docs/design/patent-fulltext.md``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

# A claim number where a claim may start: at the start of the text or a line,
# or after the sentence that ends the previous claim. OCR may space the digits
# and the dot ("1 3." for 13, "1 ." for 1). The next word starts upper case.
_CLAIM_START_RE = re.compile(
    r"(?:^|(?<=\n)|(?<=[.;:]\s))[ \t]*(?P<num>\d(?:[ \t]?\d)*)[ \t]?\.[ \t]+(?=[A-Z])"
)
# A WO claim set opens with this line.
_CLAIMS_LABEL_RE = re.compile(r"^\s*claims\s*\n", re.IGNORECASE)
# The paragraph number an EP description writes at the start of a paragraph.
_PARAGRAPH_NUMBER_RE = re.compile(r"^\[(\d{4,5})\]\s*")
_SPACE_RUN_RE = re.compile(r"[ \t]{2,}")
# A heading is short; any longer upper-case paragraph is body text.
_MAX_HEADING_CHARS = 80


def _squeeze(text: str) -> str:
    """Collapse runs of spaces and tabs to one space, line by line.

    Args:
        text: Text from one element.

    Returns:
        The text with each line stripped and inner space runs collapsed.
    """
    lines = (_SPACE_RUN_RE.sub(" ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def _claim_starts(text: str, expected: int) -> Iterator[tuple[int, int, int]]:
    """Find where numbered claims start, in ascending order.

    Only the next number in sequence counts as a claim start, so a reference
    such as "according to claim 1. " further on is not mistaken for one.

    Args:
        text: Claim text that may hold several claims.
        expected: The number the next claim should carry.

    Yields:
        ``(number, start, body_start)`` per claim start: the claim number,
        where its number begins, and where its wording begins.
    """
    for match in _CLAIM_START_RE.finditer(text):
        number = int(re.sub(r"\s", "", match.group("num")))
        if number == expected:
            yield number, match.start("num"), match.end()
            expected += 1


def _split_claims(texts: Sequence[str]) -> list[tuple[int | None, str]]:
    """Split claim text into numbered claims.

    Text before the first numbered claim, or with no number at all, is kept
    as an unnumbered part rather than dropped.

    Args:
        texts: The ``claim-text`` strings of one claim set, in order.

    Returns:
        ``(number, wording)`` per claim; ``number`` is ``None`` for text
        that carries none.
    """
    claims: list[tuple[int | None, str]] = []
    expected = 1
    for raw in texts:
        text = _CLAIMS_LABEL_RE.sub("", raw)
        cursor = 0
        for number, start, body in _claim_starts(text, expected):
            _append_continuation(claims, text[cursor:start])
            claims.append((number, ""))
            cursor = body
            expected = number + 1
        _append_continuation(claims, text[cursor:])
    return [(n, w) for n, w in claims if w]


def _append_continuation(claims: list[tuple[int | None, str]], text: str) -> None:
    """Add text to the claim being built, or as an unnumbered part.

    Args:
        claims: Claims so far; the last one is extended in place.
        text: Text that belongs to the claim before it.
    """
    text = _squeeze(text)
    if not text:
        return
    if claims:
        number, wording = claims[-1]
        claims[-1] = (number, f"{wording}\n{text}" if wording else text)
    else:
        claims.append((None, text))


def claims_markdown(texts: Sequence[str]) -> str:
    """Format a claim set as Markdown, one numbered block per claim.

    A claim continued across several ``claim-text`` elements is rejoined,
    and a claim set sent as one block is split at each claim number.

    Args:
        texts: The ``claim-text`` strings of one claim set, in order.

    Returns:
        ``1. …`` blocks separated by blank lines, or an empty string.
    """
    blocks = [
        f"{number}. {wording}" if number is not None else wording
        for number, wording in _split_claims(texts)
    ]
    return "\n\n".join(blocks)


def _is_heading(paragraph: str) -> bool:
    """Tell a section heading from body text.

    OPS marks no headings; an EP or WO description writes each as a short
    upper-case paragraph of its own ("TECHNICAL FIELD").

    Args:
        paragraph: One squeezed description paragraph.

    Returns:
        True for a short upper-case paragraph with no paragraph number and
        no final full stop.
    """
    if len(paragraph) > _MAX_HEADING_CHARS or paragraph.endswith("."):
        return False
    if _PARAGRAPH_NUMBER_RE.match(paragraph):
        return False
    letters = [c for c in paragraph if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def description_markdown(paragraphs: Sequence[str]) -> str:
    """Format a description as Markdown.

    Upper-case heading paragraphs become ``##`` headings; every other
    paragraph keeps its text, paragraph number included (``[0001] …``), with
    space runs collapsed.

    Args:
        paragraphs: The ``p`` strings of one description, in order.

    Returns:
        Markdown paragraphs separated by blank lines, or an empty string.
    """
    blocks: list[str] = []
    for raw in paragraphs:
        paragraph = _squeeze(raw)
        if not paragraph:
            continue
        blocks.append(f"## {paragraph}" if _is_heading(paragraph) else paragraph)
    return "\n\n".join(blocks)
