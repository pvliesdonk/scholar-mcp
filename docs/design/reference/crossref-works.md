---
type: Reference
title: CrossRef work journal fields
description: The CrossRef REST API work fields that place an article in its journal (ISSN, volume, issue, pages), as the access-link OpenURL reads them.
subject_version: "Crossref REST API 4.5.1 (swagger), observed November 2026"
valid_for: "Crossref REST API 4.x"
generated:
  by: process:researching-references
  at: 2026-11-02T20:30:00+01:00
verified:
  - by: process:researching-references
    at: 2026-11-02T20:30:00+01:00
stale_after: 2027-05-02T00:00:00+00:00
status: draft
sources:
  - id: swagger
    title: Crossref REST API OpenAPI (swagger) specification, `Work` definition
    resource: https://api.crossref.org/swagger-docs
    accessed: 2026-11-02
  - id: nature-sample
    title: Crossref work record for DOI 10.1038/nature14539
    resource: https://api.crossref.org/works/10.1038/nature14539
    accessed: 2026-11-02
---

# CrossRef work journal fields

The CrossRef enricher stores a paper's whole CrossRef work as
`crossref_metadata` (#541 reads part of it). This page covers the fields that
say where in a journal the article appears.

## Scope

- Covers: `ISSN`, `issn-type`, `volume`, `issue`, `page`, `article-number`
  and `container-title` of a work.
- Does not cover: the rest of the work, the enricher's request path, or
  rate limits.
- Depended on by: `src/scholar_mcp/_access_links.py` (`_crossref_details`,
  the journal title fallback).

## Claims

- `ISSN` is a list of strings, and `issn-type` a list of `WorkISSNType`
  objects. [source: swagger] (`Work`)
- Each `issn-type` entry pairs a `value` with a `type`; the Nature sample
  gave `print` for `0028-0836` and `electronic` for `1476-4687`, and listed
  both values in `ISSN`. [source: nature-sample]
  [pins: tests/test_access_links.py::test_openurl_carries_crossref_journal_details]
- `volume`, `issue`, `page` and `article-number` are single strings.
  [source: swagger] (`Work`)
- `page` holds the range with a hyphen: `"436-444"` in the Nature sample,
  where `volume` was `"521"` and `issue` `"7553"`. [source: nature-sample]
  [pins: tests/test_access_links.py::test_openurl_carries_crossref_journal_details]
- `container-title` is a list of strings; the sample gave `["Nature"]`.
  [source: swagger] [source: nature-sample]
  [pins: tests/test_access_links.py::test_journal_title_falls_back_when_venue_is_empty]
- None of these fields is required by the specification; only fields such as
  `DOI`, `type`, `publisher` and `issued` are. [source: swagger] (`Work`,
  `required`)
- Which `type` values `issn-type` can take besides `print` and `electronic`
  is not listed in the definition. [unverified] Check the `WorkISSNType`
  definition or Crossref's schema documentation.

## Where this project departs from the subject

The access-link builder sends an untyped ISSN (one listed in `ISSN` with no
`issn-type`) as the print ISSN, and an `article-number` as the start page when
`page` is absent. Neither mapping comes from CrossRef. See
[access links](../access-links.md).

## Not covered

How completely publishers deposit these fields, and the formats `page` takes
besides a hyphenated range, rest on one sample.
