---
type: Reference
title: EPO OPS published-data search range
description: How many results one OPS search request returns, the default range, and the cap on results a search can reach.
subject_version: "OPS 3.2"
valid_for: "OPS 3.x"
generated:
  by: process:researching-references
  at: 2026-11-06
stale_after: 2027-11-06
status: draft
sources:
  - id: ops-faq-results
    title: EPO FAQ "How many results are displayed in OPS?" (no last-updated date on the page; text checked verbatim against the live page 2026-11-06)
    resource: https://epo.org/en/service-support/faq/searching-patents/open-patent-services/general-information/how-many-results-are
    accessed: 2026-11-06
  - id: ops-yaml
    title: OPS 3.2 OpenAPI description (vendored at sources/epo-ops/ops.yaml)
    resource: ./sources/epo-ops/ops.yaml
    accessed: 2026-11-06
---

# EPO OPS published-data search range

The published-data search service takes the slice of results to return as a
`Range` of 1-based positions, `first-last`. Two limits apply to it, and
neither appears in the OpenAPI description.

- **Default.** Without a `Range`, a search returns positions 1 to 25. The
  EPO FAQ: "The default display in OPS only shows the first 25 results".
  The OpenAPI description gives the same default, `1-25`, for the `Range` of
  `/published-data/search` and `/published-data/search/{constituent}`, and
  states no maximum. [source: ops-faq-results] [source: ops-yaml]
- **Per request.** One request returns at most 100 results: "You can download
  batches of up to 100 results at a time", with the example `&Range=1-100`.
  [source: ops-faq-results]
- **Per search.** "OPS can only display a total of 2 000 results. If there are
  more than 2 000 hits in your results list, you will have to limit your
  search query to reduce the number of results." [source: ops-faq-results]

`search_patents` clamps `limit` to 1 to 100 before building the range (#488),
so a request never asks for more than one batch.

## Not recorded

- What OPS answers for a range wider than 100 positions: an error, a
  truncated slice, or the full width. The FAQ gives only the limit, and no
  request past it has been observed.
- What OPS answers for a range that starts past position 2,000.
