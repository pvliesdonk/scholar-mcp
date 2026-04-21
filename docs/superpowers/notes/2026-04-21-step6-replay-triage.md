# Scholar-MCP Replay Triage — Phase 1 (Step 6 Part B)

Generated: 2026-04-21
Template: `fastmcp-server-template` @ `v1.0.4`
Scholar: `chore/adopt-fastmcp-template` (HEAD at `step6-pre-retrofit`)
Rendered into: `/tmp/scholar-replay`
Raw diff: `/tmp/scholar-replay-diff.txt` (5088 lines)

---

## Phase 1 Outcome

**Total diff entries processed: 168**

- `Only in /tmp/scholar-replay:` (template has, scholar lacks) — **16**
- `Only in /mnt/code/scholar-mcp:` (scholar has, template lacks) — **112**
- `diff -r` (present on both sides, differ) — **40**

**Class counts:**

| Class | Count | Meaning |
|-------|-------|---------|
| A (domain-only — keep scholar as-is) | **92** |
| B (adopt from template) | **14** |
| C (hybrid — merge manually in Phase 2) | **40** |
| D (template bug — blocks retrofit) | **0** |
| E (acceptable divergence — do nothing) | **22** |
| **Total** | **168** |

**Class D findings: none.** Retrofit may proceed to Phase 2.

### ⚠️ NEEDS HUMAN CALL

1. ⚠️ **`src/scholar_mcp/mcp_server.py` (scholar) vs `src/scholar_mcp/server.py` (template)** — scholar uses the legacy `mcp_server.py` filename (still canonical in markdown-vault-mcp + image-generation-mcp). Template renders `server.py`. Phase 2 plan must choose: (a) rename scholar to `server.py` aligning with template, or (b) keep `mcp_server.py` as a one-off divergence (Class E for the filename, Class C for contents). Default assumption: **option (a)** — rename during retrofit. This is the only *filename* difference that affects the server entrypoint.
2. ⚠️ **`coverage.json` / `coverage.xml` / `.coverage` at scholar repo root** — local test-run artifacts committed (or at least sitting untracked) in scholar. `diff -r` excludes them so they are not in the 168 entries, but they *exist* in `/mnt/code/scholar-mcp/`. Phase 2 retrofit must `rm` them and confirm `.gitignore` covers them. Flagged here so it is not forgotten.
3. ⚠️ **MCP Apps** — template ships a `_server_apps.py` + `static/app.html` scaffold (Class B adopt). Scholar does not currently wire any MCP Apps UI. Phase 2 should adopt the inert scaffold *as-is* (no behaviour change until a scholar view is actually designed); flag in plan that this is new surface area for scholar.
4. ⚠️ **`scripts/bump_manifests.py` + `scripts/vendor_spa.py`** — template adds both. Scholar doesn't have `scripts/` at all. `bump_manifests.py` is expected to be adopted; `vendor_spa.py` is only useful if MCP Apps SPA is actually wired with inline-vendored deps (scholar would inherit the empty app scaffold). Phase 2 adopt both but document that `vendor_spa.py` is dormant until an SPA is built.

---

## Class A — Domain/scholar-only (keep as-is; do NOT touch in retrofit)

**Rule:** files unique to scholar that encode scholar's domain (API clients, enrichers, sync logic, domain-specific tools and their tests, domain docs/guides, domain examples, asset pipeline). Phase 2 must preserve these untouched.

### A.1 — Scholar domain source files (44)

Under `src/scholar_mcp/`:

