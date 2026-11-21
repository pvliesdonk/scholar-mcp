"""Identify the paper a patent's non-patent literature names (#59).

Two routes beyond the DOI. An arXiv identifier in the citation text is exact
and joins the DOI batch. Otherwise the title is guessed from the text and
looked up with Semantic Scholar's title match, whose single best hit is
returned as an unconfirmed ``candidate``: the endpoint always answers with
its closest title, so a generic title such as "Deep learning" matches an
unrelated paper of that name. How the endpoint behaves is in
``docs/design/reference/semantic-scholar-api.md``; the choices are in
``docs/design/patent-npl-resolution.md``.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from ._rate_limiter import RateLimitedError
from ._s2_client import FIELD_SETS

if TYPE_CHECKING:
    from ._record_types import PaperRecord
    from ._s2_client import S2Client

logger = logging.getLogger(__name__)

# A new-style arXiv identifier after a marker: "arXiv:1704.04861",
# "abs/1704.04861", or the DataCite DOI form "10.48550/arXiv.1610.02357".
_ARXIV_RE = re.compile(r"(?:arxiv[:.]\s*|abs/)(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)
_ARXIV_DOI_PREFIX = "10.48550/arxiv."

# EPO appends where a citation was found: "* citation found in description *".
_EPO_NOTE_RE = re.compile(r"\*[^*]*\*\s*$")
_QUOTED_RE = re.compile(r"[\"“„]([^\"“”„]{10,300})[\"”“]")
# "AUTHOR, First ; AUTHOR, First [et al.]: Title. In: …" (German examiner style).
# "In:" introduces the containing work, never the end of the author list.
_AFTER_AUTHORS_RE = re.compile(r"^[^:]{2,200}?(?:\]|[A-Za-z.])(?<!\bIn)\s*:\s+(.+)$")
# "Lee KB, Cheon S (2017) Title; Venue" (short style).
_AFTER_YEAR_RE = re.compile(r"\((?:19|20)\d{2}\)\s*;?\s*(.+)$")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "or",
        "the",
        "to",
        "via",
        "with",
        "using",
    ]
)
_WEB_MARKERS = ("wikipedia", "http://", "https://", "www.")

# A candidate must share this share of significant words with the guess, in
# both directions, so neither a longer nor a shorter title slips through.
_MIN_OVERLAP = 0.8
_MIN_TITLE_WORDS = 3
# A preprint and its publication can be a year apart.
_YEAR_TOLERANCE = 1
# Title lookups spend the S2 budget every client of this server shares.
MAX_TITLE_MATCHES = 10


def extract_arxiv_id(text: str, doi: str | None) -> str | None:
    """Return the arXiv identifier a citation names, or None.

    Args:
        text: Free-text citation.
        doi: The DOI found in it, if any; an arXiv DataCite DOI counts.

    Returns:
        The identifier, such as ``1704.04861``, without its version.
    """
    if doi and doi.lower().startswith(_ARXIV_DOI_PREFIX):
        return doi[len(_ARXIV_DOI_PREFIX) :].split("v")[0]
    match = _ARXIV_RE.search(text)
    return match.group(1) if match else None


def _clean(text: str) -> str:
    """Strip EPO's list dash and trailing location note from a citation.

    Args:
        text: Raw citation string.

    Returns:
        The citation proper.
    """
    text = _EPO_NOTE_RE.sub("", text).strip()
    return text[2:].strip() if text.startswith("- ") else text


def _first_sentence(text: str) -> str:
    """Cut a title off at the first sentence or field break.

    Args:
        text: Text that starts with the title.

    Returns:
        The text up to the first ". ", ";" or ". In:".
    """
    return re.split(r"\.\s|;|\.$", text, maxsplit=1)[0].strip()


def guess_title(raw: str) -> str | None:
    """Guess the title of the work a citation string names.

    Takes a quoted title when there is one; otherwise tries the text after
    the author list (``AUTHORS: Title.``), then the text after a bracketed
    year (``(2017) Title;``).

    Args:
        raw: Raw citation string from EPO.

    Returns:
        The guessed title, or ``None`` when no pattern fits or it is too
        short to look up.
    """
    text = _clean(raw)
    quoted = _QUOTED_RE.search(text)
    # A quoted title is the title: what follows the authors is then the
    # quoted string plus dates and publishers, not a better guess.
    candidates = [quoted.group(1)] if quoted else []
    for pattern in () if quoted else (_AFTER_AUTHORS_RE, _AFTER_YEAR_RE):
        match = pattern.search(text)
        if match:
            candidates.append(_first_sentence(match.group(1)))
    for title in candidates:
        if len(_significant_words(title)) >= _MIN_TITLE_WORDS:
            return title
    return None


def _significant_words(text: str) -> set[str]:
    """Return the lower-case words of a title, without stop words.

    Args:
        text: A title.

    Returns:
        The set of significant words; numbers such as years do not count.
    """
    words = _WORD_RE.findall(text.lower())
    return {w for w in words if w not in _STOPWORDS and not w.isdigit()}


def _plausible(candidate: PaperRecord, title: str, raw: str) -> bool:
    """Check a title-match hit against the citation it should match.

    Args:
        candidate: The paper Semantic Scholar matched.
        title: The guessed title.
        raw: The raw citation string.

    Returns:
        True when the titles share most significant words both ways and,
        if the citation names years, the paper's year is within a year of one.
    """
    guessed = _significant_words(title)
    found = _significant_words(candidate.get("title") or "")
    if not guessed or not found:
        return False
    shared = len(guessed & found)
    if shared / len(guessed) < _MIN_OVERLAP or shared / len(found) < _MIN_OVERLAP:
        return False
    years = [int(y) for y in _YEAR_RE.findall(raw)]
    year = candidate.get("year")
    if years and year is not None:
        return any(abs(year - y) <= _YEAR_TOLERANCE for y in years)
    return True


def _wants_title_match(entry: dict[str, Any]) -> bool:
    """Say whether an NPL entry should be looked up by title.

    Args:
        entry: A resolved NPL entry.

    Returns:
        True when nothing identified it and it does not look like a web page.
    """
    if any(k in entry for k in ("paper", "book", "isbn", "doi")):
        return False
    raw = entry["raw"].lower()
    return not any(marker in raw for marker in _WEB_MARKERS)


async def attach_title_candidates(
    entries: list[dict[str, Any]], s2: S2Client, patent_id: str
) -> None:
    """Attach an unconfirmed title-match candidate to unidentified NPL entries.

    A plausible hit is added as ``candidate`` with ``confidence:
    "unconfirmed"`` and ``match: "title"``, never as ``paper``. Lookups run
    one at a time, at most :data:`MAX_TITLE_MATCHES` per call, and stop at
    the first rate limit or failure, leaving the remaining entries as they
    are.

    Args:
        entries: Resolved NPL entries, changed in place.
        s2: Semantic Scholar client.
        patent_id: Patent the references are cited by, for the log.
    """
    pending = [e for e in entries if _wants_title_match(e)]
    looked_up = 0
    for entry in pending:
        title = guess_title(entry["raw"])
        if title is None:
            continue
        if looked_up == MAX_TITLE_MATCHES:
            logger.info("npl_title_match_capped patent=%s", patent_id)
            return
        looked_up += 1
        try:
            candidate = await s2.match_title(title, fields=FIELD_SETS["compact"])
        except RateLimitedError:
            logger.info("npl_title_match_rate_limited patent=%s", patent_id)
            return
        except Exception:
            # Best-effort like the DOI batch: a failing S2 leaves the
            # remaining references as they are rather than failing the call.
            logger.warning("npl_title_match_failed patent=%s", patent_id, exc_info=True)
            return
        if candidate is not None and _plausible(candidate, title, entry["raw"]):
            entry["candidate"] = candidate
            entry["confidence"] = "unconfirmed"
            entry["match"] = "title"
