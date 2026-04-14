# PR 2 — ISO + IEC Relaton Loader Design

> Sub-spec of [`2026-04-13-standards-tier2-design.md`](2026-04-13-standards-tier2-design.md).
> PR 1 (`feat(standards): v0.9.0 PR 1/5 — sync infrastructure foundation`) is merged at
> commit `2dcbc72`. This document captures the PR-2-specific decisions and surface
> needed before plan-writing.

## Goal

Ship the first concrete loaders for the sync infrastructure landed in PR 1: ISO and IEC
metadata via the Relaton YAML dumps at `relaton/relaton-data-iso` and
`relaton/relaton-data-iec`. Closes scholar-mcp#80 and scholar-mcp#81.

## Decisions taken during brainstorming

1. **Joint-standard `body` value: `"ISO/IEC"`.** Standards present in both dumps under a
   joint identifier (e.g. `ISO/IEC 27001:2022`, `ISO/IEC 15408:2022`) get
   `StandardRecord.body = "ISO/IEC"`. The `_SYNC_BODIES` CLI choice tuple stays
   `(ISO, IEC, IEEE, CEN, CC, all)` — `"ISO/IEC"` is never a sync source, only a stored
   body value. The `source` column on the row records which loader actually wrote it
   (`"ISO"` or `"IEC"`); `body` reflects the standard's true joint nature.

2. **Live-fetch fallback: yes, via single-file Relaton GET.** A cache miss on
   `get_standard("ISO 9001:2015")` triggers a single
   `https://raw.githubusercontent.com/relaton/relaton-data-iso/main/data/{slug}.yaml`
   request. Parsed via the same `_yaml_to_record` mapper as sync. Cached as a 90-day
   live record (`synced=False`). Avoids the false-negative trap of "not found until
   sync runs." No HTML scraping — `raw.githubusercontent.com` is rate-limit free, no
   auth needed, deterministic format.

3. **GitHub auth: optional `SCHOLAR_GITHUB_TOKEN` env.** Default unauthenticated path
   covers cron-driven daily syncs (60 req/hr is plenty for 6 calls/sync). Token is a
   dev convenience for repeated `--force` testing. Documented in
   `docs/guides/standards.md`.

## File structure

### New files

```
src/scholar_mcp/
  _sync_relaton.py             # shared YAML loader; per-body RelatonLoader
  _relaton_live.py             # single-file live fallback fetcher
tests/
  fixtures/standards/
    relaton_iso_sample/        # ~15 YAML files (joint + plain + a withdrawn case)
    relaton_iec_sample/        # ~10 YAML files (incl. 2+ joint with ISO)
  test_sync_relaton.py
  test_relaton_live.py
docs/
  guides/standards.md          # Tier 2 sync usage, cron suggestions, troubleshooting
  specs/2026-04-13-pr2-iso-iec-relaton-design.md   # this document
```

### Modified files

| File | Change |
|---|---|
| `src/scholar_mcp/_record_types.py` | `StandardRecord.body` docstring lists `"ISO/IEC"` as valid |
| `src/scholar_mcp/_standards_client.py` | New regex groups for ISO/IEC/IEEE in `resolve_identifier_local`; register `RelatonLiveFetcher` for `ISO`, `IEC`, `ISO/IEC` keys in `StandardsClient._fetchers` |
| `src/scholar_mcp/cli.py` | `_select_loaders` returns real `RelatonLoader` instances (was empty list in PR 1) |
| `src/scholar_mcp/_cache.py` | New `list_synced_standard_ids(source: str) -> set[str]` method — required by withdrawn-detection step |
| `src/scholar_mcp/_protocols.py` | `CacheProtocol` gains the same method |
| `src/scholar_mcp/config.py` | New `github_token: str \| None` field, `SCHOLAR_GITHUB_TOKEN` env var |
| `README.md` | "Tier 2 standards" section under Features; sync-standards example shows ISO+IEC working |
| `docs/guides/claude-code-plugin.md` | Mention sync-standards in the plugin features list |
| `server.json`, `.claude-plugin/plugin/.claude-plugin/plugin.json`, `.claude-plugin/plugin/.mcp.json` | bump to `1.7.0-rc.2` |

