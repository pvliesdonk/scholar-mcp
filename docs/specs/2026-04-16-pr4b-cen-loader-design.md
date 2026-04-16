# PR 4b — CEN/CENELEC Harmonised Standards Loader

**Date:** 2026-04-16
**Closes:** scholar-mcp#83
**Builds on:** scholar-mcp#121 (sync infrastructure), #136 (CC loader pattern)
**Follow-ups filed:** scholar-mcp#137 (EUR-Lex Formex XML parser), #138 (live scrape fallback), #139 (quarterly table review)

## Context

The v0.9.0 rollout originally bundled CEN/CENELEC + Common Criteria into one PR. They were split into PR 4a (CC, merged as #136) and PR 4b (CEN, this spec). This is the last body-specific loader before the enrichment PR (#85).

## Summary

Ship CEN/CENELEC harmonised standards as a Tier 2 sync-only body using a hard-coded table of ~100-200 standards from the major EU directives. CEN has no reliable structured data source (EUR-Lex Formex XML is fragile, the CEN portal returns 500s, the NANDO→SMCS migration is incomplete), so a curated constant table is the pragmatic approach — same pattern as CC's framework documents but larger.

## Scope Decisions

### Hard-coded table, not Formex XML

EUR-Lex endpoints returned empty/202 during research. The CEN/CENELEC portal at `standards.cencenelec.eu` returns HTTP 500. The new EU Single Market Compliance Space is an Angular SPA with no public API. Rather than building a fragile parser against unstable government infrastructure, we ship a curated `_HARMONISED_STANDARDS` constant covering the standards that EU-regulation-focused academic papers most commonly cite.

The table needs quarterly review when new implementing decisions publish (#139). If EUR-Lex stabilises, #137 (Formex XML parser) replaces the table entirely.

### Single body `"CEN"` for everything

CEN and CENELEC are technically separate organisations, but from a citation-resolution perspective the distinction adds no value for the LLM consumer. All European Norms use the `EN` prefix regardless of publisher. `body="CEN"` covers everything; `search(body="CEN")` returns all ENs.

### No cross-linking to ISO/IEC records

Many EN standards are adoptions of ISO or IEC standards (`EN ISO 13849-1:2023` = `ISO 13849-1:2023`). Unlike the CC ↔ ISO 15408 case, the EN adoption doesn't add a free PDF (both are paywalled), so the cross-link provides no paywall-bypass value. The `EN ISO` prefix is self-documenting — the LLM can strip it if it wants the ISO record. No `related` field population, no ISO loader denylist, no dual-write.

### Sync-only, cache-only `_CENFetcher`

CEN has no live API. The Tier 2 design proposed scraping `standards.cencenelec.eu`, but the site is unreliable and paywalled stubs add no value. `_CENFetcher` mirrors `_CCFetcher`: cache-only `.get()` with WARNING log on miss, `.search()` delegates to `search_synced_standards(source="CEN")`.

## Module Changes

| File | Change |
|---|---|
| `src/scholar_mcp/_sync_cen.py` | **New** — `HarmonisedStandard` dataclass, `_HARMONISED_STANDARDS` constant (~100-200 entries), `_hs_to_record` mapper, `CENLoader` class (iterates table, content-hash gate for idempotency) |
| `src/scholar_mcp/_standards_client.py` | Add EN regex groups (`_EN_ISO_IEC_RE`, `_EN_ISO_RE`, `_EN_IEC_RE`, `_EN_RE`); `_CENFetcher` class; register `_fetchers["CEN"]` |
| `src/scholar_mcp/cli.py` | Extend `_select_loaders` with `CENLoader()` |
| `tests/test_sync_cen.py` | **New** — table integrity tests, record builder tests, loader integration tests |
| `tests/test_standards_client.py` | EN regex tests + `_CENFetcher` tests |
| `tests/test_cli_sync_standards.py` | `--body CEN` and `--body all` tests |
| `README.md` | Add CEN to supported bodies |
| `docs/guides/standards.md` | CEN section |

No changes to: `_cache.py`, `_protocols.py`, `_server_deps.py`, `_relaton_live.py`, `_sync_relaton.py`, `_sync_cc.py`.

## Data Model

```python
@dataclass(frozen=True)
class HarmonisedStandard:
    """One entry in the hard-coded harmonised-standards table.

    Attributes:
        identifier: Canonical EN form, e.g. ``"EN 55032:2015"``,
            ``"EN ISO 13849-1:2023"``.
        title: Full title of the standard.
        directive: EU directive shorthand (``"EMC"``, ``"RED"``,
            ``"Machinery"``, ``"CRA"``, ``"MDR"``, ``"GPSR"``).
        status: ``"harmonised"`` for active OJ listings,
            ``"withdrawn"`` for standards removed by a later decision.
        published_date: ISO-format date or None.
    """
```

All records map to:
- `body="CEN"`, `source="CEN"`
- `full_text_available=False` (CEN standards are paywalled)
- `price=None` (per Tier 2 design — no price population)
- `url=""` (no canonical catalogue URL; CEN portal is unreliable)

## Data Flow

### Sync (`scholar-mcp sync-standards --body CEN`)

```
CENLoader.sync(cache):
    table_hash = SHA256(sorted table identifiers + statuses)
    prev = cache.get_sync_run("CEN")
    if not force and prev.upstream_ref == table_hash:
        return SyncReport(unchanged=N)  # short-circuit

    prev_ids = cache.list_synced_standard_ids(source="CEN")
    current_ids = set()
    for entry in _HARMONISED_STANDARDS:
        record = _hs_to_record(entry)
        current_ids.add(record["identifier"])
        cache.set_standard(record["identifier"], record, source="CEN", synced=True)

    # Withdrawal: prev_ids - current_ids are standards removed from the
    # table (code change). Same >50% guard for safety.
    missing = prev_ids - current_ids
    if prev_ids and len(missing) > 0.5 * len(prev_ids):
        errors.append("withdrawal aborted: >50% missing")
    else:
        for ident in missing:
            mark as withdrawn

    report.upstream_ref = table_hash
    return report
```

### Live fetch — none

`_CENFetcher.get(identifier)` → cache hit or `None` + WARNING log.

## Identifier Resolution

EN regex groups in `resolve_identifier_local`, checked **after** the existing ETSI block (ETSI requires explicit `ETSI` prefix, so `EN 55032:2015` won't false-positive into ETSI):

```
_EN_ISO_IEC_RE  — "EN ISO/IEC 27001:2022"   → ("EN ISO/IEC 27001:2022", "CEN")
_EN_ISO_RE      — "EN ISO 13849-1:2023"      → ("EN ISO 13849-1:2023", "CEN")
_EN_IEC_RE      — "EN IEC 62443-3-3:2020"    → ("EN IEC 62443-3-3:2020", "CEN")
_EN_RE          — "EN 55032:2015"            → ("EN 55032:2015", "CEN")
```

Ordering: `EN ISO/IEC` before `EN ISO` before `EN IEC` before plain `EN` (most-specific first). All placed after CC and ETSI blocks, before ISO/IEC/IEEE blocks.

**Regression guard:** `ETSI EN 303 645` must still dispatch to `"ETSI"` (existing `_ETSI_RE` has explicit `ETSI` prefix so it wins by position).

## Error Handling

Minimal — no HTTP, no external data source.

- **Table data bugs:** surfaced as test failures (`test_harmonised_standards_identifiers_unique`, etc.).
- **Cache miss in `_CENFetcher`:** `logger.warning("cen_cache_miss identifier=%s hint=%s", id, "run sync-standards --body CEN")`. Returns `None`.
- **Withdrawal guard abort:** `logger.warning(...)` + error in report. Same pattern as CC and Relaton loaders.

## Testing

### `tests/test_sync_cen.py` (new)

**Table integrity:**
- `test_harmonised_standards_table_not_empty` — `>= 50` entries
- `test_harmonised_standards_identifiers_unique` — no duplicates
- `test_harmonised_standards_all_have_directive` — non-empty directive on every entry
- `test_harmonised_standards_identifiers_start_with_en` — all start with `EN `

**Record builder:**
- `test_hs_to_record_plain_en` — body/status/full_text fields correct
- `test_hs_to_record_en_iso` — EN ISO identifier preserved
- `test_hs_to_record_withdrawn` — withdrawn status maps correctly

**CENLoader integration:**
- `test_cen_loader_cold_sync` — `report.added == len(table)`
- `test_cen_loader_resync_unchanged_short_circuits` — `added=0, unchanged=N`
- `test_cen_loader_force_rewrites` — `force=True` bypasses hash gate

### `tests/test_standards_client.py` (extend)

- `test_resolve_en_plain`, `test_resolve_en_iso`, `test_resolve_en_iec`, `test_resolve_en_iso_iec`
- `test_resolve_etsi_en_still_dispatches_to_etsi` — regression guard
- `test_cen_fetcher_registered`, `test_cen_fetcher_cache_miss_logs_warning`
- `test_standards_client_search_cen_delegates_to_cache`

### `tests/test_cli_sync_standards.py` (extend)

- `test_select_loaders_accepts_cen`, `test_select_loaders_all_includes_cen`

No live-smoke tests (no external data source).

## PR Layout

Single PR, four ordered commits:

1. `feat(standards): CEN harmonised-standards table + CENLoader` — `_sync_cen.py` with data model, table, record builder, loader. Table integrity + loader tests.
2. `feat(standards): register CEN in StandardsClient + CLI + identifier regex` — EN regex groups, `_CENFetcher`, `_fetchers["CEN"]`, `_select_loaders`. Regex + dispatch tests.
3. `docs(standards): CEN/CENELEC body in README and standards guide`
4. (If needed) `test(standards): additional CEN coverage` — patch-coverage gaps.

## Acceptance Gates

- [ ] CI green
- [ ] Lint + format + mypy clean
- [ ] Codecov patch coverage ≥ 80%
- [ ] README + docs updated
- [ ] PR description closes #83; references #137 / #138 / #139

## Out of Scope

Filed as follow-ups:

- **#137** — EUR-Lex Formex XML parser (comprehensive automated sync alternative)
- **#138** — Live scrape fallback from `standards.cencenelec.eu`
- **#139** — Quarterly table review (recurring maintenance)

Explicitly **not** doing:

- Full CEN/CENELEC catalogue beyond harmonised standards
- Cross-linking EN → ISO/IEC records via `related`
- Price field population
- Live fallback of any kind

## The Hard-Coded Table

The `_HARMONISED_STANDARDS` constant covers standards from these EU directives:

| Directive | Shorthand | Example standards |
|---|---|---|
| Electromagnetic Compatibility | EMC | EN 55032, EN 55035, EN 61000-series |
| Radio Equipment | RED | EN 300 328, EN 301 489-series, EN 62311 |
| Machinery | Machinery | EN ISO 13849-1, EN ISO 12100, EN 60204-1 |
| Cyber Resilience Act | CRA | EN IEC 62443-series (expected) |
| Medical Devices Regulation | MDR | EN ISO 13485, EN 62304 |
| General Product Safety | GPSR | EN 71-series (toys), EN 14988 (highchairs) |
| Low Voltage | LVD | EN 62368-1, EN 60335-1, EN 61010-1 |

The implementer should populate `_HARMONISED_STANDARDS` with the most-cited standards from each directive. A reasonable starting set: ~20-30 per directive for EMC/RED/Machinery (the most mature), ~10 each for CRA/MDR/GPSR. Total ~100-150 entries. Each entry needs: identifier, title, directive shorthand, status ("harmonised" or "withdrawn"), and optional published_date.

Source for populating: the [EU harmonised standards pages](https://single-market-economy.ec.europa.eu/single-market/european-standards/harmonised-standards_en) per directive, which list the OJ references and standard numbers.
