# PR 4a — Common Criteria Framework + Protection Profiles Loader

**Date:** 2026-04-15
**Closes:** scholar-mcp#84
**Builds on:** scholar-mcp#121 (sync infrastructure), #122 / #126 / #130 (StandardsClient + Relaton patterns)
**Follow-ups filed:** scholar-mcp#131 (sec-certs certified products), #132 (Supporting Documents), #133 (CEM Supplements), #134 (HTML auto-discovery)

## Context

The v0.9.0 standards rollout originally bundled CEN/CENELEC + Common Criteria into a single PR 4. They share no code or data sources, so we split them: this spec covers PR 4a (Common Criteria only). CEN/CENELEC moves to a separate PR 4b.

## Summary

Ship Common Criteria as a Tier 2 sync-only body covering two record categories: ~15 framework documents (CC:2022, CC:2017, ISO/IEC 15408 / 18045 dual publications) and ~500 Protection Profiles. CC has no live API, so the loader is sync-only — the existing `body=` dispatch pattern in `StandardsClient` is preserved by registering a thin cache-only `_CCFetcher` that surfaces a "run sync" hint on cache miss.

## Scope decisions made during brainstorming

### What "Common Criteria" loads

CC has three potential record categories:

1. **Framework documents** — `CC:2022`, `CC:2017`, `ISO/IEC 15408`, CEM. ~15 documents. **In scope.** This is what academic citations primarily reference.
2. **Protection Profiles** — published security requirement specifications. ~500 documents. **In scope.** Common in security-research papers.
3. **Certified products** — ~6700 product certifications. **Out of scope** (deferred to #131 — academic citations rarely reference individual product certs).

### CC ↔ ISO/IEC 15408 modeling: parallel publication, not joint committee

CC and ISO/IEC 15408 are **parallel publications** of the same content under two different publishers — not a single joint committee output. PR 2/3 used a joint-`body` model (`ISO/IEC`, `IEC/IEEE`, `ISO/IEC/IEEE`) for true joint committee outputs that have a single canonical citation form. CC ↔ ISO 15408 has two distinct citation forms (`CC:2022` OR `ISO/IEC 15408` — never joined), so it gets a different model: **two records cross-linked via the `related` field**.

| Storage relationship | When to use | Storage model |
|---|---|---|
| Joint committee (one publication, multiple bodies on cover) | `ISO/IEC 27001:2022`, `ISO/IEC/IEEE 42010-2011`, `IEC/IEEE 61588:2021` | Single record, joint `body` value matching the real-world cover citation |
| Parallel publication (separate publications, same content) | CC ↔ ISO/IEC 15408, CC ↔ ISO/IEC 18045 | Two records, one per publishing body, cross-linked via `related` |

This distinction is captured in user memory `project_cc_iso_15408.md` for future cross-body work.

### Ownership conflict resolution: ISO loader denylist for 15408 family

`relaton-data-iso` already contains `iso-iec-15408-1-2022.yaml` (and -2, -3 variants), which PR 2's `RelatonLoader` would normally pull and write with `body="ISO/IEC"` and `source="ISO"`. The CC loader's value proposition is the **free PDF** (vs. ISO's paywall), and we want the LLM to discover this regardless of which identifier form they look up.

Decision: **ISO loader denylists the 15408 family; CC loader owns those records entirely.** Adds a per-body `_RELATON_SKIP_SLUGS` constant in `_sync_relaton.py`; a small set of slugs (~8) under the `"ISO"` key. Deterministic ownership regardless of sync order; the LLM always gets `full_text_url` pointing at the free CC PDF.

### Protection Profile identifier extraction: hybrid

The `pps.csv` columns include URLs like `KECS-PP-0822-2017_PP_EN.pdf`, `BSI-CC-PP-0099-V2-2017.pdf`, `ANSSI-CC-PP-2014_01.pdf` — these contain stable scheme IDs but there's no dedicated ID column.

Decision: **per-scheme regex with composite fallback.** Maintain a `_PP_SCHEME_PATTERNS` dict keyed by 2-letter scheme code (KR, DE, FR, US, ES, …) with one regex per scheme. On no match, fall back to the composite form `f"CC PP {scheme}-{name}"` so we never drop a record. Logged at DEBUG when fallback fires.

### No live fetcher — cache-only `_CCFetcher`

CC has no live API (the portal HTML is unstructured and rate-limited; we don't HTML-scrape). Instead of skipping `_fetchers["CC"]` registration entirely, we register a thin cache-only wrapper that:

- Returns `cache.get_standard(identifier)` directly on `.get()` — no network.
- Logs `WARNING` on cache miss with a `run sync-standards --body CC` hint so operators see the gap.
- Delegates `.search(query)` to `cache.search_synced_standards(query, source="CC", limit=...)`.

This keeps the `_StandardsFetcher` Protocol uniform across all bodies and makes `body="CC"` searches behave consistently with `body="ISO"` etc.

## Module Changes

| File | Change |
|---|---|
| `src/scholar_mcp/_sync_cc.py` | **New** — `CCFrameworkEntry` dataclass, `_FRAMEWORK_DOCS` constant (~15 entries), `_PP_SCHEME_PATTERNS` per-scheme regex dict, `_extract_pp_id` helper with composite fallback, `_pp_row_to_record` mapper, `CCLoader` orchestrating Phase 1 (framework) → Phase 2 (PP CSV, content-hash gated) → Phase 3 (withdrawal detection with >50% guard) |
| `src/scholar_mcp/_sync_relaton.py` | Add `_RELATON_SKIP_SLUGS: dict[str, frozenset[str]]` constant; apply it during the tarball iteration to skip the 15408 family under `body="ISO"` |
| `src/scholar_mcp/_standards_client.py` | Add CC regex groups to `resolve_identifier_local` (`_CC_VERSION_RE`, `_CC_PART_RE`, `_CEM_RE`, `_CC_PP_RE`); add `_CCFetcher` class; register `_fetchers["CC"] = _CCFetcher(cache=cache)` |
| `src/scholar_mcp/cli.py` | Extend `_select_loaders` to construct `CCLoader()` for `--body CC` and include in `--body all` |
| `tests/fixtures/standards/cc_sample/pps.csv` | New small fixture (~6 rows covering each scheme variant + one unknown-scheme fallback) |
| `tests/test_sync_cc.py` | New test file (~250 LOC) covering identifier extraction, framework table, PP row mapper, loader integration, error paths |
| `tests/test_sync_relaton.py` | Two new tests: `test_iso_loader_skips_15408_slugs`, `test_iso_loader_skip_slugs_only_applies_to_iso_body` |
| `tests/test_standards_client.py` | New regex tests + `_CCFetcher` integration tests (10 tests) |
| `tests/test_cli_sync_standards.py` | Two new tests: `test_select_loaders_accepts_cc`, `test_select_loaders_all_includes_cc` |
| `README.md` | Add CC to standards bodies list with example identifiers |
| `docs/guides/standards.md` | Add CC section: identifier forms, sync command, CC↔ISO 15408 cross-link explanation, deferred follow-ups |

No changes to: `_cache.py`, `_protocols.py`, `_server_deps.py`, `_server_tools.py`, `_relaton_live.py`, `_record_types.py`.

## Data Flow

### Sync (`scholar-mcp sync-standards --body CC`)

```
cli._select_loaders({"CC"}) → CCLoader()
  → CCLoader.sync(cache):
      # Phase 1 — framework documents (no network, hard-coded table)
      for entry in _FRAMEWORK_DOCS:
          for record in _framework_to_records(entry):     # 1 or 2 records per entry
              cache.set_standard(record["identifier"], record, source="CC", synced=True)
              for alias in _framework_aliases(entry):
                  cache.set_standard_alias(alias, record["identifier"])

      # Phase 2 — Protection Profiles, content-hash gated
      csv_bytes = await _fetch_pps_csv(http)
      csv_hash = hashlib.sha256(csv_bytes).hexdigest()
      prev = await cache.get_sync_run("CC")
      if not force and prev and prev.upstream_ref == csv_hash:
          report.unchanged += await _count_synced_pps(cache)
          return report   # short-circuit

      for row in csv.DictReader(io.StringIO(csv_bytes.decode("utf-8"))):
          record = _pp_row_to_record(row)
          if record is None:
              report.errors.append(...)
              continue
          cache.set_standard(record["identifier"], record, source="CC", synced=True)

      # Phase 3 — withdrawal detection (same >50% guard as RelatonLoader)
      prev_ids = await cache.list_synced_standard_ids(source="CC")
      missing = prev_ids - current_ids
      if len(missing) > 0.5 * len(prev_ids):
          report.errors.append("withdrawal pass aborted: too many missing")
      else:
          for ident in missing:
              existing = await cache.get_standard(ident)
              await cache.set_standard(ident, {**existing, "status": "withdrawn"},
                                       source="CC", synced=True)

      report.upstream_ref = csv_hash
      return report
```

### Live fetch — none

CC has no live API. `_CCFetcher.get(identifier)` queries the cache directly:

- Cache hit → return record.
- Cache miss → `logger.warning("cc_cache_miss identifier=%s hint=%s", id, "run sync-standards --body CC")`, return `None`.

### Identifier resolution flows (LLM lookups)

```
get_standard("CC:2022 Part 1")
  → resolve_identifier_local → ("CC:2022 Part 1", "CC")
  → _fetchers["CC"].get(...) → cache hit → record(body="CC", related=["ISO/IEC 15408-1:2022"])

get_standard("ISO/IEC 15408-1:2022")
  → resolve_identifier_local → ("ISO/IEC 15408-1:2022", "ISO/IEC")
  → _fetchers["ISO/IEC"].get(...) → cache hit → record(body="ISO/IEC", source="CC",
    full_text_url=<free CC PDF>, full_text_available=True, related=["CC:2022 Part 1"])

get_standard("BSI-CC-PP-0099-V2-2017")
  → resolve_identifier_local → ("BSI-CC-PP-0099-V2-2017", "CC")
  → _fetchers["CC"].get(...) → cache hit → PP record

get_standard("CC PP unknown-scheme-Some Random Name V1.0")    # fallback form
  → resolve_identifier_local → no specific PP match, generic CC pattern catches it
  → _fetchers["CC"].get(...) → cache hit (composite-fallback identifier)
```

## Error Handling (per CLAUDE.md Logging Standard)

- **Phase 1 failures** — pure dict construction, no external errors. Bugs in `_FRAMEWORK_DOCS` surface as test failures.
- **Phase 2 fetch errors** (HTTP, timeout, malformed CSV at parse-init time): `logger.error("cc_pp_fetch_failed err=%s", exc, exc_info=True)`. Returns `SyncReport(added=phase1_count, errors=[...])`. CLI exit 1 (hard fail for this body).
- **Phase 2 row-parse errors** (per-row): `logger.warning("cc_pp_row_parse_error name=%s", row_name)`, increment `errors` counter, continue.
- **PP ID extraction fallback** (no scheme regex match): `logger.debug("cc_pp_id_fallback scheme=%s name=%s", scheme, name)`. Not an error — by design.
- **Withdrawal-pass abort** (>50% missing): `logger.warning("cc_withdrawal_aborted missing=%s prev=%s", ...)`. Returns report without marking anything withdrawn.
- **`_CCFetcher` cache miss**: `logger.warning("cc_cache_miss identifier=%s hint=run sync-standards --body CC", id)`. Returns `None` to caller.

No bare `except`. All exceptions specified by type.

## Testing

TDD throughout. Coverage targets: ≥80% patch.

### `tests/fixtures/standards/cc_sample/pps.csv`

~6 rows covering each scheme variant the regex must handle (KECS, BSI, ANSSI, NIAP, CCN, plus one unknown-scheme row → exercises the composite fallback).

### `tests/test_sync_cc.py` (new, ~250 LOC)

**Identifier extraction:**
- `test_extract_pp_id_kecs`, `test_extract_pp_id_bsi`, `test_extract_pp_id_anssi`, `test_extract_pp_id_niap`, `test_extract_pp_id_ccn`
- `test_extract_pp_id_unknown_scheme_falls_back_to_composite`

**Framework table:**
- `test_framework_to_records_dual_publication` — verifies CC + ISO records, `related` cross-link both ways.
- `test_framework_to_records_cc_only` — `iso_identifier=None` → 1 record.
- `test_framework_records_have_free_pdf_url` — `full_text_url` shared, `full_text_available=True` on both.
- `test_framework_records_aliases_include_fuzzy_forms`.

**PP CSV parsing:**
- `test_pp_row_to_record_happy_path`, `test_pp_row_to_record_archived_status`, `test_pp_row_to_record_active_status`, `test_pp_row_to_record_missing_certification_url_returns_none`, `test_pp_row_published_date_parsed`.

**CCLoader integration (mocked HTTP via `respx`):**
- `test_cc_loader_cold_sync_writes_framework_and_pps`
- `test_cc_loader_resync_unchanged_csv_short_circuits`
- `test_cc_loader_resync_changed_csv_detects_updates`
- `test_cc_loader_withdrawal_detection`
- `test_cc_loader_withdrawal_abort_on_majority_missing`
- `test_cc_loader_owns_iso_15408_records` — CC writes both `CC:2022 Part 1` and `ISO/IEC 15408-1:2022`; verifies the dual record's `source="CC"`, `full_text_available=True`, `related` cross-link, and free-PDF `full_text_url`

**HTTP error paths:**
- `test_cc_loader_csv_fetch_404`, `test_cc_loader_csv_fetch_timeout`.

### `tests/test_sync_relaton.py` (extension)

- `test_iso_loader_skips_15408_slugs`
- `test_iso_loader_skip_slugs_only_applies_to_iso_body`

### `tests/test_standards_client.py` (extension)

10 new tests covering CC regex resolution + `_CCFetcher` registration + cache-miss warning behavior.

### `tests/test_cli_sync_standards.py` (extension)

`test_select_loaders_accepts_cc`, `test_select_loaders_all_includes_cc`.

### Live smoke (pytest `-m live`, opt-in)

- `test_live_fetch_cc_pps_csv_real` — real `pps.csv`, ≥100 records, ≥5 distinct schemes.
- `test_live_framework_pdf_urls_resolve_real` — HEAD all `_FRAMEWORK_DOCS[*].cc_pdf_url`, expect 200.

## PR Layout

Single PR `feat/standards-cc-loader`, six ordered commits:

1. `feat(standards): ISO loader denylist for shared-ownership slugs` — adds `_RELATON_SKIP_SLUGS` and the 15408 family entries. Independent test coverage. Lands first as the prerequisite.
2. `feat(standards): CC framework table + dual-publication record builder` — `_sync_cc.py` skeleton, `CCFrameworkEntry`, `_FRAMEWORK_DOCS`, `_framework_to_records`. Pure data + transform.
3. `feat(standards): CC Protection Profile CSV parser + per-scheme regex` — `_extract_pp_id`, `_pp_row_to_record`, fixture. No HTTP yet.
4. `feat(standards): CCLoader sync orchestration + content-hash gate` — `CCLoader` class, mocked-HTTP integration tests, withdrawal guard.
5. `feat(standards): register CC in StandardsClient + CLI + identifier regex` — `_CCFetcher`, `_fetchers["CC"]`, regex groups, `_select_loaders` extension.
6. `docs(standards): Common Criteria body in README and standards guide` — user-facing docs.

Each commit independently green on `uv run pytest -x -q`, `uv run ruff check --fix . && uv run ruff format --check .`, `uv run mypy src/`. No squash on merge.

## Acceptance Gates

Per CLAUDE.md "Hard PR Acceptance Gates":

- [ ] CI passes (~6 commits)
- [ ] `uv run ruff check --fix . && uv run ruff format --check .` clean
- [ ] `uv run mypy src/` clean
- [ ] Codecov patch coverage ≥ 80%
- [ ] `README.md` + `docs/guides/standards.md` updated in the same PR
- [ ] PR description closes #84; references #131 / #132 / #133 / #134

Manifest version bumps handled by release workflow.

## Out of Scope

Filed as follow-ups:

- **#131** — Common Criteria certified-products dataset (sec-certs JSON, ~6700 records)
- **#132** — CC Supporting Documents and Guidance Documents loader
- **#133** — CEM Supplements and Application Notes
- **#134** — Auto-discover CC framework documents from portal HTML

Explicitly **not** doing in PR 4a:

- Live HTML scraping of the CC portal.
- Modifying `StandardRecord` shape — the existing schema covers everything.
- Cache-schema migration — none needed.
