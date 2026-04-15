# PR 3 — IEEE Relaton Loader (v0.9.0 standards rollout)

**Date:** 2026-04-15
**Closes:** scholar-mcp#82 (IEEE Tier 2 metadata lookup)
**Builds on:** scholar-mcp#122 (PR 2: ISO + IEC Relaton loaders), scholar-mcp#121 (PR 1: sync infrastructure)
**Follow-ups filed:** scholar-mcp#127, scholar-mcp#128, scholar-mcp#129 (see "Out of scope")

## Context

PR 2's design called PR 3 "a trivial config addition once PR 2's `RelatonLoader` ships." While verifying that premise against the real `relaton/relaton-data-ieee` GitHub repository, two pre-existing defects and one fresh requirement surfaced that enlarge the scope beyond a config-only change. This spec captures the combined work.

## Summary

Ship IEEE as a fully-functional Tier 2 Relaton body — both the bulk-sync path (`sync-standards --body IEEE`) and the live-fetch fallback. Fix the pre-existing `docid` / `docidentifier` schema-key mismatch that silently breaks live-fetching of real ISO/IEC standards today, and add a per-body slug-convention strategy so IEEE's `UPPERCASE_UNDERSCORED.yaml` filenames resolve correctly alongside ISO's `lowercase-hyphenated.yaml` form.

## In Scope

1. **IEEE added as a Relaton body.** `_RELATON_CONFIGS["IEEE"]` points at `relaton/relaton-data-ieee`. `StandardsClient._fetchers["IEEE"]` registers a `RelatonLiveFetcher(source="IEEE")` instance. `_select_loaders` in `cli.py` accepts `--body IEEE` and `all` includes IEEE.
2. **Joint-committee identifiers parsed and stored.** Standards whose `docid` list contains both ISO and IEEE entries produce `body="ISO/IEC/IEEE"`; IEC + IEEE produces `body="IEC/IEEE"`. Existing ISO/IEC joint handling unchanged. Dispatch remains single-key (`"IEEE"`) — joints reachable via identifier lookup or `body="IEEE"` since they share `source="IEEE"`.
3. **Relaton schema-key fix (pre-existing bug).** `_sync_relaton.py` currently reads `doc.get("docidentifier")`, but real relaton repos expose the top-level key as `docid:`. Unit tests use the old-shape fixtures, so the bug was latent. Fix: `doc.get("docid") or doc.get("docidentifier")`. Apply the same fallback to `bibitem.get(...)` alias paths.
4. **Per-body slug-convention strategy.** ISO/IEC keep their existing `lowercase-hyphenated.yaml` slug. IEEE produces `UPPERCASE_UNDERSCORED.yaml` (preserving dots and intra-token hyphens): `IEEE 1003.1-2024` → `IEEE_1003.1-2024.yaml`; `ISO/IEC/IEEE 42010-2011` → `ISO_IEC_IEEE_42010-2011.yaml`.
5. **Trademark-scope filtering.** IEEE `docid` entries often include a trademark variant (`scope: trademark`, identifier contains `™`). These are skipped when picking the canonical identifier.
6. **Live-smoke test marker.** Introduce pytest `-m live` marker (configured in `pyproject.toml`, not run in CI by default) so one targeted live-fetch test against real GitHub raw URLs catches future schema drift early. Otherwise the `docid`-style bug would have recurred silently.

## Out of Scope

Filed as follow-ups:

- **scholar-mcp#127** — ANSI/IEEE and AIEE historical identifier forms (`ANSI/IEEE Std 754-1985`, `AIEE 11-1937`). Still reachable via all-bodies fallback.
- **scholar-mcp#128** — IEEE P-prefixed draft identifiers (`IEEE P802.11-REVme`). Separate question about whether `sync-standards` should include drafts at all.
- **scholar-mcp#129** — Explicit `_fetchers["IEC/IEEE"]` / `_fetchers["ISO/IEC/IEEE"]` dispatch keys. Would require body-column filtering in `search_synced_standards`. Current workaround: `body="IEEE"` returns joints too.

Pre-existing, unchanged:

- **scholar-mcp#92** — IEEE Xplore authenticated full-text path.

Explicitly **not** doing:

- Price field population (all Tier 2 records carry `price=None` per Tier 2 design).
- Citation formatting for `StandardRecord` (F4 future).
- Any cache schema migration (existing columns are sufficient).

## Design Decisions

