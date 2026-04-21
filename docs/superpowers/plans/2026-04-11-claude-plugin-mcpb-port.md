# Plan: Port Claude Code plugin + mcpb bundle distribution

- **Issue**: pvliesdonk/scholar-mcp#106
- **Branch**: `feat/claude-plugin-mcpb-port` (base: `feat/reposition-citation-landscape`)
- **Source**: `pvliesdonk/markdown-vault-mcp#350`
- **Date**: 2026-04-11

## Scope

Mechanical port of the plugin/mcpb infrastructure from MV#350. The
scholar-specific SKILL.md content is out of scope — this PR drops in a
placeholder SKILL.md that PR 4 (#107) will replace with real scholar-
workflow guidance.

Package name rewiring: `markdown-vault-mcp` → `pvliesdonk-scholar-mcp`
(PyPI), `scholar-mcp` (CLI). Env vars: `MARKDOWN_VAULT_MCP_*` →
`SCHOLAR_MCP_*`. Extras: MV uses `[all]` which bundles FastMCP +
FastEmbed + api embeddings; scholar-mcp's `[all]` and `[mcp]` both
resolve to `fastmcp + uvicorn`, so pinning `[mcp]` keeps the surface
minimal.

## Files to create

### `.claude-plugin/plugin/.claude-plugin/plugin.json`
Plugin metadata. Name `scholar-mcp`, version tracked in lockstep with
server.json via the release workflow.

### `.claude-plugin/plugin/.mcp.json`
Launches via `uvx --from pvliesdonk-scholar-mcp[mcp]==<VERSION>
scholar-mcp serve`. Wires the minimal useful env var set:
- `SCHOLAR_MCP_S2_API_KEY` (optional, the main "please set this" var)
- `SCHOLAR_MCP_READ_ONLY` (default true)
- `SCHOLAR_MCP_CONTACT_EMAIL` (OpenAlex polite pool + Unpaywall)
- `SCHOLAR_MCP_CACHE_DIR`
- `SCHOLAR_MCP_DOCLING_URL` (optional, PDF conversion)
- `SCHOLAR_MCP_EPO_CONSUMER_KEY` / `_SECRET` (optional, patents)
- `FASTMCP_LOG_LEVEL`

### `.claude-plugin/plugin/README.md`
Readme shown in the Claude Code marketplace listing. Rewrite from MV's
version: short pitch, install command, configure env vars, what you
get (tools summary per domain), update command, docs links.

### `.claude-plugin/plugin/skills/scholar-workflow/SKILL.md`
**Placeholder only.** Frontmatter + a one-paragraph note saying the
skill will be authored in the next stacked PR. PR 4 (#107) replaces
this with real content organised by scholarly activity (literature
search, prior art, citation management, full-text retrieval).

### `packaging/mcpb/.gitignore`
Copied from MV.

### `packaging/mcpb/manifest.json.in`
mcpb bundle manifest. Name `scholar-mcp`, display name "Scholar", same
schema as MV's. `user_config` includes all scholar-mcp env vars with
appropriate types and `sensitive: true` on S2 API key, EPO secret,
VLM API key.

### `packaging/mcpb/pyproject.toml.in`
Pin `pvliesdonk-scholar-mcp[mcp]==${VERSION}`.

### `packaging/mcpb/src/server.py`
Entry shim. Imports `scholar_mcp.cli.main` and injects `serve` into
sys.argv. Same shape as MV's shim.

### `packaging/mcpb/build.sh`
Local build script. Envsubst `${VERSION}` only, call `mcpb validate`
then `mcpb pack`. Same shape as MV's.

### `tests/test_packaging_mcpb.py`
Smoke tests ported from MV:
- `cli.main` import target exists
- shim calls `main` and injects `serve`
- manifest template parses and has expected shape (name, version
  substitution, `${DOCUMENTS}` preserved for runtime)
- `--from` does not use local source `.`
- sensitive env vars marked
- pyproject template pins `[mcp]==${VERSION}`
- `plugin.json` shape: name, repository, semver version
- `.mcp.json` pinned `--from` spec matches `plugin.json` version

### `docs/guides/claude-code-plugin.md`
New guide. Install, configure, what you get, update, uninstall.
Adapted for scholar-mcp's env vars and the four source domains.

## Files to modify

### `.github/workflows/release.yml`
- **"Update server.json and uv.lock to released version"** step:
  extend to also update
  `.claude-plugin/plugin/.claude-plugin/plugin.json` and
  `.claude-plugin/plugin/.mcp.json` (version in `plugin.json`,
  `--from` spec in `.mcp.json`). Commit and push all three together,
  then re-point the release tag to the manifest-bump commit via
  `git tag -f` / `git push --force origin refs/tags/v${VERSION}` so
  marketplace installs pointing at `ref: vVERSION` get the bumped
  manifests.
- **New `build-mcpb` job** (after `release`): checks out the release
  tag, installs `@anthropic-ai/mcpb@2.1.2`, renders the manifest /
  pyproject templates with envsubst-restricted-to-`${VERSION}`,
  copies the server shim, validates + packs the bundle, uploads as
  artifact.
- **New `publish-mcpb` job**: downloads the artifact and uploads to
  the GitHub release via `gh release upload --clobber`.
- **New `publish-claude-plugin-pr` job**: checks out
  `pvliesdonk/claude-plugins` catalog repo, bumps the
  `markdown-vault-mcp` → `scholar-mcp` entry in
  `.claude-plugin/marketplace.json`, opens a PR via
  `peter-evans/create-pull-request@v7`.

### `.gitignore`
Add `.worktrees/` (same as MV).

### `CLAUDE.md`
Add **gate 6: Manifest version lockstep** — `server.json`, plugin
`plugin.json`, and plugin `.mcp.json` must carry the same version.
Add the two new paths (`.claude-plugin/plugin/README.md` and
`docs/guides/claude-code-plugin.md`) to the docs-update checklist
section.

### `README.md`
Add "Claude Desktop (.mcpb bundle)" and "Claude Code plugin" sections
to the Installation block.

### `docs/index.md`
Add "As a Claude Code plugin" quick-start tab (or bullet — whatever
fits the current docs/index.md Quick-start block).

### `docs/installation.md`
Add a Claude Code Plugin section.

### `mkdocs.yml`
Add `guides/claude-code-plugin.md` to the nav + left sidebar.

## Secrets required (for the workflow to actually run)

- `CLAUDE_PLUGINS_PAT` — repository secret. PAT with write access to
  the `pvliesdonk/claude-plugins` catalog repo. Must be configured
  before the next release fires, otherwise the
  `publish-claude-plugin-pr` job will fail but won't block the rest
  of the release (it's a separate job, no `needs:` chain into
  publish-pypi/docker/registry).

This secret provisioning is **out of scope for this PR** — will be
flagged in the PR body as a follow-up operational step.

## Acceptance criteria

- All gates pass: pytest, ruff, mypy.
- `packaging/mcpb/build.sh` runs locally without mcpb installed (the
  script should exit with a clear install hint) and succeeds once
  mcpb is installed. *Out of scope for CI — local only.*
- `tests/test_packaging_mcpb.py` passes — asserts the manifest
  template, plugin.json, and .mcp.json are syntactically valid and
  mutually consistent.
- Docs updated (README, docs/index.md, docs/installation.md,
  mkdocs.yml, new guide).
- Placeholder SKILL.md is clearly marked "replaced in PR 4" so the
  next commit doesn't accidentally ship a stub.

## Out of scope

- Real scholar-workflow SKILL.md content (PR 4 / #107).
- Prerelease mode for release.yml (PR 5 / #108).
- Catalog-repo entry creation — the `pvliesdonk/claude-plugins`
  catalog already exists; the workflow just bumps the existing entry.
  Creating the initial entry is a one-time manual op, not part of
  this PR.
- Any `pvliesdonk/claude-plugins` catalog-repo changes (separate repo).
