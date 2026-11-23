# Chapter citations

`generate_citations` cites a chapter of an edited book as a chapter, with
its book (#593). The CrossRef data comes from the chapter mapping in
[CrossRef book chapters](crossref-book-chapters.md); how each format
represents a chapter is recorded in
[Book-chapter entries in BibTeX, biblatex, CSL-JSON and RIS](reference/chapter-citation-entry-types.md).
The code is `_chapter_citation.py`, called from `_citation_formatter.py`.

## When a paper is a chapter

- A paper is a chapter when its `chapter_info` has
  `citation_source: "crossref"` and a `parent_title`. Without a book title
  there is no book to cite it in, and the paper is inferred as before.
- `chapter_info` exists only after enrichment: `generate_citations` runs the
  `papers` enrichment (OpenAlex, CrossRef, then the chapter mapping) when
  `enrich` is true, the default. With `enrich=False` no CrossRef lookup runs,
  S2's batch endpoint returns no `chapter_info`, and a chapter comes out as
  `@article` (or whatever its venue implies), as it did before #593.
- A conference paper stays `inproceedings`. Springer deposits proceedings
  papers (LNCS and similar series) as CrossRef `book-chapter` works; for
  example 10.1007/978-3-319-24574-4_28 is a `book-chapter` in "Lecture
  Notes in Computer Science" / "Medical Image Computing and
  Computer-Assisted Intervention – MICCAI 2015" (observed against
  api.crossref.org on 2026-11-23). S2's `Conference` publication type or a
  conference keyword in the venue therefore wins over `chapter_info`.
- A chapter wins over `book_metadata`: a chapter whose ISBN led to a book
  record is still the chapter, not the whole book.

## What is emitted

| Part | BibTeX `@incollection` | CSL `chapter` | RIS `CHAP` |
| --- | --- | --- | --- |
| Chapter authors (S2 `authors`) | `author` | `author` | `AU` |
| Chapter title (S2 `title`) | `title` | `title` | `TI` |
| Year (S2 `year`) | `year` | `issued` | `PY` |
| `parent_title` | `booktitle` | `container-title` | `T2` |
| `editors` | `editor` | `editor` | `A2` |
| `pages` | `pages`, as given | `page`, as given | `SP`/`EP` when it has exactly one hyphen, else `SP` |
| `publisher` | `publisher` | `publisher` | `PB` |
| `publisher_location` | `address` | `publisher-place` | `CY` |
| `edition` | `edition` | `edition` | `ET` |
| `isbn` | `isbn` | `ISBN` | `SN` |

DOI, URL, abstract and arXiv fields are written as for any paper. The S2
`venue` is not used for a chapter: for a series chapter it is often the
series, and `parent_title` is already the book.

## Decisions

- **`@incollection` always, never `@inbook`.** Classic BibTeX's `@inbook`
  holds the book's title in `title` and has no field for a chapter title;
  biblatex's `@inbook` holds the chapter there. `@incollection` reads the
  same in both. pandoc picks `@inbook` for a chapter without editors; that
  would misplace the chapter title under classic BibTeX, so it was not
  followed. CSL `chapter` and RIS `CHAP` have no such split.
- **Missing parts are left out.** Editors (present only when the chapter or
  its fetched parent lists them), pages, place and edition are each
  optional; the entry is written without them.
- **No author and no editor: still a chapter.** About a third of CrossRef
  chapter records name neither (front matter, indexes, encyclopedia
  entries). Such a record is written as a chapter with no `author` and no
  `editor`, and its BibTeX key falls back to `anon<year>` as for any paper
  without authors. Alternatives considered:
  - *Cite the whole book instead.* Loses the chapter's title, pages and
    DOI, which identify what was cited.
  - *Promote the editors to `author`.* Misattributes, and does not apply
    here since there are no editors.
  - *Fall back to `@article`/`@misc`.* Loses the book.
  BibTeX's `plain.bst` warns "empty author" and still writes the entry;
  biblatex's styles accept a missing `author`; CSL requires no variable and
  its `chapter` type explicitly covers prefaces and forewords.
- **Authors come from S2.** `chapter_info` carries no authors; the chapter's
  authors are S2's `authors`, so "no author" means S2 lists none.
- **Editors are `"Given Family"` strings** and go through the same name
  parser as authors. An organisation editor (CrossRef `name` only, absent
  from the 380-record sample) would be split like a personal name.
- **Two `chapter_info` shapes exist.** #67's CrossRef shape (flat
  `parent_title`, `editors`, `publisher`, …) is the one read here. #64's
  parsed shape fills `parent_book` only on patent NPL entries and
  `batch_resolve` results, which never reach `generate_citations`, so it is
  not read.

## Not covered

- `series` (CrossRef's first `container-title` for a series chapter):
  `chapter_info` does not keep it, and adding it is an enricher change.
- Chapter numbers: CrossRef has no such field.
- CSL `entry-encyclopedia` and biblatex `@inreference`/`@suppbook`: the
  CrossRef chapter record does not say which chapters are encyclopedia
  entries or front matter.