### Schema-key fix applies to all Relaton bodies, not just IEEE

The `docid` / `docidentifier` mismatch was latent because unit tests use `docidentifier:` fixtures and no live smoke test existed. Fixing it in this PR rather than filing a separate bug PR:

- The fix is one-liner with an `or` fallback (`doc.get("docid") or doc.get("docidentifier")`) — no behavior change for fixtures or any existing consumer.
- PR 3 touches the same function (`_yaml_to_record`) to add IEEE/joint handling. Splitting the schema-key fix into its own PR means two review rounds on the same function.
- Without the fix, PR 3's IEEE loader would also produce stubs, not full records — the feature would not actually work end-to-end.

### `body` reflects joint nature; dispatch stays single-key

A joint standard like `ISO/IEC/IEEE 42010-2011` stores with `body="ISO/IEC/IEEE"` and `source="IEEE"`. This mirrors PR 2's ISO/IEC policy (`body` describes the standard, `source` describes the loader that wrote it).

Dispatch keys, however, stay at `"IEEE"` only. Joint-bodies don't get their own `_fetchers` entries. Rationale:

- Callers who type a full joint identifier (`ISO/IEC/IEEE 42010-2011`) go through `resolve_identifier_local` → body-prefix match → dispatches to `_fetchers["IEEE"]` which covers the IEEE repo.
- Callers who search by `body="IEEE"` get IEEE-primary + all joints (both share `source="IEEE"`), which is usually what they want.
- Callers who want to filter to only triple-joints or only IEC/IEEE joints can filter client-side, or wait for scholar-mcp#129.
- Adding dispatch keys would require body-column filtering in `search_synced_standards`; the current API only supports `source`-column filtering. That's a bigger schema-query change than this PR warrants.

**Two different `body` values flow through the system — do not confuse them:**

| Where | Value | Purpose |
|---|---|---|
| `resolve_identifier_local` return tuple | `"IEEE"` (even for `IEC/IEEE` and `ISO/IEC/IEEE` identifiers) | Dispatch key — must match a `_fetchers` entry |
| `StandardRecord.body` on the returned / stored row | `"IEEE"`, `"IEC/IEEE"`, or `"ISO/IEC/IEEE"` | Accurate metadata — describes the standard's true joint nature |

Concretely: `resolve_identifier_local("ISO/IEC/IEEE 42010-2011")` returns `("ISO/IEC/IEEE 42010-2011", "IEEE")` — the canonical identifier preserves the joint form, but the dispatch body is flattened to `"IEEE"`. The resulting record has `body="ISO/IEC/IEEE"` because `_canonical_identifier_and_body` inspects the full `docid` list and detects the joint nature.

The existing PR 2 behavior is untouched: `resolve_identifier_local("ISO/IEC 27001:2022")` still returns body `"ISO/IEC"` because `_fetchers["ISO/IEC"]` exists as a dispatch key.

### Per-body slug-convention dispatch, not regex

`_identifier_to_relaton_slug` becomes a dispatcher on identifier prefix:

- `ISO` / `IEC` / `ISO/IEC` → existing lowercase-hyphen logic (unchanged).
- `IEEE` / `IEC/IEEE` / `ISO/IEC/IEEE` → new uppercase-underscore logic (preserving `.` and `-` inside tokens).

This reads more clearly than a unified regex with many branches and keeps the ISO/IEC path byte-identical to PR 2 (zero regression risk). The function remains single-purpose; a switch on prefix is the right level of abstraction.

### Trademark entries are docid-level, not record-level

An IEEE `docid` list typically contains two `primary: true` entries — one canonical identifier (`IEEE 1003.1-2024`) and one trademark variant (`IEEE 1003.1-2024™`, `scope: trademark`). Both are flagged primary. The canonical-picking logic filters out `scope: trademark` entries before picking the primary. The record itself is still emitted; only the trademark identifier variant is discarded.

Alias entries (non-primary) keep their trademark variants recorded as aliases — useful for fuzzy lookup from a raw citation string that happens to include `™`.

### Fallback order for joint standards

Live-fetch of `ISO/IEC/IEEE 42010-2011` tries the IEEE repo first (confirmed host), then ISO, then IEC. `IEC/IEEE` tries IEEE first, then IEC. Rationale: the IEEE repo is the canonical publisher of these joints in the Relaton ecosystem. ISO and IEC repos may contain copies for cross-reference but aren't authoritative.

