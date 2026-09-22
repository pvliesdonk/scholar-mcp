---
type: Reference
title: Semantic Scholar API behaviour used by Scholar MCP
description: Rate limits, errors, pagination, and paper metadata in the Semantic Scholar API.
subject_version: "Academic Graph API v1 and Datasets API v1, observed September 2026"
valid_for: "The published v1 APIs as checked on 2026-09-21"
generated:
  by: process:researching-references
  at: 2026-09-21
stale_after: 2027-03-21
status: draft
sources:
  - id: product
    title: Semantic Scholar Academic Graph API product page
    resource: https://www.semanticscholar.org/product/api
    accessed: 2026-09-21
  - id: tutorial
    title: Semantic Scholar API tutorial
    resource: https://www.semanticscholar.org/product/api/tutorial
    accessed: 2026-09-21
  - id: graph-docs
    title: Academic Graph API documentation
    resource: https://api.semanticscholar.org/api-docs/graph
    accessed: 2026-09-21
  - id: key-observations
    title: Maintainer's direct key and throttle observations on issue 389
    resource: https://github.com/pvliesdonk/scholar-mcp/issues/389#issuecomment-5630995868
    accessed: 2026-09-21
  - id: type-observations
    title: Maintainer's keyed paper-batch observations on issue 389
    resource: https://github.com/pvliesdonk/scholar-mcp/issues/389#issuecomment-5698506793
    accessed: 2026-09-21
  - id: throttle-observations
    title: Deployed-server and direct-call observations on issue 406
    resource: https://github.com/pvliesdonk/scholar-mcp/issues/406
    accessed: 2026-09-21
---

# Semantic Scholar API behaviour used by Scholar MCP

This page records external behaviour relevant to the current client, graph tools,
and the planned shared gate and deferral work in #408 and #409. The observations
are scoped to the dates and keys named below; they do not establish a universal
throttle policy.

## Scope

- Covers: Academic Graph request limits, HTTP refusals, citation pagination and
  filters, author papers, and publication types. Datasets appears only as a key
  acceptance probe.
- Does not cover: the cost or design of a local Datasets store; see #406.
- Depended on by: `src/scholar_mcp/_s2_client.py`, `_rate_limiter.py`,
  `_tools_graph.py`, and `docs/design/service-lifecycle.md`.

## Claims

### Rate limits and refusals

- The introductory keyed limit is **one request per second across all
  endpoints**; an individual key may receive a higher rate after review.
  [source: product] [source: tutorial]
- Most endpoints admit unauthenticated requests. Their published allowance is
  1,000 requests per second **shared among all unauthenticated users**, with
  possible further throttling during heavy use; this is no per-client guarantee.
  [source: product]
- The tutorial classifies HTTP 429 as a rate-limit refusal and HTTP 403 as a
  permission refusal. [source: tutorial]
  [pins: tests/test_s2_rate_limiting.py::test_try_once_raises_rate_limited]
- The maintainer reported that a known-expired key and a fabricated key each
  received 403 `ForbiddenException` on Graph and Datasets calls in a
  2026-09-11 series (eight expired-key requests). The raw responses were not
  retained here, so this is a correction to the issue's earlier claim, not a
  freshly verified rule. [unverified] Recheck with a safely expired key or
  retained request and response records. [source: key-observations]
  The test of 403 logging covers the project's response to that status, not
  the vendor's expired-key behaviour.
- The maintainer reported that a key accepted by Datasets also received 429
  with the message suggesting an API key. If reproduced, that body cannot be
  used to identify anonymous traffic. [unverified] Retain a redacted keyed
  request and its response. [source: key-observations]
- The maintainer reported no `Retry-After` or rate-limit headers on the 429
  responses inspected. Clients should tolerate their absence, but their
  absence in future responses is not established. [unverified] Retain the
  response headers from a keyed 429. [source: key-observations]
- The maintainer reported throttling below the published pace: a new key
  passed 22/41 requests at 1.1–6-second spacing, an old key passed 11/20, and
  the deployed server exhausted its 1+2+4-second retry ladder on four of
  roughly 18 calls. No raw measurements are retained in this page and no
  cause was established. [unverified] Repeat a controlled, low-volume
  measurement if this precision becomes necessary. [source: key-observations]
  [source: throttle-observations]
- The maintainer reported that the Datasets dataset endpoint returned 401
  without a key, 403 with a fabricated or expired key, and 200 with an accepted
  key. [unverified] Retain redacted requests and responses before using this
  as a key diagnostic. [source: key-observations]
- Whether a valid key with no remaining quota is refused with 403 or 429 is
  unknown. [unverified] It needs an observed response from such a key.
- Whether a 429 request counts as activity for any key inactivity window is
  unknown. [unverified] It needs a vendor statement or controlled observation.

### Graph endpoint shape

- Paper search offers `minCitationCount` and `sort`, while
  `/paper/{paper_id}/citations` exposes `offset`, `limit`, `fields`, `year`,
  and `fieldsOfStudy` but no documented `minCitationCount` or `sort` parameter.
  Client-side citation-count filtering therefore requires scanning pages.
  [source: graph-docs]
  [pins: tests/test_tools_graph.py::test_get_citations_min_citations_paginates_to_find_results]
- The citations endpoint pages by `offset` and `limit`, with a documented
  maximum limit of 1,000; each data item contains `citingPaper`.
  [source: graph-docs] [pins: tests/test_s2_client.py::test_get_citations]
- Citation order is not documented as newest-first in the endpoint reference.
  [unverified] Confirm with a vendor guarantee or a dated, repeatable response
  sample before making correctness depend on that order.
- The maintainer reported `/author/{id}` ignoring `limit=3` and returning
  466 embedded `papers`; `/author/{id}/papers` is the documented paginated
  path. [unverified] Recheck the embedded-field behaviour with a retained
  response. [source: key-observations] [source: graph-docs]

### Paper types

- The issue records a keyed paper-batch response in which three conference
  papers carried both `JournalArticle` and `Conference`, and a journal control
  carried only `JournalArticle`. The pasted JSON has no retained transport
  provenance. [unverified] Recheck with a saved response before treating this
  as a general type rule. [source: type-observations]
- The venue names in that pasted sample contained none of `conference`,
  `proceedings`, `workshop`, or `symposium`. [unverified] Recheck the sample
  against a saved response. [source: type-observations]
- Whether another publication type should also map to `@inproceedings`, or
  whether `publicationTypes` can be `null`, was not established by that sample.
  [unverified] Check representative records or an explicit schema guarantee.

## Where this project departs from the subject

The current keyed `S2Client` sends requests 0.1 seconds apart, faster than the
published one-request-per-second introductory rate. #408 owns the correction.
The current retry ladder can still end with a 429; #409 owns deferral of that
call. The keepalive's 60-day assumption is not established by the sources
above and should not be treated as a vendor guarantee.

## Not covered

The vendor's private throttle algorithm, exact meaning of a valid key's quota
state, and ordering guarantees for citations remain unknown. The historical
issue observations also need retained evidence or repetition. No live Graph
requests were made for this research pass, to preserve the project's limited
API allowance.
