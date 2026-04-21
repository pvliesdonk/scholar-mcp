# Plan: Fix codecov/patch status for fork PRs

- **Issue**: pvliesdonk/scholar-mcp#109
- **Branch**: `feat/ci-fork-codecov-fix` (base: `origin/main`)
- **Source of truth**: `pvliesdonk/markdown-vault-mcp@470c061`
- **Date**: 2026-04-11

## Problem

When a PR originates from a fork, the `test` job's `GITHUB_TOKEN` is read-only
for `pull_request` events regardless of the `permissions: statuses: write`
block. This is a GitHub security restriction to prevent fork PRs from writing
to the base repo. The consequence is that the inline "Post codecov/patch
status" step in `.github/workflows/ci.yml` fails with HTTP 403 on fork PRs, so
the `codecov/patch` commit status is never posted and the PR appears perpetually
missing a required check.

Own-branch PRs are unaffected because they run in the base-repo context where
the token is read/write.

## Fix (ported from markdown-vault-mcp@470c061)

`workflow_run` always runs in the **base-repo context**, where `GITHUB_TOKEN`
has `statuses: write` even for runs originating from forks. The fix is:

1. In the test job, compute the patch-coverage state as before, then **save it
   to `patch-coverage.json`** and **upload it as a workflow artifact**.
2. Still attempt to post the status inline (own-branch PRs post here), but add
   `continue-on-error: true` so the fork PR 403 no longer fails the job.
3. Add a new `coverage-status.yml` workflow that triggers on `workflow_run`
   completion, filters to fork PRs, downloads the artifact, and posts the
   commit status from the base-repo context.

## Changes

### `.github/workflows/ci.yml`

Replace the single "Post codecov/patch status" step (lines 135–156) with three
steps, all guarded on `matrix.python-version == '3.13' && github.event_name == 'pull_request'`:

1. **Save patch coverage result** — writes `{state, description}` to
   `patch-coverage.json` via `jq`. Uses `|| 'error'` / `|| 'diff-cover step
   did not run'` fallbacks so the file is always valid even when the
   `diffcover` step was skipped.
2. **Upload patch coverage artifact** — `actions/upload-artifact@v4` with
   `name: patch-coverage`, `retention-days: 1`.
3. **Post codecov/patch status** — unchanged body, but now marked
   `continue-on-error: true` and annotated with a comment explaining why.

### `.github/workflows/coverage-status.yml` (new file)

- Triggers on `workflow_run` for workflow `"CI"`, `types: [completed]`.
- Condition: runs only when `workflow_run.event == 'pull_request'` and
  `head_repository.full_name != repository` (i.e. fork PRs only — own-branch
  PRs already posted from the test job).
- Permissions: `statuses: write`, `actions: read`.
- Steps: `actions/download-artifact@v4` with `run-id` from the upstream run,
  then `actions/github-script@v7` reading `patch-coverage.json` and calling
  `github.rest.repos.createCommitStatus` with `sha = workflow_run.head_sha`.
- `target_url` points at `https://app.codecov.io/gh/pvliesdonk/scholar-mcp`
  (differs from MV's URL — this is the only non-mechanical change).

## Acceptance criteria

- `uv run pytest -x -q` passes (no code changes; sanity).
- `uv run ruff check --fix .` → `uv run ruff format .` → `uv run ruff format --check .` all clean (workflow YAML only; ruff doesn't touch it, but discipline).
- `uv run mypy src/` clean.
- Own-branch PR: inline post step continues to work; `continue-on-error` has
  no effect when the API call succeeds.
- Fork PR (simulated via a separate follow-up): inline post step fails with
  403, `continue-on-error` swallows it, workflow_run fires coverage-status.yml,
  status is posted from base-repo context. Actual fork verification must
  happen post-merge since it requires an external fork.
- Docs: no user-facing behavior change — no README/docs updates required for
  this PR (CI plumbing only).

## Why this lives in its own PR

This is a mechanical port with zero dependency on the later stacked PRs
(plugin/mcpb bundle, repositioning, prerelease). Landing it first unblocks
fork-PR contributors immediately and keeps the stack's blast radius isolated.
