"""Resolve a patent's non-patent literature references to papers and books.

``get_patent``'s citations section caches only the raw EPO citations; this
pipeline reruns on every call, so it reflects the current paper and book
indexes. The steps and their reasons are in
``docs/design/patent-npl-resolution.md``.
"""

from __future__ import annotations

import asyncio as _asyncio
import logging
from typing import TYPE_CHECKING, Any

from ._cache import checked_isbn13
from ._chapter_parser import hint_to_dict, parse_chapter_hint
from ._epo_xml import extract_doi
from ._npl_titles import attach_title_candidates, extract_arxiv_id
from ._rate_limiter import RateLimitedError, S2RetryDeadlineExceeded
from ._s2_client import FIELD_SETS

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from ._record_types import BookRecord, PaperRecord
    from ._s2_client import S2Client

    # Looks a book up by ISBN; None when no record is found.
    BookResolver = Callable[[str], Awaitable[BookRecord | None]]

logger = logging.getLogger(__name__)


def _npl_s2_id(raw: str, doi: str | None) -> str | None:
    """Return the Semantic Scholar identifier an NPL reference names, if any.

    An arXiv identifier wins over an arXiv DataCite DOI (``10.48550/arXiv.…``),
    which S2 resolves less reliably than the arXiv ID itself; any other DOI
    wins over an arXiv identifier (#59).

    Args:
        raw: Raw citation string.
        doi: The DOI extracted from it, or ``None``.

    Returns:
        ``DOI:…`` or ``ARXIV:…``, or ``None``.
    """
    arxiv = extract_arxiv_id(raw, doi)
    if doi and not (arxiv and doi.lower().startswith("10.48550/")):
        return f"DOI:{doi}"
    return f"ARXIV:{arxiv}" if arxiv else None


def _attach_npl_chapter_info(entry: dict[str, Any], raw: str) -> None:
    """Attach ``chapter_info`` to an NPL *entry* when hints are found.

    Parses the raw citation string for chapter-level hints and, if any
    are present, adds a ``chapter_info`` dict with ``citation_source``
    set to ``"parsed"``.

    Args:
        entry: Mutable NPL entry dict to enrich in-place.
        raw: Raw citation string from the patent NPL reference.
    """
    hint = parse_chapter_hint(raw)
    if not hint.has_chapter_info:
        return
    entry["chapter_info"] = hint_to_dict(hint)


async def _resolve_identified(
    npl_refs: Sequence[dict[str, Any]], s2: S2Client, patent_id: str
) -> dict[int, PaperRecord | None]:
    """Resolve the references that name a DOI or arXiv ID, in one S2 batch.

    A throttle or an exhausted retry deadline propagates, so the tool can
    defer; any other failure is logged and leaves every reference unresolved.

    Args:
        npl_refs: The raw NPL references, each with ``raw``.
        s2: Semantic Scholar client.
        patent_id: Patent the references are cited by, for the log.

    Returns:
        Reference position to paper (``None`` where S2 had none), for the
        references that named an identifier.
    """
    # The DOI is read from the raw text again rather than from the parsed
    # ``doi``: citations cached before #482 stored None for the doi.org and
    # "DOI 10." forms.
    positions: list[int] = []
    ids: list[str] = []
    for i, npl in enumerate(npl_refs):
        s2_id = _npl_s2_id(npl["raw"], extract_doi(npl["raw"]))
        if s2_id:
            positions.append(i)
            ids.append(s2_id)
    if not ids:
        return {}
    try:
        papers = await s2.batch_resolve(ids, fields=FIELD_SETS["compact"])
    except (RateLimitedError, S2RetryDeadlineExceeded):
        raise
    except Exception:
        logger.warning("npl_resolution_failed patent=%s", patent_id)
        papers = [None] * len(ids)
    return dict(zip(positions, papers, strict=True))


