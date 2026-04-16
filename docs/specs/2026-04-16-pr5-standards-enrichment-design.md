# PR 5 — Standards Auto-Enrichment

**Date:** 2026-04-16
**Closes:** scholar-mcp#85
**Builds on:** All prior v0.9.0 PRs (#121, #122, #126, #130, #136, #140) — the full standards infrastructure
**Follow-ups filed:** scholar-mcp#141 (standard_candidates for ambiguous matches), #142 (CrossRef-corrected title at phase 1)

## Context

This is the final PR in the v0.9.0 standards rollout. PRs 1–4b shipped the sync infrastructure and all body-specific loaders (ISO, IEC, IEEE, CC, CEN). PR 5 wires the standards metadata into the paper-processing pipeline so citations that look like standards references automatically get structured metadata attached.

## Summary

Add `StandardsEnricher` to the existing `EnrichmentPipeline`. When `get_citations`, `get_references`, or `get_citation_graph` return S2 citation records, the enricher checks each citation's `title` field. If the title is predominantly a standards identifier (regex match consuming >50% of the title text), it calls `StandardsClient.get(identifier)` and attaches the result as `record["standard_metadata"]` — a `StandardRecord` dict with identifier, title, body, status, full-text URL, etc.

## Design Decisions

### Strict trigger: >50% title coverage heuristic

`resolve_identifier_local(title)` returns a canonical identifier and body. The enricher compares `len(canonical)` to `len(title.strip())` — if the canonical form covers more than half the title, the citation IS a standard (e.g., `"RFC 9000"` = 100%, `"NIST SP 800-53 Rev. 5"` = 100%). A citation titled `"Implementing ISO 27001 in healthcare: a systematic review"` = ~20% coverage → skip (it's a paper ABOUT the standard, not a citation OF it).

This prevents false positives: the enricher only fires on citations that ARE standards, not papers that mention standards. LLM consumers can trust `standard_metadata` as high-confidence.

### Phase 0, tags `{"papers"}`

Standards detection is independent of CrossRef/OpenAlex results — it examines the S2 title directly. Running at phase 0 means standards metadata is available for any phase-1 enricher. S2 doesn't mangle the short, structured titles that standards citations have (e.g., `"ISO 9001:2015"`, `"RFC 9000"`), so CrossRef correction isn't needed.

### No cold-cache guard

Tier 2 cache-only fetchers (CC, CEN) return `None` instantly — no network cost. Relaton live-fetch (ISO/IEC/IEEE) does one cheap GitHub raw GET per miss. The pipeline's existing `concurrency=10` semaphore + per-fetcher rate limiters already throttle. Adding a miss counter adds complexity for a scenario that resolves itself once `sync-standards` runs.

### `standard_metadata` as a dynamic dict field

Same pattern as `crossref_metadata` — a dynamic field on the paper dict. No `_record_types.py` changes. The field contains a `StandardRecord`-shaped dict: `identifier`, `title`, `body`, `status`, `full_text_url`, `full_text_available`, `published_date`, `url`, `related`, etc.

## Module Changes

| File | Change |
|---|---|
| `src/scholar_mcp/_enricher_standards.py` | **New** — `StandardsEnricher` class implementing the Enricher protocol |
| `src/scholar_mcp/_server_deps.py` | Register `StandardsEnricher()` in `_build_enrichment_pipeline()` |
| `tests/test_enricher_standards.py` | **New** — trigger heuristic tests, enrichment tests, registration test |
| `README.md` | Mention auto-enrichment of standards citations |
| `docs/guides/standards.md` | New "Auto-enrichment" section |

No changes to: `_record_types.py`, `_standards_client.py`, `_sync_*.py`, `_relaton_live.py`, `_cache.py`, `_protocols.py`.

## `StandardsEnricher` Interface

```python
class StandardsEnricher:
    name = "standards"
    phase = 0
    tags = frozenset({"papers"})

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """True when the citation title is predominantly a standards identifier.

        Checks:
        1. No existing standard_metadata (skip re-enrichment).
        2. Title is non-empty.
        3. resolve_identifier_local matches.
        4. Canonical identifier covers >50% of the title text.
        """

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Resolve the standards identifier and attach metadata.

        Calls bundle.standards.get(canonical_identifier). If the
        standard is found (cache hit or live-fetch success), sets
        record["standard_metadata"] to the StandardRecord dict.
        If not found, does nothing (no error, no stub).
        """
```

## Data Flow

```
get_citations("paperId")
  → S2 returns N citations as dicts
  → EnrichmentPipeline.enrich(citations, tags={"papers"})
    → Phase 0 (concurrent, semaphore=10):
        OpenAlexEnricher — adds venue
        CrossRefEnricher — adds crossref_metadata
        StandardsEnricher — for each citation:
            title = record["title"]
            match = resolve_identifier_local(title)
            if match and len(canonical) > 0.5 * len(title):
                standard = await bundle.standards.get(canonical)
                if standard:
                    record["standard_metadata"] = standard
    → Phase 1:
        OpenLibraryEnricher — book lookups
        GoogleBooksEnricher — book cover/snippet
  → Return enriched citations to caller
```

## Error Handling

**No custom error handling needed.** The `EnrichmentPipeline` wraps every `enrich()` call in a try/except that logs at DEBUG and moves on. If `bundle.standards.get()` raises (httpx timeout, unexpected schema), the pipeline catches it — the citation record simply doesn't get `standard_metadata`. No crash, no degraded response for the other citations.

Within `StandardsEnricher.enrich()`:
- `resolve_identifier_local` is pure (no exceptions).
- `bundle.standards.get()` can raise `httpx.HTTPError` — caught by pipeline.
- Cache-miss → `None` return → no field attached. Not an error.

## Testing

### `tests/test_enricher_standards.py` (new)

**Trigger heuristic (`can_enrich`):**
- `test_can_enrich_short_standard_title` — `"RFC 9000"` → True
- `test_can_enrich_iso_standard_title` — `"ISO 9001:2015"` → True
- `test_can_enrich_nist_sp_title` — `"NIST SP 800-53 Rev. 5"` → True
- `test_can_enrich_long_paper_title_about_standard` — `"Implementing ISO 27001 in healthcare: a systematic review"` → False
- `test_can_enrich_already_enriched_skips` — record with `standard_metadata` present → False
- `test_can_enrich_empty_title` — `""` or missing title → False
- `test_can_enrich_no_match` — `"Machine learning for anomaly detection"` → False

**Enrichment (`enrich`):**
- `test_enrich_attaches_standard_metadata` — mock `bundle.standards.get()` returning a StandardRecord → `record["standard_metadata"]` populated with correct fields
- `test_enrich_cache_miss_no_metadata` — `bundle.standards.get()` returns `None` → `"standard_metadata"` key absent
- `test_enrich_skips_when_no_match` — title without standards pattern → no side effects

**Integration:**
- `test_enricher_registered_in_pipeline` — verify `StandardsEnricher` appears in the pipeline's phase-0 enrichers via `_build_enrichment_pipeline()` or equivalent
- `test_enricher_conforms_to_protocol` — verify the enricher satisfies the Enricher protocol (has all required attributes/methods)

## PR Layout

Single PR, three ordered commits:

1. `feat(standards): StandardsEnricher for auto-enrichment of citation records` — `_enricher_standards.py` + tests + `_server_deps.py` registration
2. `docs(standards): auto-enrichment in README and standards guide`
3. (If needed) `test(standards): additional enricher coverage`

## Acceptance Gates

- [ ] CI green
- [ ] Lint + format + mypy clean
- [ ] Codecov patch coverage ≥ 80%
- [ ] README + docs updated
- [ ] PR description closes #85; references #141 / #142

## Out of Scope

Filed as follow-ups:

- **#141** — `standard_candidates` field for ambiguous multi-match enrichment
- **#142** — Enrich from CrossRef-corrected title at phase 1

Explicitly **not** doing:

- Changes to `StandardRecord` TypedDict
- Changes to `StandardsClient`
- Any new MCP tools (enrichment is automatic, not tool-invoked)
- Price field population
- Full-text retrieval (just metadata attachment; the LLM uses `full_text_url` to fetch if needed)
