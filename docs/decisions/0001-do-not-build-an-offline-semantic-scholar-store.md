# ADR 0001: Do not build an offline Semantic Scholar store

- Status: Accepted
- Date: 2026-09-18
- Decision owner: Maintainer
- Evidence: [issue #406](https://github.com/pvliesdonk/scholar-mcp/issues/406)

## Context

Semantic Scholar throttling made a local copy of the Datasets API a possible
way to serve common lookups without a live request. Issue #406 measured the
available datasets and recorded that even a partial store would require tens
of gigabytes of compressed source data, while a citation graph would require
hundreds of gigabytes. Search and recommendation coverage would remain
uncertain.

The repository did not independently retain those vendor responses. The issue
is the evidence record for the measurements and marks unresolved causes and
coverage claims as unverified.

## Decision

Do not build an offline Semantic Scholar store. Keep Scholar MCP's resilience
work on the live API path through shared pacing, cooldowns, and deferred jobs.

## Consequences

- Operators do not need to provision or refresh a large local dataset.
- Semantic Scholar lookups still depend on the live service.
- Reconsider this decision if the vendor offers a materially smaller dataset,
  the required lookup coverage changes, or live API reliability changes enough
  to justify the storage and maintenance cost.
