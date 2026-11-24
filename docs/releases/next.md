# Next release

<!-- notes-range-end: 7e6795e3ae8cc61d9ff110fda504e9dd67cdf18c -->

<!-- RELEASE-SUMMARY NEXT START -->
Book chapters are cited as chapters. When a paper's DOI is a CrossRef book
chapter, the paper result names the book it belongs to, with the book's
editors and the chapter's pages, and `generate_citations` writes it as a
chapter entry: BibTeX `@incollection`, CSL-JSON `chapter`, RIS `CHAP`.
Chapter references in a patent's cited literature no longer report page
ranges as ISBNs, read the German `Kap.` and `S.` forms, and carry their book
when they name one. CrossRef lookups are paced to the public pool's limits.
See Upgrading.
<!-- RELEASE-SUMMARY NEXT END -->

## Upgrading

No step is needed. If you watch the logs for CrossRef warnings, a throttled
CrossRef lookup now logs `crossref_rate_limited` without a traceback, where
it used to log `crossref_error` with one
([#760](https://github.com/pvliesdonk/scholar-mcp/pull/760)).

**Clients:** nothing beyond reconnecting. The new fields are additions:
`chapter_info` on paper results, `chapter_info.parent_book` on `get_patent`
citations. One output changes for the same input: `generate_citations`
writes a CrossRef book chapter as a chapter entry where it used to write an
article or the whole book.

**State:** the cache keeps everything. The books that chapters belong to are
cached alongside the other CrossRef lookups.

**Security posture:** none.

## Book chapters cited as chapters

"A chapter in an edited volume is cited as the whole book or as an article,
which is wrong in a bibliography"
([#593](https://github.com/pvliesdonk/scholar-mcp/issues/593)). Semantic
Scholar's "coverage of book chapters is weaker than journal articles"
([#67](https://github.com/pvliesdonk/scholar-mcp/issues/67)), so this release
takes the book from CrossRef.

When enrichment finds that a paper's DOI is a CrossRef `book-chapter`, the
paper gets a `chapter_info` with `citation_source: "crossref"`: the chapter
and book titles, the book's DOI, editors, pages, publisher, place, edition
and ISBN, each left out when CrossRef lacks it
([#754](https://github.com/pvliesdonk/scholar-mcp/pull/754)). This runs
wherever paper results are enriched, such as `get_paper`, `get_citations`
and `get_references`. CrossRef keeps a book's editors on the book's record
rather than the chapter's, so the book is fetched too and cached. The book title is the
book's, not the series it appears in. The fields are listed in
[Enrichment: Book chapters](../use/enrichment.md#book-chapters).

`generate_citations` then writes that paper as a chapter of its book
([#764](https://github.com/pvliesdonk/scholar-mcp/pull/764)):

- BibTeX `@incollection`, with the book as `booktitle`, plus `editor`,
  `pages`, `publisher`, `address`, `edition` and `isbn` where known.
  `@incollection` is the one chapter type classic BibTeX and biblatex read
  the same way.
- CSL-JSON `chapter`, with the book as `container-title`.
- RIS `CHAP`, with the book as `T2` and its editors as `A2`.

A chapter with no author or editor on record is still written as a chapter,
without those fields. A paper Semantic Scholar marks as a conference paper
stays `@inproceedings`, because CrossRef files proceedings volumes such as
Lecture Notes in Computer Science as books. Nothing needs enabling:
`generate_citations` enriches by default, and with `enrich` set to false no
CrossRef lookup runs, so a chapter is cited as before. See
[`generate_citations`](../reference/tools/citations.md).

What this does not cover:

- CrossRef has no chapter number, so neither does the entry.
- A chapter whose CrossRef record does not link to its book is described from
  its own record, without the book's editors. That was every Elsevier chapter
  in the sample behind this work; looking the book up by ISBN instead is open
  as [#753](https://github.com/pvliesdonk/scholar-mcp/issues/753).
- A chapter without a DOI gets no CrossRef lookup. A title search was
  measured and not built: it found the chapter for 2 of 37 such papers
  ([#745](https://github.com/pvliesdonk/scholar-mcp/issues/745)).

## Chapters in a patent's cited literature

`get_patent(sections=["citations"])` reads chapter details from each cited
reference's text into `chapter_info`. Three changes:

- **ISBNs are checked.** "`get_patent`'s NPL `chapter_info.isbn` can hold a
  number that is not an ISBN": a page range and a Wikipedia revision id were
  reported as ISBNs
  ([#737](https://github.com/pvliesdonk/scholar-mcp/issues/737)). An ISBN is
  now reported only when its check digit is valid
  ([#750](https://github.com/pvliesdonk/scholar-mcp/pull/750)).
- **German citations are read.** German examiner citations write the chapter
  and pages as `Kap. 1, S. 1-44`; these now give the chapter number and page
  range, as `Ch.` and `pp.` do. The book title after `In:` also stops before
  an edition statement such as `1st edition`, in English and German
  citations alike ([#751](https://github.com/pvliesdonk/scholar-mcp/pull/751)).
- **The book is attached.** When a reference resolved to a paper and names
  its chapter, pages or `In:` book with a valid ISBN, the book's record is
  added as `chapter_info.parent_book`
  ([#755](https://github.com/pvliesdonk/scholar-mcp/pull/755)). A reference
  that resolved to no paper keeps its book in the entry's `book` field, as
  before.

See [`get_patent`](../reference/tools/patents.md).

## CrossRef lookups are paced

CrossRef requests used to go out with no pacing, up to ten at a time, while
the public pool allows one in flight. Lookups by DOI are now spaced at least
0.2 seconds apart with one in flight, the rate the pool advertises for them
([#760](https://github.com/pvliesdonk/scholar-mcp/pull/760)), so enriching
many papers at once takes longer. A throttled lookup is logged as a
throttle, and a DOI CrossRef doesn't know is logged at DEBUG; either way the
paper is returned without its CrossRef data, and the next request asks again.

## Fix

`batch_resolve` sent some Semantic Scholar paper ids to EPO as patent
numbers: an id starting with `be`, `ca` or `de` and a digit "comes back as a
patent (`source_type: "patent"`) with an EPO error, not as the paper"
([#699](https://github.com/pvliesdonk/scholar-mcp/issues/699)). A
40-character hex id is now always a paper
([#759](https://github.com/pvliesdonk/scholar-mcp/pull/759)).