Existing pure-ISO and pure-IEC ordering unchanged.

## Module Changes

| File | Change |
|---|---|
| `src/scholar_mcp/_sync_relaton.py` | `docid`/`docidentifier` fallback in 3 call sites; `_RELATON_CONFIGS["IEEE"]`; `_canonical_identifier_and_body` extended for IEEE and joint detection; trademark-scope filter in canonical picker |
| `src/scholar_mcp/_relaton_live.py` | `_identifier_to_relaton_slug` dispatches on prefix to lowercase-hyphen (ISO/IEC) vs. uppercase-underscore (IEEE) logic; `_identifier_prefers_*` helpers extended; repo-order helper accounts for IEEE preference |
| `src/scholar_mcp/_standards_client.py` | `_fetchers["IEEE"] = RelatonLiveFetcher(http, cache=cache, source="IEEE")`; `resolve_identifier_local` regex groups for `IEEE`, `IEEE Std`, `IEC/IEEE`, `ISO/IEC/IEEE` |
| `src/scholar_mcp/cli.py` | `_select_loaders` supports `--body IEEE`; `--body all` includes IEEE |
| `pyproject.toml` | Register pytest `live` marker |
| `README.md` | IEEE added to supported standards body list + example identifier |
| `docs/guides/standards.md` | IEEE section: identifier forms, sync example, joint-standards note |

No changes to: `_cache.py`, `_protocols.py`, `_server_deps.py`, `_server_tools.py`.

## Data Flow

### Sync

```
cli._select_loaders({"IEEE"})
  → RelatonLoader(body="IEEE", config=_RELATON_CONFIGS["IEEE"])
      → fetch commit SHA → incremental-check vs. last sync
      → list data/*.yaml, diff against cache (source="IEEE")
      → per-file:
          _yaml_to_record(doc):
              docid = doc.get("docid") or doc.get("docidentifier") or []
              canonical = _canonical_identifier_and_body(docid)
                  - filters scope=trademark entries
                  - detects joint nature from type presence (ISO/IEC/IEEE)
              → StandardRecord(body=..., source="IEEE", synced_at=now)
          cache.upsert_standards([record], source="IEEE", synced=True)
      → cache.record_sync_run("IEEE", added=N, updated=M, withdrawn=K)
      → cache.mark_withdrawn(in_cache - in_repo, source="IEEE")
```

### Live fetch

```
RelatonLiveFetcher(source="IEEE").get("IEEE 1003.1-2024")
  → slug = _identifier_to_relaton_slug("IEEE 1003.1-2024") = "IEEE_1003.1-2024"
  → repos = ["relaton-data-ieee"]  (plus ISO/IEC for joint identifiers)
  → for each repo:
      GET raw.githubusercontent.com/relaton/{repo}/main/data/{slug}.yaml
      404 → next repo
      5xx / parse error → log WARNING, next repo
      200 + parsed → _yaml_to_record → return
  → all repos fail → return stub StandardRecord(title="", full_text_available=False)
```

## Error Handling

Per the Logging Standard in `CLAUDE.md`:

- **Sync-path YAML parse errors** (one bad file): `logger.warning("relaton_yaml_parse_error file=%s err=%s", ...)`, skip file, increment `errors` counter.
- **Sync-path HTTP errors on commit-SHA check**: `logger.error("relaton_sync_fetch_error body=%s err=%s", ...)`, body counted as failed; process exits 3 (partial) if other bodies succeeded, 1 if this was the only body.
- **Canonical-identifier extraction misses** (no primary, all trademark-scoped, unparseable joint): `logger.debug("relaton_yaml_skip reason=%s", ...)`, skip record. Not an error.
- **Live-fetch 404 in all repos**: return stub record. Caller surfaces canonical form even without metadata.
- **Live-fetch transient errors**: `logger.warning` + fall through; stub returned on exhaustion.

## Testing

TDD throughout. Each feature commit has its failing test first.

### `tests/test_sync_relaton.py` (parser/loader)

