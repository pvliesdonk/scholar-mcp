---
type: Reference
title: OpenAlex API keys and limits
description: How OpenAlex authenticates a request, what a key changes, and how it refuses a request over budget or with a key it rejects.
subject_version: "OpenAlex help pages, last updated 2026-11-03"
valid_for: "The OpenAlex API access model as documented in November 2026"
generated:
  by: process:researching-references
  at: 2026-11-12T15:33:33+00:00
stale_after: 2027-05-12T00:00:00+00:00
status: draft
sources:
  - id: auth
    title: OpenAlex help, "Rate limits and authentication"
    resource: https://help.openalex.org/how-to-use-the-api/rate-limits-and-authentication
    accessed: 2026-11-12
  - id: pricing
    title: OpenAlex help, "Pricing"
    resource: https://help.openalex.org/access/pricing/
    accessed: 2026-11-12
  - id: costs
    title: OpenAlex help, "Example costs"
    resource: https://help.openalex.org/access/example-costs/
    accessed: 2026-11-12
  - id: errors
    title: OpenAlex help, "Errors"
    resource: https://help.openalex.org/api/errors/
    accessed: 2026-11-12
  - id: old-docs
    title: ourresearch/openalex-docs (archived 2026-07-23)
    resource: https://github.com/ourresearch/openalex-docs
    accessed: 2026-11-12
---

# OpenAlex API keys and limits

How OpenAlex decides whether to serve a request: the key, the budget, and the
refusals. Scholar MCP makes one kind of OpenAlex call, a single work looked up
by DOI. This page covers what that call depends on.

## Scope

- Covers: passing a key, per-second and daily limits with and without one,
  what a DOI lookup costs, the 403 and 429 refusals, the `mailto` polite pool.
- Does not cover: the work object (see
  [OpenAlex work objects](openalex-works.md)), search, paging, OQL, content
  downloads.
- Depended on by: `src/scholar_mcp/domain.py` (`_open_clients`),
  `src/scholar_mcp/_openalex_client.py` (`get_by_doi`, `OpenAlexRefusedError`).

## Claims

### Passing a key

- A key is passed either as an `api_key` query parameter or as
  `Authorization: Bearer <key>`; the page documents both forms. [source: auth]
  [pins: tests/test_openalex_auth.py::test_key_is_sent_to_openalex_only]
- A key is created on an openalex.org account (signup at
  `https://openalex.org/signup`, key at `https://openalex.org/settings/api-key`).
  [source: auth]
- A key works only after its owner clicks an emailed activation link; until
  then "Requests with it get a 403 with the code key_not_activated."
  [source: auth] [pins: tests/test_openalex_client.py::test_get_by_doi_403_is_refused_not_absent]
- `POST https://api.openalex.org/api-keys` with an `email` returns a key in
  `pending_activation` state and mails the activation link. [source: auth]
  Scholar MCP does not use it (see below).

### Limits and budget

- Per-second limits: 10 requests/s without a key, 30 with a free key or
  prepaid usage, 50 on an annual plan. [source: auth]
- "Every account gets $1 of API usage per day for free"; without a key the
  daily budget is $0.10, a tenth of that. [source: pricing] [source: costs]
- The daily budget resets at midnight UTC. [source: auth]
- Getting a single entity by ID or DOI is free; a list call costs 1 credit and
  a search 10. [source: costs]
- Every response carries `X-RateLimit-Limit`, `X-RateLimit-Remaining`,
  `X-RateLimit-Credits-Used` and `X-RateLimit-Reset`. [source: errors]

### Refusals

- Exceeding the per-second limit or the daily budget returns
  `429 Too Many Requests` with a `Retry-After` header. [source: errors]
  [pins: tests/test_openalex_client.py::test_get_by_doi_429_is_refused_and_retryable]
- 4xx and 5xx responses cost no credits. [source: errors]
- An error body has the shape `{"error": "...", "message": "..."}`. [source: errors]
- The response to a malformed or unknown key is not documented.
  [unverified] A request with a made-up key would settle it.

### The `mailto` polite pool

- The current help pages do not mention `mailto` or a polite pool; the
  archived docs repository still describes both, alongside a 100,000-calls-a-day
  limit that the current pages contradict. [source: auth] [source: old-docs]
- Whether OpenAlex still treats `mailto` specially is [unverified]. Comparing
  the rate-limit headers of a keyless request with and without `mailto` would
  settle it.

## Where this project departs from the subject

- Scholar MCP sends the key only as a Bearer header, never as `api_key=`, so
  the key stays out of URLs and request logs.
  [pins: tests/test_openalex_auth.py::test_key_is_sent_to_openalex_only]
- Scholar MCP does not create keys through `POST /api-keys`. The key arrives
  as `SCHOLAR_MCP_OPENALEX_API_KEY`, and a key the server created could not
  be written back to the environment (#619).
- Scholar MCP keeps sending `mailto:<contact_email>` in its User-Agent, which
  costs nothing whether or not OpenAlex still reads it.

## Not covered

- The status and body for an invalid (not merely unactivated) key.
- Whether a 403 for a disabled or revoked key carries its own `error` code.