def _npl_entry(raw: str, doi: str | None, paper: PaperRecord | None) -> dict[str, Any]:
    """Build one NPL entry from what the identifier lookup found.

    Args:
        raw: Raw citation string.
        doi: The DOI in it, kept when no paper was found for it.
        paper: The paper S2 resolved, or ``None``.

    Returns:
        ``{"raw", "paper", "confidence": "high"}`` for a resolved paper,
        else ``{"raw", ["doi",] "confidence": None}``, with ``chapter_info``
        when the text names a chapter.
    """
    entry: dict[str, Any] = {"raw": raw}
    if paper is not None:
        entry["paper"] = paper
        entry["confidence"] = "high"
    else:
        if doi:
            entry["doi"] = doi
        entry["confidence"] = None
    _attach_npl_chapter_info(entry, raw)
    return entry


async def _lookup_npl_book(
    resolve_book: BookResolver, isbn: str, patent_id: str
) -> BookRecord | None:
    """Resolve one cited book, treating any failure as not found.

    Book resolution is best-effort, like the DOI lookup: a failing Open
    Library leaves the reference with its ISBN rather than failing the call.

    Args:
        resolve_book: ISBN lookup.
        isbn: Validated ISBN-13.
        patent_id: Patent the reference is cited by, for the log.

    Returns:
        The book record, or ``None``.
    """
    try:
        return await resolve_book(isbn)
    except Exception:
        logger.warning(
            "npl_book_resolution_failed patent=%s isbn=%s",
            patent_id,
            isbn,
            exc_info=True,
        )
        return None


async def _attach_npl_books(
    entries: list[dict[str, Any]], resolve_book: BookResolver, patent_id: str
) -> None:
    """Attach the cited book to NPL references that carry a valid ISBN (#70).

    Only references no paper was found for are tried. A found book is added
    as ``book`` with ``confidence: "high"``; otherwise the reference keeps
    its validated ``isbn`` so a caller can look it up elsewhere.

    Args:
        entries: Resolved NPL entries, changed in place.
        resolve_book: ISBN lookup.
        patent_id: Patent the references are cited by, for the log.
    """
    pending: list[tuple[dict[str, Any], str]] = []
    for entry in entries:
        isbn = checked_isbn13((entry.get("chapter_info") or {}).get("isbn") or "")
        if isbn is not None and "paper" not in entry:
            pending.append((entry, isbn))
    books = await _asyncio.gather(
        *(_lookup_npl_book(resolve_book, isbn, patent_id) for _, isbn in pending)
    )
    for (entry, isbn), book in zip(pending, books, strict=True):
        if book is None:
            entry["isbn"] = isbn
        else:
            entry["book"] = book
            entry["confidence"] = "high"


async def resolve_npl_refs(
    npl_refs: Sequence[dict[str, Any]],
    *,
    s2: S2Client | None,
    resolve_book: BookResolver | None,
    patent_id: str,
) -> list[dict[str, Any]]:
    """Resolve a patent's NPL references, each on a best-effort basis.

    In order: a DOI or arXiv ID to a Semantic Scholar paper, an ISBN to a
    book, then an unconfirmed title-match candidate for what is left.

    Args:
        npl_refs: The raw NPL references from EPO, each with ``raw``.
        s2: Semantic Scholar client; without it no paper is looked up.
        resolve_book: ISBN lookup; without it no book is looked up.
        patent_id: Patent the references are cited by, for the logs.

    Returns:
        One entry per reference, in order.
    """
    papers: dict[int, PaperRecord | None] = {}
    if s2 is not None and npl_refs:
        papers = await _resolve_identified(npl_refs, s2, patent_id)
    entries = [
        _npl_entry(
            npl["raw"],
            extract_doi(npl["raw"]) if s2 is not None else None,
            papers.get(i),
        )
        for i, npl in enumerate(npl_refs)
    ]
    if resolve_book is not None:
        await _attach_npl_books(entries, resolve_book, patent_id)
    if s2 is not None:
        await attach_title_candidates(entries, s2, patent_id)
    return entries