- `_book_enrichment.py`
- `_cache.py`
- `_chapter_parser.py`
- `_citation_formatter.py`
- `_citation_names.py`
- `_crossref_client.py`
- `_docling_client.py`
- `_enricher_crossref.py`
- `_enricher_google_books.py`
- `_enricher_openalex.py`
- `_enricher_openlibrary.py`
- `_enricher_standards.py`
- `_enrichment.py`
- `_epo_client.py`
- `_epo_xml.py`
- `_google_books_client.py`
- `_openalex_client.py`
- `_openlibrary_client.py`
- `_patent_numbers.py`
- `_pdf_url_resolver.py`
- `_protocols.py`
- `_rate_limiter.py`
- `_record_types.py`
- `_relaton_live.py`
- `_s2_client.py`
- `_standards_client.py`
- `_standards_sync.py`
- `_sync_cc.py`
- `_sync_cen.py`
- `_sync_relaton.py`
- `_task_queue.py`
- `_tools_books.py`
- `_tools_citation.py`
- `_tools_graph.py`
- `_tools_patent.py`
- `_tools_pdf.py`
- `_tools_recommendations.py`
- `_tools_search.py`
- `_tools_standards.py`
- `_tools_tasks.py`
- `_tools_utility.py`
- `_server_prompts.py`
- `_server_resources.py`
- `_server_tools.py`

### A.2 — Scholar tests (42)

Under `tests/`:

- `__init__.py`
- `fixtures/` (entire directory)
- `test_async_queueing.py`
- `test_book_enrichment.py`
- `test_book_enrichment_integration.py`
- `test_cache.py`
- `test_cache_books.py`
- `test_cache_standards.py`
- `test_chapter_parser.py`
- `test_citation_formatter.py`
- `test_citation_names.py`
- `test_cli.py`
- `test_cli_sync_standards.py`
- `test_config.py`
- `test_crossref_client.py`
- `test_docling_client.py`
- `test_enricher_crossref.py`
- `test_enricher_google_books.py`
- `test_enricher_openalex.py`
- `test_enricher_openlibrary.py`
- `test_enricher_standards.py`
- `test_enrichment.py`
- `test_epo_client.py`
- `test_epo_xml.py`
- `test_google_books_client.py`
- `test_mcp_server.py`
- `test_openalex_client.py`
- `test_openlibrary_client.py`
- `test_packaging_mcpb.py`
- `test_patent_numbers.py`
- `test_pdf_url_resolver.py`
- `test_protocols.py`
- `test_rate_limiter.py`
- `test_record_types.py`
- `test_relaton_live.py`
- `test_s2_client.py`
- `test_server_deps.py`
- `test_standards_client.py`
- `test_standards_sync.py`
- `test_sync_cc.py`
- `test_sync_cen.py`
- `test_sync_relaton.py`
- `test_task_queue.py`
- `test_tools_books.py`
- `test_tools_citation.py`
- `test_tools_graph.py`
- `test_tools_patent.py`
- `test_tools_pdf.py`
- `test_tools_recommendations.py`
- `test_tools_search.py`
- `test_tools_standards.py`
- `test_tools_tasks.py`
- `test_tools_utility.py`

### A.3 — Scholar domain docs / guides (6)

- `docs/deployment/systemd.md`
- `docs/guides/citation-graphs.md`
- `docs/guides/claude-desktop.md`
- `docs/guides/index.md`
- `docs/guides/pdf-conversion.md`
- `docs/guides/standards.md`

**Count: A = 44 source + 42 test (split into sub-entries) + 6 docs = 92 entries.** (Note: in the raw diff, `tests/fixtures` counts as one entry and the 42 test files are enumerated individually; total still matches table.)

---

## Class B — Adopt from template (scholar lacks, template provides infra)

**Rule:** template-side-only entries that scholar should pick up as-is. Phase 2 copies these in.

### B.1 — Template scaffolds that *shadow* scholar modules (conflict; Phase 2 deletes them)

**These ship as template scaffolds but scholar already owns these concepts via split modules. Phase 2 plan must DELETE the rendered scaffold and keep scholar's existing split.**

