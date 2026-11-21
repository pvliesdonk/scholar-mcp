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
  `chapter_info.isbn`, checked by `checked_isbn13`: free text holds other
  10- and 13-digit numbers, and only a valid check digit makes one an ISBN
  ([ISBNs in free-text citations](reference/isbn-in-citation-text.md)).
- The lookup is `resolve_book_by_isbn`, the one ISBN lookup every caller
  shares (#706). Like `batch_resolve`, this path leaves `fetch_authors` off:
  the cache first, then one Open Library request, with authors filled from
  the cache only, because a patent can cite many books at once (#403).
- A failing Open Library is logged at WARNING and leaves the reference with
  its `isbn`; it never fails the call.
- A chapter reference keeps its `chapter_info` next to the `book`, which is
  the book the chapter sits in.

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
