# Plan: Reposition scholar-mcp as a scholarly-sources MCP server

- **Issue**: pvliesdonk/scholar-mcp#110
- **Branch**: `feat/reposition-citation-landscape` (base: `feat/ci-fork-codecov-fix`)
- **Date**: 2026-04-11

## Background

The repo started as a paper-only wrapper around Semantic Scholar. Patents,
books, and standards were added over subsequent milestones. The surface
still signals "academic literature" everywhere — the README headline, the
docs/index.md intro, the tool-reference ordering, and server.json all read
as if papers are the product and the rest are optional add-ons.

The user's reframing: if you write papers, you need all four source types
for citations and prior art. They are peer domains of the same discipline —
the scholarly citation landscape — not a paper product with sidecars.

Per-domain depth is still uneven (papers: 10+ tools with a citation graph;
standards: 3 tools with full-text). That asymmetry is real and worth
acknowledging, but it reflects structural differences in public data
availability, not a value hierarchy. The roadmap in GitHub issues and
milestones tracks where depth is being added.

## Scope

This PR is a **positioning rewrite**, not a capability change. No code
behavior changes. All edits are to user-facing docs + server.json +
config.py docstring where it's easy.

## Files to change

### `README.md`

- Line 13 headline: from
  > A FastMCP server providing structured academic literature access via Semantic Scholar, with OpenAlex enrichment and optional docling-serve PDF conversion.

  to:
  > A FastMCP server for the scholarly citation landscape — **papers**, **patents**, **books**, and **standards** — giving LLMs a unified way to search, cross-reference, and retrieve prior art across all four source types via Semantic Scholar, EPO OPS, Open Library, and standards bodies, with OpenAlex enrichment and optional docling-serve PDF/full-text conversion.

- Feature list: reorganise so the four source domains are bullets 1–4, each
  describing that domain's capabilities at the same level of detail. Keep
  the cross-cutting bullets (PDF conversion, caching, auth, transport) after.
- Add a short "Coverage by domain" paragraph after the feature list that
  says: "Per-domain depth is uneven — papers currently have the richest
  tool surface, standards the leanest. Parity work is tracked in
  [GitHub issues](https://github.com/pvliesdonk/scholar-mcp/issues) and
  [milestones](https://github.com/pvliesdonk/scholar-mcp/milestones). The
  roadmap shows intent, not a completeness commitment."
- Update the MCP Tools section ordering: Papers (Search & Retrieval / Citation
  Graph / Recommendations / Citation Generation), Patents, Books, Standards,
  then PDF Conversion / Utility / Task Polling.

### `docs/index.md`

- Line 3: same headline rewrite as README.
- Line 7: "19 tools" → "27 tools"; "search, explore, and retrieve academic
  papers" → "search, cross-reference, and retrieve papers, patents, books,
  and standards".
- Feature bullets: add one bullet each for Patents, Books, Standards as
  peers of Search & retrieval. Move Citation graph under Papers since it's
  currently paper-only. Keep the cross-cutting bullets afterwards.
- Architecture diagram: add Patent / Book / Standards boxes at the same
  level as Search / Citation / PDF, and add the backend APIs (EPO OPS,
  Open Library, NIST/IETF/W3C/ETSI) next to S2 / OpenAlex / docling.

### `docs/tools/index.md`

- Line 3: "25 tools across ten categories" → "27 tools organised by
  scholarly source type".
- Restructure top-level sections: **Papers** (with sub-sections Search &
  Retrieval / Citation Graph / Recommendations / Citation Generation),
  **Patents**, **Books**, **Standards**, **Utility**, **PDF Conversion**,
  **Task Polling**. Move existing Standards content up from the bottom.
- Mirror the README "Coverage by domain" note as a block near the top.

### `server.json`

- Line 5 description:
  > "Academic literature search, citation graphs, and PDF conversion via Semantic Scholar."

  →

  > "Scholarly-sources MCP server for papers, patents, books, and standards — search, cross-reference, and retrieve prior art across Semantic Scholar, EPO OPS, Open Library, and standards bodies."

  (Must stay under any MCP registry length limits — target ~200 chars.)

### `src/scholar_mcp/config.py`

- The class docstring and attribute docstrings are neutral and don't need
  paper-centric corrections. **Skip.** Keeping this in the plan so I don't
  forget to verify by re-reading the file.

### `docs/guides/index.md`

- Leave alone for this PR — the existing guides are all legitimately cross-
  cutting (Claude Desktop setup, auth, PDF conversion, citation graphs,
  deployment). Per-domain guides are a separate follow-up.

## Out of scope

- Any tool renames (tracked in #111, will run parallel to the stack).
- Adding new per-domain guides (follow-up work).
- Any change to tool behavior, parameters, or return shapes.
- Changes to CLAUDE.md or TEMPLATE.md.

## Acceptance criteria

- Gates: `pytest -x -q`, `ruff check --fix .` → `ruff format .` →
  `ruff format --check .`, `mypy src/` — all clean.
- Patch coverage ≥ 80%: not applicable (no Python source changes).
- README.md and docs/** reflect the new framing consistently — no
  remaining "academic literature" framing in top-level positioning.
- Tool count is 27 everywhere it appears in docs.
- server.json description reflects the new framing.

## Commit message

```
docs: reposition scholar-mcp as a scholarly-sources MCP server

Rewrite README, docs/index.md, docs/tools/index.md, and server.json to
frame papers, patents, books, and standards as peer source domains of
the scholarly citation landscape rather than as a paper product with
sidecars. Per-domain depth is still uneven — papers currently have the
richest tool surface, standards the leanest — but parity is roadmap
work, not a value hierarchy. Roadmap pointer is GitHub issues and
milestones; no separate roadmap doc.

Corrects stale tool counts (19/25 → 27) and reorders the tool
reference so the four source domains are peer top-level sections.

No behavior changes.

Closes #110.
```
