# Resolving a patent's non-patent literature

`get_patent(sections=["citations"])` returns each non-patent literature (NPL)
reference with its raw citation string and, on a best-effort basis, the work
it names. Resolution reruns on every call, so it reflects the current paper
and book indexes; only the raw EPO citations are cached.

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
- The lookup is `resolve_book_by_isbn`, shared with `batch_resolve`: the
  cache first, then one Open Library request, with authors filled from the
  cache only, because a patent can cite many books at once (#403).
- A failing Open Library is logged at WARNING and leaves the reference with
  its `isbn`; it never fails the call.
- A chapter reference keeps its `chapter_info` next to the `book`, which is
  the book the chapter sits in.

Title search for a reference with neither DOI nor ISBN is #59: it trades
coverage for false matches, so it is decided there for papers and books
together.