## Component design

### `_sync_relaton.RelatonLoader`

```python
@dataclass(frozen=True)
class RelatonConfig:
    body: str                  # "ISO" or "IEC"
    repo: str                  # "relaton/relaton-data-iso"
    branch: str = "main"

_RELATON_BODIES: dict[str, RelatonConfig] = {
    "ISO": RelatonConfig(body="ISO", repo="relaton/relaton-data-iso"),
    "IEC": RelatonConfig(body="IEC", repo="relaton/relaton-data-iec"),
}

class RelatonLoader:
    """One instance per body. Conforms to standards_sync.Loader Protocol."""

    def __init__(self, body: str, *, http: httpx.AsyncClient | None = None,
                 token: str | None = None) -> None: ...

    body: str  # set in __init__

    async def sync(self, cache: CacheProtocol, *, force: bool = False) -> SyncReport: ...
```

### Sync algorithm

```
1. sha = GET https://api.github.com/repos/{repo}/commits/{branch} → .sha
   (Authorization: token {SCHOLAR_GITHUB_TOKEN} when set)

2. last = (await cache.get_sync_run(body))?.upstream_ref
   if sha == last and not force:
       return SyncReport(body=body, unchanged=COUNT_OF_EXISTING, ...)

3. with httpx.stream("GET", f"https://api.github.com/repos/{repo}/tarball/{sha}") as r:
       with tarfile.open(fileobj=r.raw, mode="r|gz") as tar:
           current_ids: set[str] = set()
           for member in tar:
               if not member.name.endswith(".yaml") or "/data/" not in member.name:
                   continue
               record, aliases = _yaml_to_record(yaml.safe_load(tar.extractfile(member)))
               if record is None:
                   errors.append(f"unparseable: {member.name}")
                   continue
               current_ids.add(record["identifier"])
               existing = await cache.get_standard(record["identifier"])
               if existing is None:
                   added += 1
               elif _record_changed(existing, record):
                   updated += 1
               else:
                   unchanged += 1
               await cache.set_standard(record["identifier"], record,
                                         source=body, synced=True)
               for alias in aliases:
                   await cache.set_standard_alias(alias, record["identifier"])

4. # Withdrawn detection — guarded against partial-tarball disasters
   prev_ids = await cache.list_synced_standard_ids(source=body)
   missing = prev_ids - current_ids
   if prev_ids and len(missing) > 0.5 * len(prev_ids):
       errors.append(
           f"withdrawal pass aborted: {len(missing)}/{len(prev_ids)} ids missing "
           "(>50% — likely partial sync)"
       )
   else:
       for ident in missing:
           prev = await cache.get_standard(ident)
           prev["status"] = "withdrawn"
           await cache.set_standard(ident, prev, source=body, synced=True)
           withdrawn += 1

5. return SyncReport(body=body, added, updated, unchanged, withdrawn,
                     errors, upstream_ref=sha, ...)
```

**New cache method needed**: `list_synced_standard_ids(source: str) -> set[str]`. Single
SQL query against `standards` table. Added to `CacheProtocol` and `ScholarCache`.

### Joint-standard detection (`_canonical_identifier_and_body`)

```python
def _canonical_identifier_and_body(yaml_doc: dict) -> tuple[str, str]:
    """Return (canonical_identifier, body) for a Relaton document.

    Joint detection rules:
    - If docidentifier list contains BOTH a type=ISO entry and a type=IEC entry,
      the standard is joint → body="ISO/IEC", identifier = the ISO/IEC-form entry.
    - If only one of {ISO, IEC} types is present → body=that type, identifier=that entry.
    - Fallback: docidentifier[type=primary] determines both.
    """
```

### `_yaml_to_record(yaml_doc) -> tuple[StandardRecord | None, list[str]]`