- `test_yaml_to_record_reads_docid_key` — real-shape fixture with `docid:`, asserts full record parses (regression guard for the pre-existing bug).
- `test_yaml_to_record_falls_back_to_docidentifier_key` — old-shape fixture still works.
- `test_canonical_identifier_ieee_only` — `[{type: IEEE, primary: true}]` → `("IEEE X-YYYY", "IEEE")`.
- `test_canonical_identifier_iec_ieee_joint` — IEC + IEEE entries → `("IEC/IEEE X-YYYY", "IEC/IEEE")`.
- `test_canonical_identifier_iso_iec_ieee_joint` — ISO + IEC + IEEE entries → `("ISO/IEC/IEEE X-YYYY", "ISO/IEC/IEEE")`.
- `test_canonical_identifier_ieee_skips_trademark_scope` — entries with `scope: trademark` are filtered before primary-picking.
- `test_relaton_loader_ieee_smoke` — `RelatonLoader("IEEE", ...)` constructs, reports `body="IEEE"`.

### `tests/test_relaton_live.py` (slug + live fetch)

- `test_identifier_to_slug_ieee_plain` — `IEEE 1003.1-2024` → `IEEE_1003.1-2024`.
- `test_identifier_to_slug_ieee_std_variant` — `IEEE Std 1588-2019` → `IEEE_Std_1588-2019`.
- `test_identifier_to_slug_iec_ieee_joint` — `IEC/IEEE 61588-2021` → `IEC_IEEE_61588-2021`.
- `test_identifier_to_slug_iso_iec_ieee_joint` — `ISO/IEC/IEEE 42010-2011` → `ISO_IEC_IEEE_42010-2011`.
- `test_identifier_to_slug_preserves_iso_lowercase_hyphen` — `ISO 9001:2015` still → `iso-9001-2015` (regression guard).
- `test_live_fetch_ieee_hit` — mocked 200 response parses to a full record with `body="IEEE"`.
- `test_live_fetch_ieee_fallback_to_iso_for_joint` — `ISO/IEC/IEEE 42010-2011` IEEE-404 → ISO-200.

### `tests/test_standards_client.py` (regex + dispatch)

- `test_resolve_ieee_plain` — `resolve_identifier_local("IEEE 802.11-2020")` → `("IEEE 802.11-2020", "IEEE")`.
- `test_resolve_ieee_std_variant` — `IEEE Std 1588-2019` accepted.
- `test_resolve_iec_ieee_joint` — `IEC/IEEE 61588-2021` → `("IEC/IEEE 61588-2021", "IEC/IEEE")`. Dispatch key is `"IEEE"` but the body field is preserved.
- `test_resolve_iso_iec_ieee_joint` — triple-joint resolves.
- `test_standards_client_search_ieee_delegates_to_relaton` — mock cache, `search(body="IEEE")` → forwards `source="IEEE"`.
- `test_standards_client_fetchers_ieee_instance_registered` — `_fetchers["IEEE"]` is `RelatonLiveFetcher` with `_source="IEEE"`.

### `tests/test_cli_sync.py`

- `test_select_loaders_accepts_ieee` — `--body IEEE` returns IEEE loader only.
- `test_select_loaders_all_includes_ieee` — `--body all` returns ISO + IEC + IEEE.

### Live smoke (pytest `-m live`, opt-in)

- `test_live_fetch_ieee_1003_1_2024_real` — hits `raw.githubusercontent.com/relaton/relaton-data-ieee/main/data/IEEE_1003.1-2024.yaml`, asserts non-empty title and `body="IEEE"`.

## PR Layout

Single PR with ordered commits:

1. `fix(standards): read docid key in relaton YAML, fall back to docidentifier` — includes the `pyproject.toml` pytest `live` marker registration and one ISO live-smoke test as the regression guard.
2. `feat(standards): extend relaton parser for IEEE + joint-committee bodies`
3. `feat(standards): IEEE slug strategy + repo dispatch in RelatonLiveFetcher` — includes the IEEE live-smoke test.
4. `feat(standards): register IEEE in StandardsClient + CLI + RelatonConfig`
5. `docs(standards): IEEE body in README and guides`

Each commit green on `uv run pytest -x -q`, `uv run ruff check`, `uv run mypy src/`. No squash on merge — stacked commits ease review.

## Acceptance Gates

Per `CLAUDE.md` "Hard PR Acceptance Gates":

- [ ] CI passes (all tests green)
- [ ] `uv run ruff check --fix .` + `uv run ruff format .` clean
- [ ] `uv run mypy src/` clean
- [ ] Codecov patch coverage ≥ 80 %
- [ ] `README.md` + `docs/guides/standards.md` updated in the same PR
- [ ] PR description closes #82; references #127 / #128 / #129

Manifest version bumps are handled by the release workflow; not included here.
