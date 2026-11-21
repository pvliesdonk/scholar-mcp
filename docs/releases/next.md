# Next release

<!-- notes-range-end: dcab175a9f7266a7610b73842433f27e74671ebf -->

<!-- RELEASE-SUMMARY NEXT START -->
Patents become readable and citable. `get_patent` returns a patent's claims
and description, which came back empty before, as compact Markdown with the
description in pages. `generate_citations` accepts patent numbers next to
paper identifiers and writes biblatex, CSL-JSON and RIS patent entries.
A patent's cited literature now resolves to books by ISBN and to papers by
arXiv identifier, and a reference with neither may carry an unconfirmed
title-matched candidate. See Upgrading.
<!-- RELEASE-SUMMARY NEXT END -->

## Upgrading

No step is needed. The first `get_patent` call for a patent's claims or
description after upgrading fetches them from EPO again, because the copies
the previous release cached were empty
([#702](https://github.com/pvliesdonk/scholar-mcp/pull/702),
[#703](https://github.com/pvliesdonk/scholar-mcp/pull/703)).

**Clients:** nothing beyond reconnecting. `get_patent` gains `text_offset`
and `max_chars`, and its claims, description and citations carry new fields;
none of the existing fields changed meaning.

**State:** the cache keeps everything except the patent claims and
description rows, which a one-shot repair drops so they are fetched again.

**Security posture:** none in this server. Images and packages built from the
lock file move FastMCP from 4.2.3 to 4.2.4, which fixes a race in the OAuth
proxy where two concurrent token requests could redeem one authorization code
or refresh token twice (GHSA-78c8-3jhx-5mg7). That matters if you run OIDC
authentication ([#705](https://github.com/pvliesdonk/scholar-mcp/pull/705)).

## Patent claims and descriptions

`get_patent(sections=["claims", "description"])` returns the text of the
patent, read from EPO's own full-text service. In earlier releases both
sections came back as an empty string for every patent: the parser expected a
response shape EPO never sends, and a patent without full text failed the
whole call with a server error
([#701](https://github.com/pvliesdonk/scholar-mcp/issues/701)). Both are
fixed ([#702](https://github.com/pvliesdonk/scholar-mcp/pull/702)).

The text arrives ready to read, because the callers are agents and "patent
full text is available directly from the EPO OPS API", so no PDF conversion
is needed ([#44](https://github.com/pvliesdonk/scholar-mcp/issues/44)):

- Claims come as one numbered block per claim. A claim EPO splits over
  several pieces is rejoined, and a WO claim set sent as one block is split
  at each claim number.
- The description's section headings become `##` headings, and each
  paragraph keeps its number (`[0001]`), the way patents are cited.
- The description is paged like converted PDFs: up to 20,000 characters per
  response, and `next_offset` names where the next page starts; pass it back
  as `text_offset`. Claims come whole.
- A publication EPO holds no full text for gives `null` sections, not an
  error; `fetch_patent_pdf` has the document then.

How EPO shapes these responses is recorded in
[EPO OPS full-text claims and description](https://github.com/pvliesdonk/scholar-mcp/blob/main/docs/design/reference/epo-ops-fulltext.md),
from responses captured for the tests
([#703](https://github.com/pvliesdonk/scholar-mcp/pull/703)).

## Citing patents

`generate_citations` now formats patents as well as papers. Patent numbers
such as `EP1234567A1` go in the same `paper_ids` list as DOIs and arXiv
identifiers, and the citations keep the order of that list. "Patents have
different required BibTeX/RIS fields than academic papers"
([#50](https://github.com/pvliesdonk/scholar-mcp/issues/50)), so each format
gets its own patent entry
([#700](https://github.com/pvliesdonk/scholar-mcp/pull/700)):

- BibTeX is a biblatex `@patent`, with inventors as `author`, applicants as
  `holder`, the full number with its office (`EP 3491801 B1`), and a `type`
  of application or granted patent read from the kind code where it is
  known for EP, US, WO and DE.
- CSL-JSON is type `patent`, with the office as `authority` and the filing
  date as `submitted`. CSL has no field for the applicants, so they are left
  out there.
- RIS is type `PAT`, with the applicants in `PB`.

A patent EPO cannot look up becomes a comment with the reason, as an
unresolved paper does. When nothing resolves, the response now lists the
reason for each identifier, so a caller can tell a busy EPO from a wrong
number. The
format rules are in
[Patent entries in biblatex, CSL-JSON and RIS](https://github.com/pvliesdonk/scholar-mcp/blob/main/docs/design/reference/patent-citation-formats.md).

## A patent's cited literature

`get_patent(sections=["citations"])` lists the non-patent literature a patent
cites. Until now only a reference with a DOI was resolved to a paper; "NPL
references without a DOI currently get `confidence: null`"
([#59](https://github.com/pvliesdonk/scholar-mcp/issues/59)). Three more
routes now apply, each on a best-effort basis that never fails the call:

- **Books by ISBN.** "Patents frequently cite textbooks and monographs in
  their non-patent literature (NPL) references"
  ([#70](https://github.com/pvliesdonk/scholar-mcp/issues/70)). A reference
  with a valid ISBN gets the book from Open Library as `book`, or keeps the
  checked ISBN as `isbn` when Open Library has none
  ([#707](https://github.com/pvliesdonk/scholar-mcp/pull/707)).
- **Papers by arXiv identifier.** `abs/1704.04861`, `arXiv:…` and the
  `10.48550/arXiv.…` form resolve exactly, as a DOI does
  ([#708](https://github.com/pvliesdonk/scholar-mcp/pull/708)).
- **Title candidates.** A reference with none of these gets its title looked
  up with Semantic Scholar's title match. A hit is returned as `candidate`
  with `confidence: "unconfirmed"`, never as `paper`, and only when its title
  and year agree with the citation; verify it before citing it
  ([#708](https://github.com/pvliesdonk/scholar-mcp/pull/708)). These lookups
  share the Semantic Scholar budget, so a call makes at most ten.

## Smaller fixes

- `search_patents` with an empty `date_from` and no `date_to` sent EPO a
  query containing `pd <= None`; it now adds no date filter
  ([#717](https://github.com/pvliesdonk/scholar-mcp/pull/717)).