Maps a parsed Relaton YAML to (record, alias_list). Returns `(None, [])` on schema
mismatches that prevent extracting an identifier or title. Field mapping per parent
spec (lines 195–207). Errors are non-fatal — caller adds them to `SyncReport.errors`.

### `_relaton_live.RelatonLiveFetcher`

```python
class RelatonLiveFetcher:
    """Live-fetch single Relaton YAML files on cache miss.

    Registered into StandardsClient._fetchers for ISO, IEC, ISO/IEC.
    """

    async def fetch(self, identifier: str) -> StandardRecord | None: ...
```

Algorithm:
1. `slug = _identifier_to_relaton_slug(identifier)` — e.g. `"ISO 9001:2015"` →
   `"iso-9001-2015"`, `"ISO/IEC 27001:2022"` → `"iso-iec-27001-2022"`. Returns `None`
   for forms it can't slugify.
2. Choose repo order by the canonical identifier prefix: `ISO` or `ISO/IEC` → try
   `relaton-data-iso` first; `IEC` → try `relaton-data-iec` first. The other repo is
   the fallback. `GET https://raw.githubusercontent.com/relaton/{repo}/main/data/{slug}.yaml`.
   First HTTP 200 wins. 404 on both → return stub record `{identifier, body, title="",
   full_text_available=False}` (per existing `Fetcher` "resolved-locally-but-fetch-failed"
   convention).
3. Parse via `_yaml_to_record` (imported from `_sync_relaton`). The mapper is shared so
   live and synced records have identical shape.

### Identifier → slug helper

Best-effort, fixture-driven. Covers:
- `ISO 9001:2015` → `iso-9001-2015`
- `ISO/IEC 27001:2022` → `iso-iec-27001-2022`
- `IEC 62443-3-3:2020` → `iec-62443-3-3-2020`
- `ISO 9001:2015/Amd 1:2020` → `iso-9001-2015-amd-1-2020`

Edge-case slugs that don't round-trip from canonical → upstream (rare but real for
some technical-report variants) yield `None` from the helper, falling through to the
stub record.

### Identifier resolver regex extensions

In `_standards_client.resolve_identifier_local`, after the existing tier-1 patterns:

```python
# ISO joint with IEC: must check before plain ISO/IEC to claim the joint form first
_ISO_IEC_JOINT_RE = re.compile(r"(?i)\b(?:iso[/\s]*iec|iec[/\s]*iso)\s*(\d{1,5}(?:-\d+)*)\s*[:\s-]\s*(\d{4})\b")
_ISO_RE          = re.compile(r"(?i)\biso\s*(\d{1,5}(?:-\d+)*)\s*[:\s-]\s*(\d{4})\b")
_IEC_RE          = re.compile(r"(?i)\biec\s*(\d{1,5}(?:-\d+)*)\s*[:\s-]\s*(\d{4})\b")
```

Returned canonicals: `"ISO/IEC 27001:2022"`, `"ISO 9001:2015"`, `"IEC 62443-3-3:2020"`.

The bare `27001:2022` form (no body prefix) is ambiguous and **deliberately not
matched** — that path is left to the broader sync-time alias rows.

## Tests

Layered like `_sync_standards.py`'s tests in PR 1.

### `test_sync_relaton.py`

- `test_yaml_to_record_plain_iso` — single ISO entry → correct fields
- `test_yaml_to_record_joint_iso_iec` — joint entry → `body="ISO/IEC"`, identifier in `ISO/IEC` form
- `test_yaml_to_record_missing_identifier` — returns `(None, errors)`
- `test_canonical_identifier_iec_only` — IEC-only entry → `body="IEC"`
- `test_loader_cold_sync_inserts_records` — empty cache + fixture tarball → `added` matches fixture count
- `test_loader_resync_same_sha_returns_unchanged` — second call with same SHA → no API/tarball fetch, `unchanged > 0`
- `test_loader_force_resyncs_despite_same_sha` — `force=True` bypasses SHA check
- `test_loader_modified_record_increments_updated` — fixture entry edited → `updated == 1`
- `test_loader_removed_record_marked_withdrawn` — fixture entry removed → row `status="withdrawn"`, `withdrawn == 1`
- `test_loader_withdrawal_pass_aborts_on_mass_disappearance` — sync with a tarball missing >50% of prior ids → `withdrawn == 0`, error appended to report, prior rows retain previous `status`
- `test_loader_joint_dedup_iso_then_iec` — sync ISO then IEC → joint records single-row, aliases merged
- `test_loader_joint_dedup_iec_then_iso` — reverse order → identical final state
- `test_loader_uses_token_when_present` — `SCHOLAR_GITHUB_TOKEN` set → Authorization header sent (assert via respx)

