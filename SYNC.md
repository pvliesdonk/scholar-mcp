# Sync: Template ↔ Derived Repos

This template has two known derived repositories:

| Repo | Domain |
|------|--------|
| [pvliesdonk/markdown-vault-mcp](https://github.com/pvliesdonk/markdown-vault-mcp) | Obsidian/Markdown vault |
| [pvliesdonk/image-gen-mcp](https://github.com/pvliesdonk/image-gen-mcp) | Image generation |

When infrastructure improvements land in a derived repo they should be
backported here, and vice-versa.  Domain-specific code (tools, config fields,
CLI subcommands, service objects) is **never** synced.

---

## What is infrastructure vs domain?

**Infrastructure** — sync in both directions:

- `mcp_server.py` — auth wiring, `create_server()`, `build_event_store()`
- `cli.py` — transport handling, HTTP path normalisation, logging setup
- `config.py` — `_ENV_PREFIX`, `get_log_level()`, `_parse_bool()`, `_env()`
  (but **not** domain-specific `ServerConfig` fields)
- `_server_deps.py` — lifespan skeleton, `get_service()` pattern
  (but **not** the actual service object or background tasks)
- `_server_tools.py` — `register_tools(mcp, *, transport)` signature convention
- `pyproject.toml` — build/lint/test/release tooling
- `.github/workflows/` — CI pipelines
- `server.json` — MCP server metadata schema

**Domain** — never sync back to template:

- `ServerConfig` fields beyond `read_only`
- CLI subcommands beyond `serve`
- Business logic in `_server_tools.py` / `_server_resources.py` / `_server_prompts.py`
- The service/collection object in `_server_deps.py`
- Domain-specific tests

---

## Sync checklist: derived repo → template

When a PR in a derived repo changes infrastructure code, open a PR here with
the same change (adapted to the generic module names).

1. `_build_oidc_auth()` / `_build_bearer_auth()` — copy exactly (env prefix
   is the only difference; `_ENV_PREFIX` handles it)
2. `build_event_store()` — copy exactly
3. `cli.py` transport/path normalisation — copy exactly
4. `pyproject.toml` tool config (`ruff`, `mypy`, `pytest`, `semantic_release`)
   — copy exactly
5. GitHub workflows — copy exactly, update repo-specific URLs

## Sync checklist: template → derived repos

When this template is updated, apply the same infrastructure change in each
derived repo:

1. Rename `fastmcp_server_template` → the repo's module name where it appears
2. Rename `MCP_SERVER` → the repo's `_ENV_PREFIX` where it appears in docs/comments
3. Keep all domain logic untouched

---

## Current known divergences

| Item | Template | markdown-vault-mcp | image-gen-mcp |
|------|----------|--------------------|---------------|
| `server.json` per-package env vars | ✅ | ✅ | ❌ legacy format |
| `httpx` ImportError in `_build_oidc_auth` | ✅ | ✅ | ❌ bare import |
| `transport` param in `create_server()` | ✅ | ✅ | check |
| `build_event_store()` | ✅ | ✅ | ✅ |

---

## Approach for long-term maintenance

These repos are too domain-specific to share a single base package, but too
similar in plumbing to maintain independently.  Recommended approach:

- **Tag infrastructure commits** with `infra:` scope in the commit message
  (e.g. `fix(infra): handle httpx ImportError in OIDC auth`).  This makes
  cherry-picking across repos easy: `git log --grep="(infra)"`.

- **Cherry-pick, don't diff-and-paste.**  After landing an infra fix in any
  repo, cherry-pick the commit into the others and resolve the trivial module-
  name conflicts.  The diff stays minimal because domain code is untouched.

- **Keep this file up to date.**  Update the divergences table above whenever
  a sync happens (or doesn't happen intentionally).
