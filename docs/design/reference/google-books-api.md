---
type: Reference
title: Google Books volume search behaviour used by Scholar MCP
description: ISBN search, result shape, identification, and quota failures in Google Books API v1.
subject_version: "Google Books API v1, observed September 2026"
valid_for: "The published v1 API as checked on 2026-09-21"
generated:
  by: process:researching-references
  at: 2026-09-21
stale_after: 2027-03-21
status: draft
sources:
  - id: using
    title: Google Books API v1 Using the API
    resource: https://developers.google.com/books/docs/v1/using
    accessed: 2026-09-21
  - id: volumes-list
    title: Google Books API v1 Volume list method
    resource: https://developers.google.com/books/docs/v1/reference/volumes/list
    accessed: 2026-09-21
  - id: anonymous-observation
    title: Deployed anonymous request and log recorded on issue 366
    resource: https://github.com/pvliesdonk/scholar-mcp/issues/366
    accessed: 2026-09-21
---

# Google Books volume search behaviour used by Scholar MCP

This page covers the `volumes` lookup used for ISBN enrichment and excerpts.
The exact anonymous and keyed quota limits are not published in the Books API
pages checked here.

## Scope

- Covers: public volume search, result shape, application identification, and
  the failure cases that must stay distinct from a missing book.
- Does not cover: private bookshelves, purchases, or Books content licensing.
- Depended on by: `src/scholar_mcp/_google_books_client.py`,
  `_enricher_google_books.py`, and `_tools_books.py`.

## Claims

### Search and response

- `GET /books/v1/volumes` requires `q`; `isbn:` searches the ISBN field.
  [source: using] [source: volumes-list]
  [pins: tests/test_google_books_client.py::test_search_by_isbn_returns_volume]
- A successful volume search with matches has HTTP 200 and a list result with
  `totalItems` and `items` containing volume resources. The client treats an
  empty `items` list as a no-match, distinct from an HTTP error.
  [source: using] [source: volumes-list]
  [pins: tests/test_google_books_client.py::test_search_by_isbn_returns_none_when_empty]
- Whether an actual no-match response omits `items` entirely, rather than
  returning `"items": []`, is not established by the published example or a
  captured no-match response. [unverified] Capture one answered no-match call.

### Identification and quota

- The published guide says every request identifies the application with an
  API key or OAuth token, and public data can use either. It does not state a
  numeric anonymous allowance. [source: using]
- Issue #366 reports a deployed request with no configured Books key receiving
  HTTP 429 for ISBN `9780201633610` on the 2.0.0 release candidate. The original
  container log is not retained here. [unverified] Compare a retained log and
  deployment configuration. [source: anonymous-observation]
- A single anonymous `curl` request for `isbn:0000000000` on 2026-09-21 also
  returned HTTP 429. Its JSON identified the exhausted metric as daily
  `Queries`, the reason as `rateLimitExceeded`, and the status as
  `RESOURCE_EXHAUSTED`. This is one response, not a measured quota ceiling.
  [observed: `curl -i 'https://www.googleapis.com/books/v1/volumes?q=isbn%3A0000000000'` on 2026-09-21]
- An HTTP refusal cannot establish that an ISBN is absent. The client raises
  status and transport errors; only a successful empty search becomes `None`.
  [source: volumes-list]
  [pins: tests/test_google_books_client.py::test_search_by_isbn_raises_on_error,
  tests/test_google_books_client.py::test_search_by_isbn_returns_none_when_empty]
- The numeric anonymous rate and the response to **keyed** quota exhaustion
  are unknown. In particular, a keyed 403 with `reason: rateLimitExceeded`
  has not been observed for this API here. [unverified] Verify against a Books
  response from an identified key or a Books-specific vendor statement.

## Where this project departs from the subject

The client allows an unset API key because anonymous calls have reached the
endpoint in deployment. It must nevertheless treat 429 as a failure, not as an
empty search. The discrepancy with the identification requirement in the
published guide is explicit above.

## Not covered

The daily allowance attached to the anonymous consumer, its reset time, and
whether all Books projects use the same ceiling are unknown. One observed 429
does not answer them.
