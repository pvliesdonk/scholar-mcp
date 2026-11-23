# Resolving a patent's non-patent literature

`get_patent(sections=["citations"])` returns each non-patent literature (NPL)
reference with its raw citation string and, on a best-effort basis, the work
it names. Resolution reruns on every call, so it reflects the current paper
and book indexes; only the raw EPO citations are cached.

The pipeline is `resolve_npl_refs` in `src/scholar_mcp/_npl_resolution.py`
(#710); `_tools_patent.py` only fetches and caches the raw citations.

## Papers by DOI

A DOI found in the raw text ([DOIs in free-text citations](reference/doi-in-citation-text.md))
is resolved in one Semantic Scholar batch. A match is `paper` with
`confidence: "high"`; a DOI that does not resolve is kept as `doi`.

## Books by ISBN (#70)

A reference no paper was found for, and whose text carries an ISBN, is looked
up in Open Library: the result is `book` with `confidence: "high"`, or the
validated ISBN-13 as `isbn` when Open Library has no edition or fails.

- The ISBN is the one the chapter parser already extracts into
  `chapter_info.isbn`. Free text holds other 10- and 13-digit numbers (page
  ranges such as "S. 81057-81105", Wikipedia `oldid=` revision ids), and only
  a valid check digit makes one an ISBN
  ([ISBNs in free-text citations](reference/isbn-in-citation-text.md)), so
  the parser keeps only a candidate `checked_isbn13` accepts, the first valid
  ISBN-13 before any ISBN-10 (#737). An ISBN-10 candidate never starts inside
  a longer digit group, so the tail of an ISBN-13 that failed its check is not
  retried as an ISBN-10; an unmarked ISBN-10 directly after another number and
  one space or hyphen is missed for the same reason. The book lookup checks it again with
  `checked_isbn13`, which also converts an ISBN-10 to the ISBN-13 it looks up.
  No "ISBN" marker is required: the reference does not establish that every
  citation carries one.
- The lookup is `resolve_book_by_isbn`, the one ISBN lookup every caller
  shares (#706). Like `batch_resolve`, this path leaves `fetch_authors` off:
  the cache first, then one Open Library request, with authors filled from
  the cache only, because a patent can cite many books at once (#403).
- A failing Open Library is logged at WARNING and leaves the reference with
  its `isbn`; it never fails the call.
- A chapter reference keeps its `chapter_info` next to the `book`, which is
  the book the chapter sits in.

## The book a chapter sits in (#64)

`BookChapterRecord.parent_book` is the book a cited part sits in. This
pipeline fills it in `chapter_info` through `attach_parent_book`
(`src/scholar_mcp/_chapter_parent.py`).

- A parsed `chapter_info` names a part of a book only when it has a
  `chapter_number`, a `page_start` or a `parent_title` (an `In:` clause). An
  ISBN alone names the whole book, which is no parent of itself, so it is
  not looked up as one.
- A book's own DOI ends in its ISBN (`10.1201/9781420010749`), and the
  parser reads those digits as the ISBN. When the citation's DOI ends in the
  ISBN, the paper found for that DOI is the book, so no parent is looked up.
  A chapter DOI carries its book's ISBN followed by a suffix
  (`10.1007/978-3-540-52155-6_1`), and that ISBN is the parent's.
- With a part named and a valid ISBN, the ISBN is the containing book's. It
  is looked up through `resolve_book_by_isbn`, best-effort like the other
  lookups: a book Open Library lacks, or a failing lookup, leaves
  `chapter_info` with its `isbn`. The failure is logged at DEBUG
  (`chapter_parent_book_failed`), as the logging standard asks for an
  optional extra; the paper, the entry's result, is unaffected.
- The book is stored once per entry. A reference no paper was found for
  already carries the book as the entry's `book` (above), so its
  `chapter_info` gets no `parent_book`. Only a reference a paper was found
  for, cited as part of a volume (a proceedings paper `In:` a volume with an
  ISBN, a chapter with a DOI), gets `chapter_info.parent_book`. A reader takes
  the containing book from `chapter_info.parent_book`, else from `book` when
  `chapter_info` names a part.
- #70 does not look up a resolved paper's ISBN as a book, because the paper
  already is the cited work. The parent lookup does not contradict that: it
  looks the ISBN up as the paper's container, not as the cited work. It adds
  at most one Open Library request per such reference, from the cache first,
  with authors from the cache only, as for #70.

Alternatives not taken: copying the entry's `book` into `parent_book` repeats
the same record in one response; moving it there changes where v3.4.0
returns it; a pointer from `chapter_info` to `book` is a new kind of field for
a reader to follow.

### `batch_resolve` is not wired

`batch_resolve` also attaches `chapter_info`, parsed from the identifier
string itself, but fills no `parent_book`. A caller reaches its chapter path
only by appending citation text to a `DOI:` identifier
(`DOI:10.1201/9781420010749 pp. 1-10`), a form the tool description does not
mention. Observed on 2026-11-23 against the deployed server (3.4.0-rc.1):
Semantic Scholar's batch endpoint resolved `DOI:10.1201/9781420010749` but
returned nothing for the same DOI with ` pp. 1-10` or `, Ch. 3` appended, and
OpenAlex, the fallback, returned the book for both from
`/works/https://doi.org/<DOI with the text appended>`. So the path runs only
through an undocumented input form and an OpenAlex tolerance nothing
documents, and in the observed case the paper is the book itself. A bare
book DOI reaches it with an ISBN alone, which names no part.

## Papers by arXiv identifier (#59)

An arXiv identifier (`abs/1704.04861`, `arXiv:1704.04861`, or the DataCite
DOI `10.48550/arXiv.1610.02357`) joins the DOI batch as `ARXIV:…`. It is an
exact identifier, so a hit is `paper` with `confidence: "high"`. For an arXiv
DataCite DOI the arXiv identifier is sent instead of the DOI; any other DOI
wins over an arXiv identifier.

## Candidates by title (#59)

A reference left with no `paper`, `book`, `isbn` or `doi` gets its title
guessed and sent to Semantic Scholar's title match. The endpoint always
answers with its closest title, and a generic one matches an unrelated paper
of the same name
([Semantic Scholar API behaviour](reference/semantic-scholar-api.md), "Title
match"). A hit is therefore never `paper`:

- It is added as `candidate`, with `confidence: "unconfirmed"` and
  `match: "title"`. Agents read that as a lead to check, and an agent that
  reads only `paper` never cites a guess.
- The title is the quoted one when the citation quotes it, else the text
  after the author list (`AUTHORS: Title.`), else after a bracketed year
  (`(2017) Title;`). A guess with fewer than three significant words is not
  looked up: "Deep learning" is too generic to match safely.
- A hit is kept only when its title and the guess share at least 80% of
  their significant words in both directions and, when the citation names
  years, the paper's year is within one of them. `matchScore` is not used;
  it is unbounded and undocumented.
- References that look like web pages (a URL, "Wikipedia") are not looked
  up.
- Lookups run one at a time and spend the Semantic Scholar budget every
  client of this server shares, so there are at most ten per call. They stop
  at the first rate limit (INFO) or failure (WARNING), leaving the rest
  unresolved; the call itself never fails on them.

Title search for books stays out: nothing in a citation string reliably
marks one as a book, so a cited book without an ISBN stays unresolved.