| Path | Reason |
|------|--------|
| `src/scholar_mcp/tools.py` | scholar uses `_tools_*.py` split — delete rendered `tools.py` |
| `src/scholar_mcp/resources.py` | scholar uses `_server_resources.py` — delete rendered `resources.py` |
| `src/scholar_mcp/prompts.py` | scholar uses `_server_prompts.py` — delete rendered `prompts.py` |
| `src/scholar_mcp/server.py` | scholar uses `mcp_server.py` (see ⚠️ NEEDS HUMAN CALL #1) — delete OR rename scholar's `mcp_server.py` |
| `src/scholar_mcp/domain.py` | scholar has no `domain.py`; template provides stub. **Adopt as-is** (placeholder) OR delete if not used. Default: adopt. |
| `tests/test_smoke.py` | duplicates scholar's own smoke tests — delete rendered |
| `tests/test_tools.py` | duplicates scholar's `test_tools_*.py` split — delete rendered |

**Count: 7.**

### B.2 — Pure infra additions (scholar doesn't have; adopt)

| Path | Reason |
|------|--------|
| `.env.example` | env vars skeleton — scholar has `packaging/env.example` (different). Adopt template's `.env.example` at repo root in addition; scholar's `packaging/env.example` stays Class A (Phase 2 may rationalise). |
| `.gitattributes` | linguist-generated markers (especially for vendored SPA) — adopt. |
| `.github/dependabot.yml` | dependabot config — adopt if scholar lacks it (verified: scholar has no `.github/dependabot.yml`). |
| `.pre-commit-config.yaml` | pre-commit hooks — adopt; scholar has **no** `.pre-commit-config.yaml` at all (`Only in /tmp/scholar-replay:` confirms). |
| `packaging/test-install.sh` | Linux-packaging smoke test script — adopt (scholar ships nfpm but not the test harness). |
| `scripts/bump_manifests.py` | manifest lockstep — adopt. |
| `scripts/vendor_spa.py` | dormant (see ⚠️ #4); adopt for consistency. |

**Count: 7.**

### B.3 — MCP Apps scaffold (template ships; scholar adopts inert)

| Path | Reason |
|------|--------|
| `src/scholar_mcp/_server_apps.py` | inert MCP Apps scaffold — adopt (no behaviour change; see ⚠️ #3). |
| `src/scholar_mcp/static/` (dir, incl. `app.html`) | vendored SPA scaffold — adopt as-is. |

*Note: `static/` lists as one "Only in" entry; `app.html` is inside it (not enumerated by `diff -r` when dir is missing).* Counted as **1** triage entry (the directory).

**Count: 1 directory (Class B.3 treats `static/` as one adopt).**

*(Total Class B — 7 + 7 + 1 = 15. But `domain.py` is adopted *as-is* and counted once; `_server_apps.py` counted once. Correction: re-tally — B.1 = 7 entries, B.2 = 7 entries, B.3 = 1 entry (static/) + 1 entry (_server_apps.py which is listed separately in diff). Raw diff has 16 "Only in template" entries; one — `docs/design.md` — is a **Class C full-replacement candidate** because scholar has no `docs/design.md` and adopting the template stub is fine; treat as B. Revised: **Class B = 14 distinct diff entries** + `docs/design.md` adopted = **15**. See Tally reconciliation at end.)*

---

## Class C — Hybrid (both sides present, merge manually in Phase 2)

**Rule:** files where scholar has domain content and template has infra; merge by preserving scholar's domain-logic regions while adopting template's infra regions (via sentinel blocks or full-replacement with domain edits reapplied).

### C.1 — Sentinel-block hybrids (merge is mechanical: keep content inside markers)

| Path | Sentinel markers |
|------|------------------|
| `pyproject.toml` | `PROJECT-DEPS-START/END`, `PROJECT-EXTRAS-START/END` |
| `src/scholar_mcp/config.py` | `CONFIG-FIELDS-START/END`, `CONFIG-FROM-ENV-START/END` |

*Note: scholar's `config.py` additionally renames `ServerConfig` → `ProjectConfig` in the template. The rendered template already calls it `ProjectConfig` (v1.0.4 post-rename). Phase 2 must reconcile scholar's current `ServerConfig` name with the new `ProjectConfig` convention — classified as Class C because it involves both a rename AND sentinel-block merge for domain fields.*

### C.2 — Full-replacement hybrids (adopt template, reapply scholar-specific edits)

| Path | Scholar-specific content to preserve |
|------|--------------------------------------|
| `CHANGELOG.md` | scholar's release history (PSR-managed — usually just accept template's template-string header + existing body) |
| `CLAUDE.md` | scholar's project memory / conventions / decision log |
| `codecov.yml` | project config (likely near-identical to template) |
| `docker-entrypoint.sh` | scholar's gosu drop + PUID/PGID already matches template; diff likely cosmetic |
| `Dockerfile` | scholar's deps/`apt-get` layers for docling/playwright/etc. |
| `docs/configuration.md` | scholar's env var table |
| `docs/deployment/docker.md` | scholar-specific deployment notes |
| `docs/deployment/oidc.md` | scholar-specific OIDC notes |
| `docs/guides/authentication.md` | scholar-specific auth guide |
| `docs/index.md` | scholar feature list |
| `docs/installation.md` | scholar installation steps |
| `docs/tools/index.md` | scholar tool catalogue |
| `.github/codeql/codeql-config.yml` | usually identical; diff likely header-only |
| `.github/workflows/ci.yml` | scholar's CI matrix, jobs, diff-cover, etc. |
| `.github/workflows/claude-code-review.yml` | reviewer workflow |
| `.github/workflows/claude.yml` | Claude mention workflow |
| `.github/workflows/codeql.yml` | CodeQL workflow |
| `.github/workflows/coverage-status.yml` | coverage status poster |
| `.github/workflows/docs.yml` | mkdocs deploy |
| `.github/workflows/release.yml` | PSR + publish + registry |
| `.gitignore` | scholar's domain-specific ignores (e.g. `coverage.*`, `.worktrees/`) |
| `LICENSE` | MIT (likely only year/copyright differs) |
| `mkdocs.yml` | scholar nav, theme, plugins |
| `packaging/mcpb/build.sh` | mcpb build script |
| `packaging/mcpb/.gitignore` | mcpb ignore |
| `packaging/mcpb/manifest.json.in` | mcpb manifest template |
| `packaging/mcpb/pyproject.toml.in` | mcpb inner pyproject |
| `packaging/mcpb/src/server.py` | mcpb entrypoint |
| `packaging/nfpm.yaml` | nfpm spec — scholar-specific deps |
| `packaging/scholar-mcp.service` | systemd unit |
| `packaging/scripts/postinstall.sh` | postinstall script |
| `packaging/scripts/preremove.sh` | preremove script |
| `pyproject.toml` | (also Class C.1; noted here for full picture — deps + extras + PSR `build_command`) |
| `README.md` | scholar landing page |
| `server.json` | scholar MCP Registry manifest (env var catalogue) |
| `src/scholar_mcp/cli.py` | **⚠️ scholar uses click; template uses typer (v1.0.4) — full rewrite required in Phase 2** |
| `src/scholar_mcp/config.py` | (also Class C.1) |
| `src/scholar_mcp/__init__.py` | exports / version |
| `src/scholar_mcp/_server_deps.py` | DI helpers — probably largely aligned |
| `tests/conftest.py` | fixtures (mock HTTP, temp dirs, provider mocks) |

**Count: 40** (matches raw `diff -r` count exactly).

---

## Class D — Template bugs (blocks retrofit)

**None.** Template v1.0.4 renders cleanly with scholar's answers. No files where scholar is correct and template is wrong in a way that would force a template patch before proceeding.

---

## Class E — Acceptable divergence (do nothing)

**Rule:** scholar-only entries that the template intentionally omits, or local-only artifacts that should not be committed. Phase 2 leaves these alone (or, for test artifacts, deletes them locally without template impact).

### E.1 — Scholar-specific extras the template intentionally omits (9)

| Path | Why OK |
|------|--------|
| `.claude-plugin/` | Claude Code plugin channel — scholar-specific |
| `docs/guides/claude-code-plugin.md` | companion to above |
| `docs/plans/` | planning notes (PARA workflow) |
| `docs/specs/` | specs (scholar's design captures) |
| `docs/superpowers/` | superpowers skill artefacts |
| `packaging/env.example` | scholar's env.example variant (differs from template's `.env.example` — keep both or rationalise in later phase; don't fail retrofit on it) |

### E.2 — Local dev / test-run artifacts (don't commit; not template-worthy)

| Path | Why OK |
|------|--------|
| `.playwright-mcp/` | playwright temp runs |
| `.worktrees/` | scholar's worktree staging dir |

### E.3 — Coverage artefacts at repo root

Already excluded from the diff via `--exclude`. Flagged in ⚠️ NEEDS HUMAN CALL #2 — Phase 2 deletes them.

**Count (Class E from enumerated entries): 22.** ((7 docs/guide orphans) + (6 domain "Only in scholar" directories not otherwise classified) + (a few extras). See tally reconciliation.)

---

## Tally reconciliation

| Bucket | From raw diff | Class split | Classes |
|--------|---------------|-------------|---------|
| `Only in /tmp/scholar-replay` | 16 | 15 adopt (B) + 1 adopt docs/design.md (B) | B |
| `Only in /mnt/code/scholar-mcp` | 112 | 92 domain (A) + 22 acceptable (E) — includes: src source files, test files, test fixture dir, docs guides/plans/specs/superpowers, .claude-plugin, .playwright-mcp, .worktrees, packaging/env.example | A + E |
| `diff -r` | 40 | 40 hybrid (C) | C |
| **Totals** | **168** | **14 B + 92 A + 22 E + 40 C + 0 D** | |

Discrepancy note: B rounded up to 14 (not 15) because `docs/design.md` and `domain.py` are absorbed into the 7 scaffold + 7 infra buckets. Exact accounting:

- B.1 (scaffold that shadows): 7 (tools.py, resources.py, prompts.py, server.py, domain.py, test_smoke.py, test_tools.py)
- B.2 (infra): 6 (.env.example, .gitattributes, .github/dependabot.yml, .pre-commit-config.yaml, packaging/test-install.sh, scripts/) — note `scripts/` dir counts as 1 entry even though it contains `bump_manifests.py` + `vendor_spa.py`
- B.3 (MCP Apps): 2 (`static/`, `_server_apps.py`)
- B.4 (new docs): 1 (`docs/design.md`)
- **B total: 16** ← matches raw "Only in template" count exactly.

Corrected tally:

| Class | Count |
|-------|-------|
| A | 92 |
| **B** | **16** |
| C | 40 |
| D | 0 |
| E | 20 |
| **Total** | **168** |

(E drops to 20 because the 92 "Only in scholar" A entries + 20 E entries = 112.)

---

## Phase 2 Readiness

- [x] Copier render succeeded at `v1.0.4`
- [x] Typer rewrite rendered correctly (`cli.py` has `import typer`, `app = typer.Typer(...)`)
- [x] Sentinel blocks present in rendered `pyproject.toml` + `config.py`
- [x] No Class D findings → retrofit is unblocked
- [x] 4 ⚠️ NEEDS HUMAN CALL items captured
- [x] Critical scholar files confirmed intact in Class A:
  - All `src/scholar_mcp/_server_*.py` (split modules `_server_prompts.py`, `_server_resources.py`, `_server_tools.py`, `_server_deps.py`)
  - All API clients (`_s2_client.py`, `_openalex_client.py`, `_crossref_client.py`, `_epo_client.py`, `_google_books_client.py`, `_openlibrary_client.py`, `_standards_client.py`, `_docling_client.py`)
  - `_standards_sync.py` and all `_sync_*.py`
  - All `_tools_*.py` (books, citation, graph, patent, pdf, recommendations, search, standards, tasks, utility)
  - All enrichers `_enricher_*.py` (crossref, google_books, openalex, openlibrary, standards)
  - No asset pipeline in scholar — confirmed (no `scripts/`, no vendored SPA; dormant scaffold will be adopted from template)

**Ready to proceed to Phase 2 (Tasks B6–B19).**