### `test_relaton_live.py`

- `test_identifier_to_slug_iso` / `_joint` / `_iec` / `_with_amendment` — slug shapes
- `test_identifier_to_slug_returns_none_for_unsupported` — odd form → `None`
- `test_live_fetch_iso_hit` — respx returns YAML, fetcher returns parsed record
- `test_live_fetch_falls_back_to_iec_when_iso_404` — first repo 404 → second repo wins
- `test_live_fetch_returns_stub_when_both_404` — neither repo has it → stub record
- `test_live_fetch_caches_as_live_record` — second call returns from cache, no HTTP

### `test_standards_client.py` additions

- `test_resolve_identifier_iso_plain` — `"ISO 9001:2015"` → `("ISO 9001:2015", "ISO")`
- `test_resolve_identifier_iso_no_space` — `"ISO9001:2015"` → same
- `test_resolve_identifier_iso_iec_joint` — `"ISO/IEC 27001:2022"` → `("ISO/IEC 27001:2022", "ISO/IEC")`
- `test_resolve_identifier_iec_only` — `"IEC 62443-3-3:2020"` → `("IEC 62443-3-3:2020", "IEC")`

### `test_cli_sync_standards.py` updates

The PR-1 monkeypatched stub-loader tests are kept. Add:

- `test_sync_standards_iso_real_loader` — invoke with respx-mocked GitHub API + fixture
  tarball; assert exit 0 and `added > 0`.

## HTTP mocking

All `httpx` calls go through `respx` per existing convention. Tarball mocking returns a
real gzipped tarball built in the test from `tests/fixtures/standards/relaton_iso_sample/`
contents — exercises the real `tarfile` extraction code path.

## Out of scope (deferred to later PRs)

- IEEE loader (PR 3 — trivial config addition once PR 2's `RelatonLoader` ships)
- CC and CEN loaders (PR 4)
- Enrichment integration (PR 5)
- Nightly `pytest -m live` smoke job (separate workflow PR)
- Bare-number identifier resolution (`27001:2022` without body prefix)

## Manifest version bumps

`server.json`, `.claude-plugin/plugin/.claude-plugin/plugin.json`,
`.claude-plugin/plugin/.mcp.json` → `1.7.0-rc.2`.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Relaton tarball is large (~50 MB for ISO) — memory pressure during streaming | Use `tarfile.open(fileobj=stream, mode="r|gz")` which reads members sequentially; never load full tarball into memory; the YAML files themselves are small |
| Joint-standard detection misses an edge case (e.g. `docidentifier` list contains `ISO`+`IEC`+`ISO/IEC` all three) | Decision rule prefers explicit `ISO/IEC` typed entry when present; otherwise infers from co-occurrence. Fixture covers both shapes |
| Slug helper diverges from upstream renaming | Live fallback degrades to stub on 404 — never crashes. Synced records (which use the real upstream filenames from the tarball) are unaffected |
| GitHub API quota exhaustion under repeated `--force` testing | `SCHOLAR_GITHUB_TOKEN` env var lifts limit to 5,000 req/hr; documented |
| Withdrawn detection wrongly nukes records if a sync runs against a partially-extracted tarball | If `current_ids` is suspiciously small (e.g. <50% of `prev_ids`), abort the withdrawal pass and add an error to the report. Threshold tunable; starts at 50% |
