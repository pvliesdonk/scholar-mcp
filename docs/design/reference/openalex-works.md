---
type: Reference
title: OpenAlex work objects
description: The fields of an OpenAlex work that Scholar MCP reads, and how they map onto an S2-shaped paper record.
subject_version: "OpenAlex API, work object docs at openalex-docs 8cec9db, observed September 2026"
valid_for: "The OpenAlex works API as documented and served in September 2026"
generated:
  by: process:researching-references
  at: 2026-09-28
stale_after: 2027-03-28
status: draft
sources:
  - id: work-object
    title: OpenAlex docs, "Work object"
    resource: https://github.com/ourresearch/openalex-docs/blob/8cec9dba1ee17af56e5de4666f63650a02fb798b/api-entities/works/work-object/README.md
    accessed: 2026-09-28
---

# OpenAlex work objects

The OpenAlex work fields this project reads. The venue enricher uses one of
them; `batch_resolve`'s DOI fallback maps a whole work onto the S2 field names
(#478).

## Scope

- Covers: `title`, `publication_year`, `cited_by_count`, `primary_location`,
  `best_oa_location`, `open_access`, `authorships`, `ids`, `doi`, `id`,
  `abstract_inverted_index`, `referenced_works` and `referenced_works_count`.
- Does not cover: concepts, topics, funders, affiliations (read by
  `enrich_paper` through `_select_enrichment_fields`), or filtering and paging.
- Depended on by: `src/scholar_mcp/_openalex_client.py` (`work_to_paper`,
  `work_venue`), `_enricher_openalex.py`, `_tools_utility.py` (`batch_resolve`).

## Claims

### Identity and bibliographic fields

- `title` is exactly the same as `display_name`. [source: work-object]
  [pins: tests/test_tools_utility.py::test_openalex_fallback_compact_has_exactly_the_compact_keys]
- `publication_year` is an integer year; `cited_by_count` is the integer
  number of works citing this one. [source: work-object]
  [pins: tests/test_tools_utility.py::test_openalex_fallback_compact_has_exactly_the_compact_keys]
- `primary_location.source.display_name` names the venue, for a journal
  article the publisher's journal. [source: work-object]
  [pins: tests/test_tools_utility.py::test_openalex_fallback_compact_has_exactly_the_compact_keys]
- `primary_location` and `best_oa_location` can be null. [observed: the live
  record for 10.1038/nature14539 on 2026-09-28 had a `best_oa_location` whose
  `pdf_url` was null; a null location object itself was not observed]
  [unverified] for the whole object. The mapper tolerates both.
  [pins: tests/test_tools_utility.py::test_openalex_fallback_tolerates_missing_objects]

### External identifiers

- `ids` lists every known external identifier as a URI where possible: `doi`,
  `mag`, `openalex`, `pmid`, `pmcid`. Keys for null IDs are omitted.
  `ids.doi` repeats `doi`, and `ids.openalex` repeats `id`. [source: work-object]
  [pins: tests/test_tools_utility.py::test_openalex_fallback_standard_maps_authors_ids_and_abstract]
- The docs type `mag` as an integer; the live record served it as the string
  `"2919115771"`. [source: work-object] [observed: `curl
  https://api.openalex.org/works/doi:10.1038/nature14539` on 2026-09-28]
  The mapper converts it to a string either way.

### Authors, abstract and references

- `authorships` is a list of authorship objects, limited to the first 100
  authors; each carries `author.display_name`. [source: work-object]
  [pins: tests/test_tools_utility.py::test_openalex_fallback_standard_maps_authors_ids_and_abstract]
- OpenAlex publishes no plain-text abstract, only `abstract_inverted_index`,
  which maps each word to its positions in the text. Coverage falls with age:
  over 60% of 2022 works have one against 45% of works before 2000.
  [source: work-object]
  [pins: tests/test_tools_utility.py::test_openalex_fallback_standard_maps_authors_ids_and_abstract]
- The live record for 10.1038/nature14539 had an empty inverted index.
  [observed: `curl https://api.openalex.org/works/doi:10.1038/nature14539`
  on 2026-09-28]
- `referenced_works` lists the OpenAlex IDs this work cites.
  `referenced_works_count` appears in live records but has no entry in the
  work-object docs. [source: work-object] [observed: the same request]
  [pins: tests/test_tools_utility.py::test_openalex_fallback_full_takes_only_a_pdf_url]

### Open access

- `best_oa_location` is the best open location by a documented scoring:
  publisher over repository, published over accepted version, a location with
  a `pdf_url` over one without. [source: work-object]
- `best_oa_location.pdf_url` can be null while `open_access.oa_url` is set;
  in the live record `oa_url` was a HAL landing page, not a PDF.
  [observed: the same request]
  [pins: tests/test_tools_utility.py::test_openalex_fallback_full_takes_only_a_pdf_url]
- `open_access.oa_status` is a lowercase string such as `green`.
  [observed: the same request]

## Where this project departs from the subject

`work_to_paper` renames fields to S2's names and sets `paperId`, `tldr` and
`fieldsOfStudy` to null: OpenAlex has no S2 id, no TLDR, and its topic fields
are not S2's field-of-study vocabulary. `openAccessPdf` is built from
`best_oa_location.pdf_url` only, never `oa_url`, because callers download
`openAccessPdf.url` as a PDF. Its `status` is `oa_status` upper-cased to match
the S2 records this project stores (`"GREEN"`).

## Not covered

- Whether the S2 `openAccessPdf.status` vocabulary matches OpenAlex's
  `oa_status` values beyond `green`. [unverified] The S2 reference has no
  claim for it.
