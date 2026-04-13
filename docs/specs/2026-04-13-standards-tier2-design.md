# Standards Tier 2 + Enrichment Design Spec

**Date**: 2026-04-13
**Status**: Draft
**Milestone**: v0.9.0 (scholar-mcp#80–#85)
**Supersedes (architectural)**: the "Deferred issues" section of `docs/specs/2026-04-07-standards-support-design.md`

## Overview

Extends the Tier 1 standards framework (NIST, IETF, W3C, ETSI — already shipped) with
Tier 2 and Tier 3 coverage: ISO, IEC, IEEE, CEN/CENELEC, and Common Criteria. Adds an
out-of-band catalogue-sync mechanism that populates the local SQLite cache from
community-curated bulk dumps, avoiding paywalled HTML scraping at MCP-server runtime.
Integrates standards resolution into the existing `EnrichmentPipeline` so S2 citations
that look like standards references gain structured metadata.

### In scope

- ISO metadata lookup (scholar-mcp#80)
- IEC metadata lookup (scholar-mcp#81)
- IEEE metadata lookup (scholar-mcp#82)
- CEN/CENELEC metadata lookup (scholar-mcp#83) — harmonised-standards subset only
- Common Criteria portal integration (scholar-mcp#84)
- Standards auto-enrichment in `get_paper` / `get_references` / `get_citations` (scholar-mcp#85)

### Out of scope

- Price field population (all Tier 2 records carry `price=None`)
- Full CEN/CENELEC catalogue beyond CE-marking harmonised standards
- Tier 1 migration to Relaton (scholar-mcp#120 — separate investigation)
- IEEE Xplore authenticated full-text (F7 — future)
- Citation formatting (`@techreport` / `@manual` BibLaTeX) for `StandardRecord` (F4 — future)

## Design Decisions

- **Out-of-band sync via CLI.** A new `scholar-mcp sync-standards` subcommand materialises
  catalogue data from published dumps into the local cache. MCP-server runtime reads the
  cache exactly as it does for live-fetched records — no live scraping of paywalled
  catalogues. User runs sync on first install and schedules periodic refresh via cron /
  launchd / systemd timer.
- **Format-aligned loader modules.** Data-source format, not body, is the axis of
  implementation reuse. One `_sync_relaton.py` handles ISO, IEC, IEEE (all Relaton YAML);
  `_sync_cc.py` handles Common Criteria CSV + sec-certs JSON; `_sync_cen.py` handles
  EUR-Lex Formex XML plus a live-scrape fallback.
- **Single `standards` table for synced and live-fetched records.** Synced entries are
  indistinguishable from live-fetched entries at the record level — same `StandardRecord`
  shape, same cache-read paths. Only populate path changes.
- **Enrichment via existing `Enricher` protocol.** `StandardsEnricher` slots into the
  existing pipeline at phase 2, behaves identically to `CrossRefEnricher` /
  `OpenAlexEnricher`. Broad trigger (regex + body-prefix heuristic); cache-first resolve;
  attaches `standard_metadata` to matching records.
- **Joint-standard dedup via canonical identifier + alias rows.** ISO/IEC 27001 is stored
  once under canonical `ISO/IEC 27001:2022` with alias rows for `IEC 27001:2022` and
  `27001:2022`. CC↔ISO 15408 dual-identifier pairs write one record with both alias forms.
- **Longer cache TTLs.** `_STANDARD_INDEX_TTL` and `_STANDARD_SEARCH_TTL` bumped from 7 to
  30 days — standards are effectively append-only, and 7 days was over-conservative.
  Synced records don't TTL-expire at all; they're refreshed only via explicit re-sync.

## Module Layout

```
src/scholar_mcp/
  _standards_sync.py     # CLI entry + dispatcher + SyncReport type
  _sync_relaton.py       # shared YAML loader; config-driven (ISO, IEC, IEEE)
  _sync_cc.py            # Common Criteria CSV + sec-certs JSON
  _sync_cen.py           # EUR-Lex Formex XML + live-scrape fallback
  _enricher_standards.py # StandardsEnricher — plugs into EnrichmentPipeline
```

Only additive changes to `_standards_client.py`: `StandardsClient.search()` gains a
cache-first branch that queries the `standards` table by `body` + title/identifier `LIKE`
before falling back to live fetchers; `_fetchers["CEN"]` is registered pointing at the
live fallback helper in `_sync_cen.py`. No existing fetcher behaviour changes.

## CLI Surface

```
scholar-mcp sync-standards [--body ISO|IEC|IEEE|CEN|CC|all] [--force]
```

- `--body` defaults to `all`.
- Incremental by default: uses `If-Modified-Since` or commit-SHA comparison when upstream
  supports it, otherwise compares content hashes.
- `--force` bypasses incremental checks.
- Exit codes: `0` for no-changes or synced-with-updates; `3` for partial failure (some
  bodies succeeded, some failed); `1` for hard failure (no bodies synced).
- Output: one line per body on stdout (`body added=N updated=N withdrawn=N errors=N`) plus
  a final summary line. Verbose flag `-v` sets `FASTMCP_LOG_LEVEL=DEBUG`.

Designed for unattended operation under cron / CI / launchd.

## Cache Schema Changes

### Existing `standards` table — new columns

| Column | Type | Semantics |
|---|---|---|
| `source` | `TEXT` | `"IETF"|"NIST"|"W3C"|"ETSI"|"ISO"|"IEC"|"IEEE"|"CEN"|"CENELEC"|"CC"` |
| `synced_at` | `TEXT NULL` | ISO timestamp when set by sync; `NULL` for live-fetched |

Live-fetched records keep the 90-day TTL via the existing `cached_at` column (the
project-wide cache convention). Synced records (`synced_at NOT NULL`) are **never
TTL-expired**; they're refreshed only by a subsequent sync that sees a later upstream
SHA / `Last-Modified`.

### New `standards_sync_runs` table

| Column | Type |
|---|---|
| `body` | `TEXT PRIMARY KEY` (one row per body; updated per run) |
| `started_at` | `REAL` — Unix epoch seconds, consistent with `cached_at` elsewhere |
| `finished_at` | `REAL` — Unix epoch seconds |
| `upstream_ref` | `TEXT` — commit SHA, `Last-Modified`, or similar |
| `added` | `INTEGER` |
| `updated` | `INTEGER` |
| `unchanged` | `INTEGER` |
| `withdrawn` | `INTEGER` |
| `errors` | `TEXT NOT NULL` (JSON array of error strings; `"[]"` on success) |

`started_at` / `finished_at` are floats (Unix epoch), matching
`SyncReport.started_at: float` and `cached_at REAL` on the sibling
`standards` / `books` / `papers` tables. MCP tools and JSON serialisation
render them as numeric timestamps — agents can format them locally as
needed.

Backs a new `get_sync_status` MCP tool/resource that surfaces per-body freshness.

### Existing TTL constants

```python
_STANDARD_TTL          = 90 * 86400  # unchanged — live-fetched record expiry
_STANDARD_ALIAS_TTL    = 90 * 86400  # unchanged
_STANDARD_SEARCH_TTL   = 30 * 86400  # bumped 7 → 30
_STANDARD_INDEX_TTL    = 30 * 86400  # bumped 7 → 30
```

## Sync Subsystem

### Loader protocol

```python
class Loader(Protocol):
    body: str

    async def sync(
        self, cache: CacheProtocol, *, force: bool = False
    ) -> SyncReport: ...


@dataclass
class SyncReport:
    body: str
    added: int
    updated: int
    unchanged: int
    withdrawn: int
    errors: list[str]
    upstream_ref: str
    started_at: datetime
    finished_at: datetime
```

The dispatcher in `_standards_sync.py` runs all selected loaders concurrently (one
`asyncio.Task` per body), aggregates reports, writes one row per body to
`standards_sync_runs`, and prints the stdout summary.

### `_sync_relaton.py` — shared YAML loader

Covers ISO, IEC, IEEE via a body-config table:

```python
_RELATON_BODIES = {
    "ISO":  RelatonConfig(repo="relaton/relaton-data-iso",     branch="main"),
    "IEC":  RelatonConfig(repo="relaton/relaton-data-iec",     branch="main"),
    "IEEE": RelatonConfig(repo="ietf-tools/relaton-data-ieee", branch="main"),
}
```

Per-body sync loop:

1. Resolve current commit SHA via GitHub API
   (`GET /repos/{repo}/commits/{branch}`). If it equals the
   `standards_sync_runs.upstream_ref` for this body and `not force`, report `unchanged`.
2. Stream-download tarball from `/repos/{repo}/tarball/{sha}`. Don't persist raw YAML to
   disk — extract in-process.
3. For each `data/*.yaml`: parse, map Relaton `BibliographicItem` → `StandardRecord`,
   upsert via `cache.set_standard()`, and write `cache.set_standard_alias()` for every
   `docidentifier` variant.
4. Compute withdrawn set: identifiers present in the previous SHA's key set but absent in
   the current → upsert with `status="withdrawn"`. Never delete — citations may still
   reference withdrawn standards.

### Relaton → `StandardRecord` field mapping

| Relaton field | `StandardRecord` field |
|---|---|
| `docidentifier[type=primary]` | `identifier` |
| `docidentifier[*]` (other types) | written to `standards_aliases` |
| `title[0].content` | `title` |
| `date[type=published].value` | `published_date` |
| `status.stage` | `status` (mapped: `60.60`→`published`, `95.99`→`withdrawn`, `90.xx`→`superseded`) |
| `relation[type=obsoletes].bibitem.docidentifier` | `supersedes[]` |
| `relation[type=obsoleted-by]` | `superseded_by` |
| `abstract[0].content` | `scope` |
| `editorialgroup.technical-committee` | `committee` |
| `link[type=src]` | `url` |
| `link[type=obp]`, `link[type=pub]` | `full_text_url` (may be `None` for paywalled) |

`price` is absent from Relaton — always `None` for Tier 2 synced entries.
`full_text_available` is `False` for ISO / IEC / IEEE; `True` only when `full_text_url`
points to a freely accessible document (rare for Tier 2).

### `_sync_cc.py` — Common Criteria

Two upstream sources merged under `body="CC"`:

1. **Certified products** — `https://www.commoncriteriaportal.org/products/certified_products.csv`.
   `If-Modified-Since`-gated. Columns map to `identifier = f"CC Cert {scheme}-{name}"`,
   `status="certified"` or `"archived"` (based on `Archived Date`),
   `full_text_url = Cert Report URL`, `published_date = Cert Date`.
2. **Protection Profiles** — `crocs-muni/sec-certs` weekly JSON (MIT-licensed). Maps to
   separate PP records with `identifier = f"CC PP {scheme}-{name}"`.

Cross-identifier aliasing: each CC record writes alias rows for `CC:2022` / `CC:2017` and
a dual-write under `ISO/IEC 15408` when the PP/cert references it (sec-certs JSON field
`cc_version`). Satisfies scholar-mcp#84's "cross-link CC:2022 and ISO/IEC 15408"
requirement.

Full text for CC is freely downloadable; `full_text_available=True` for all CC records.

### `_sync_cen.py` — EUR-Lex Formex XML + live fallback

Walks the EU Commission's published Implementing Decisions for each directive that cites
harmonised standards (MD, EMC, RED, MDR, GPSR, CRA, …). Downloads each Formex XML from
EUR-Lex, extracts the standards-list annex, maps each row to a `StandardRecord`:

- `body="CEN"` for `EN` prefix, `body="CENELEC"` for `EN IEC` / `EN ISO` prefix.
- `identifier = f"EN {number}:{year}"` (canonical form).
- `status`: `"harmonised"` for active listings; `"withdrawn"` when a later decision
  removes them.
- `supersedes` / `superseded_by` populated from cross-references in the decision.

**Live fallback** — for citations referencing non-harmonised ENs, a `Fetcher`-shaped
helper (`_live_get(identifier)`) inside `_sync_cen.py` is registered as
`StandardsClient._fetchers["CEN"]`:

- Single HTTP GET to `https://standards.cencenelec.eu/…/search?q={identifier}`.
- Parse first result via `selectolax` / `lxml`.
- Rate limit 2 req/s.
- On error / empty response: return stub `StandardRecord(identifier=..., body="CEN", title="", full_text_available=False)` — same "resolved-locally-but-fetch-failed" pattern as Tier 1 uses today.
- Successful live fetches cached as 90-day-TTL live records (not synced records).

Full CEN/CENELEC catalogue beyond harmonised standards is explicitly out of scope.

## Identifier Canonicalisation

`resolve_identifier_local` in `_standards_client.py` gains regex groups for Tier 2 bodies.
Joint and cross-referenced identifiers resolve to a canonical form:

| Input forms | Canonical | Body |
|---|---|---|
| `ISO 9001:2015`, `ISO9001:2015`, `iso 9001 2015` | `ISO 9001:2015` | `ISO` |
| `ISO/IEC 27001:2022`, `IEC 27001:2022`, `27001:2022` | `ISO/IEC 27001:2022` | `ISO/IEC` |
| `IEC 62443-3-3:2020`, `62443-3-3:2020` | `IEC 62443-3-3:2020` | `IEC` |
| `IEEE 802.11-2020`, `IEEE Std 802.11-2020` | `IEEE 802.11-2020` | `IEEE` |
| `EN 303 645`, `ETSI EN 303 645` | `ETSI EN 303 645` | `ETSI` (existing rule kept) |
| `EN 55032:2015` | `EN 55032:2015` | `CEN` |
| `CC:2022`, `ISO/IEC 15408:2022` | `ISO/IEC 15408:2022` (with CC alias) | `ISO/IEC` |

ETSI priority over CEN is preserved — the existing `_ETSI_RE` requires an explicit `ETSI`
prefix specifically to avoid false positives with other European bodies.

Joint ISO/IEC standards always use the canonical `ISO/IEC {n}` form, regardless of which
body's dump introduced them. When IEC sync encounters an entry with
`docidentifier[type=ISO]=ISO/IEC 27001:2022` and ISO sync already wrote the same
canonical key, the loaders upsert with merged aliases (union) and the later `synced_at`.
No duplicate records.

## Enrichment Integration

### `_enricher_standards.py` — `StandardsEnricher`

```python
class StandardsEnricher:
    name = "standards"
    phase = 2                                    # after phase 0 (OpenAlex, CrossRef) and
                                                 # phase 1 (OpenLibrary, GoogleBooks)
    tags = frozenset({"paper", "reference"})

    def can_enrich(self, record: dict[str, Any]) -> bool:
        # True when a citation-ish string in the record matches a standards pattern.
        # Inspects "citation", "title", "unstructured" in order. Uses
        # _looks_like_standard(): regex match OR body-prefix heuristic.
        ...

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        # 1. Extract standards-shaped tokens via _extract_standard_tokens()
        # 2. For each token: resolve via bundle.standards.resolve() (cache-first)
        # 3. Unique resolution  → record["standard_metadata"] = StandardRecord
        # 4. Ambiguous          → record["standard_candidates"] = [StandardRecord, ...]
        # 5. Unresolved         → no-op (silent)
        # Cold-cache guard: if >3 live fetches would be triggered in this call,
        # log and skip the remainder.
```

Registered in `_build_enrichment_pipeline()` alongside existing enrichers. Phase 2 lets
phase 0 (OpenAlex, CrossRef) and phase 1 (OpenLibrary, GoogleBooks) complete first —
some S2 references only become recognisable as standards after DOI/title enrichment.

### Trigger — `_looks_like_standard(text)`

Two signals, OR-combined:

1. **Regex match** via the extended `resolve_identifier_local` (NIST, IETF, W3C, ETSI
   from today plus new ISO, IEC, IEEE, CEN, CC groups).
2. **Body-prefix heuristic** — tokens in `{"ISO", "IEC", "IEEE", "NIST", "RFC", "ETSI", "CC:", "FIPS", "WCAG", "CEN"}` appearing at word boundaries in the first ~40 characters.

Deliberately broad. False positives (text matches prefix but doesn't actually reference a
standard) cost one cache-lookup that returns `None`. False negatives (real standard
reference missed) leave the record unenriched — worse.

### Attachment point

Two new optional TypedDict fields added to a thin extension of S2 paper/reference
record typing in `_record_types.py` (kept as documentation; paper records remain
`dict[str, Any]` at runtime per the existing `EnrichableRecord` convention):

```python
# Extension conventions for enriched paper / reference dicts:
#   standard_metadata:   StandardRecord | None    # populated on unambiguous resolve
#   standard_candidates: list[StandardRecord]     # populated on ambiguous resolve
```

Downstream tools (`get_paper`, `get_references`, `get_citations`) serialise whatever's
present — no changes to their return shape beyond passing enricher output through.

### Cache-aware resolution

`bundle.standards.resolve()` already cache-reads via `get_standard_alias` /
`get_standard`. Post-sync, the vast majority of resolutions hit the cache without
network. Cold-cache guard: if a single `enrich()` call would trigger >3 live fetches
(indicating the user hasn't run `sync-standards`), log
`standards_enrichment_cold_cache references=%s` once per tool call and skip the remainder.
Protects upstream APIs from a one-off `get_citations` hammering them when the cache
is empty.

## Testing

### Unit tests — offline fixtures only for CI

```
tests/
  fixtures/standards/
    relaton_iso_sample/         # ~20 YAML files (joint + plain)
    relaton_iec_sample/
    relaton_ieee_sample/
    cc_certified_products.csv   # ~30 trimmed rows (archived + active)
    cc_sec_certs_pps.json       # ~10 PPs (CC:2017 + CC:2022)
    eurlex_md_decision.xml      # one Machinery Directive Formex XML
  test_sync_relaton.py
  test_sync_cc.py
  test_sync_cen.py
  test_standards_sync.py        # dispatcher + CLI + SyncReport
  test_enricher_standards.py
```

Coverage targets:

- **Relaton loader**: cold sync → N added; same SHA re-sync → zero added/updated;
  modified fixture → update detected; identifier removal → `withdrawn` marker;
  joint-standard dedup between ISO + IEC syncs.
- **CC**: CSV parse → correct `StandardRecord` shape; `ISO/IEC 15408` alias written
  alongside `CC:2022`; sec-certs PP merge; archived status derived from `Archived Date`.
- **CEN**: Formex XML → harmonised EN records with correct prefix-to-body mapping; live
  fallback mocked via `respx` returns stub on HTTP error.
- **Dispatcher**: CLI `--body all` runs loaders concurrently; partial-failure exit code 3;
  `standards_sync_runs` row written per body.
- **Enricher**: broad trigger matches regex and prefix forms; no false positive on "ISO
  9000 compliance" as paper title without identifier structure; unique → `standard_metadata`;
  ambiguous → `standard_candidates`; cold-cache guard throttles after 3 unresolved.

HTTP mocking uses `respx` per existing test convention.

### Integration smoke tests — `pytest -m live`

One test per body that hits the real upstream. Skipped by default, run nightly via a
dedicated CI job. Catches upstream schema drift. Not counted toward the 80% patch-coverage
gate.

## Documentation

Per CLAUDE.md hard gate: `README.md` and `docs/**` updated in the same commit as code
changes.

- **`README.md`** — new "Tier 2 standards" subsection under Features; `scholar-mcp
  sync-standards` in Quick Start; note first sync is a one-time multi-minute operation.
- **`docs/guides/standards.md`** (new) — tier taxonomy, sync cadence recommendations
  (weekly cron suggested), scheduling examples for cron / launchd / systemd timer,
  troubleshooting (empty results → run sync).
- **`docs/tools/index.md`** — `search_standards` / `get_standard` /
  `resolve_standard_identifier` behaviour updates; new `get_sync_status` tool/resource.
- **`docs/specs/2026-04-07-standards-support-design.md`** — mark the "Deferred issues"
  section as superseded by this spec.
- **`docs/ops/standards-sync.md`** (new) — operational guidance for production deployments.
- **`.claude-plugin/plugin/skills/scholar-workflow/SKILL.md`** — update standards workflow
  section to reflect Tier 2 + Tier 3 coverage.

## Rollout

Five PRs, each independently shippable under the CLAUDE.md hard gates (CI, lint, mypy,
≥80% patch coverage, docs, manifest version lockstep):

1. **PR 1 — Sync infrastructure.** `_standards_sync.py`, `SyncReport`, CLI subcommand,
   `standards.source` + `standards.synced_at` columns, `standards_sync_runs` table, new
   `get_sync_status` tool, TTL constant bumps. Dispatcher works; zero loaders registered.
   Green CI.
2. **PR 2 — scholar-mcp#80 + scholar-mcp#81 (ISO + IEC).** Shared Relaton loader. ISO /
   IEC body config. Extended `resolve_identifier_local` regex. Joint-standard dedup
   implemented + tested. Fixtures for both.
3. **PR 3 — scholar-mcp#82 (IEEE).** Reuses PR 2's Relaton loader; trivial config addition
   (`ietf-tools/relaton-data-ieee`) + regex group. Fixtures.
4. **PR 4 — scholar-mcp#83 + scholar-mcp#84 (CEN/CENELEC + Common Criteria).**
   `_sync_cc.py` (CSV + sec-certs JSON + cross-ID aliasing). `_sync_cen.py` (Formex
   harvester + live fallback). Pairs because neither uses Relaton.
5. **PR 5 — scholar-mcp#85 (enrichment).** `_enricher_standards.py` wired into
   `_build_enrichment_pipeline`. New TypedDict attachment-field conventions documented
   in `_record_types.py`. Cold-cache guard. Final minor-version bump (v0.9.0 release
   tag).

Each PR bumps the patch version in `server.json`,
`.claude-plugin/plugin/.claude-plugin/plugin.json`, and `.mcp.json`.

## Risks & Mitigations

- **Relaton licensing.** No SPDX declared. We consume at runtime (safe) but do not
  redistribute a derived snapshot. If licensing concerns arise, fall back to live
  fetchers plus opportunistic ISO Open Data (official, redistributable). Tracked as a
  note in scholar-mcp#120.
- **Relaton coverage gaps.** Spot-check the ISO dump against a sample of well-known
  standards (ISO 27001, ISO 9001, ISO/IEC 15408) in PR 2's tests to confirm field
  fidelity before relying on it.
- **Upstream schema drift.** Nightly `pytest -m live` smoke tests catch it early. Sync
  reports error-count per body; a bad sync leaves the previous cache intact rather than
  corrupting it.
- **Cold-cache hammer.** The enricher's cold-cache guard caps live fetches per call.
- **CEN live fallback brittleness.** Live fallback is already a known-fragile pattern
  (see pvliesdonk/scholar-mcp#102 ETSI Cloudflare). Stub records on failure keep the
  resolver path non-blocking for the enricher. If CEN adds Cloudflare, the Formex-XML
  harmonised subset is still usable — only non-harmonised ENs degrade to `not_found`.
