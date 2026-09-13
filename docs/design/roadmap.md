# Scholar MCP roadmap

This is agent-authored synthesis, not a record of decisions. Tag each
argument `stated` (the user's words), `derived` (synthesis), or
`evidenced` (with a durable locator). Read the
[`roadmapping` skill](../../.agents/skills/roadmapping/SKILL.md) before
charting or refining work.

Epics are parent issues for stories; packages are milestones for single
release cuts. GitHub holds membership, dependencies and progress. This
index holds the argument for the direction and order.

## Direction

### Reliable base

- **[derived]** Stabilize the v2 foundation before committing another broad
  capability. Correctness defects, operational follow-ups, and residual
  template drift share the first package because each makes later feature work
  harder to evaluate in production. The template adoption itself is tracked by
  [#411](https://github.com/pvliesdonk/scholar-mcp/issues/411).

### Operator-provided corpus

- **[evidenced: [epic #353](https://github.com/pvliesdonk/scholar-mcp/issues/353)
  and `docs/design/operator-corpus.md`]** Operators should be able to identify
  their own documents through a manifest, attach known documents to scholarly
  records, and retrieve them through pointers while retaining ownership of the
  files. The frozen outcome stays broader than the first package so optional
  semantic context can be decided separately.

### Standards discovery and use

- **[derived]** [Epic #412](https://github.com/pvliesdonk/scholar-mcp/issues/412)
  collects the standards story around identification, access, enrichment,
  citation, lifecycle, and cross-linking. Its former milestone mixed many
  independently useful capabilities; refinement
  [#417](https://github.com/pvliesdonk/scholar-mcp/issues/417) must find a
  release-sized next slice before any are committed to a package.

### Patent research workflows

- **[derived]** [Epic #413](https://github.com/pvliesdonk/scholar-mcp/issues/413)
  collects the patent story around discovery, document use, citations, status,
  and scholarly cross-links. Refinement
  [#418](https://github.com/pvliesdonk/scholar-mcp/issues/418) must identify a
  coherent package from its independently shippable children.

### Book and chapter resolution

- **[derived]** [Epic #414](https://github.com/pvliesdonk/scholar-mcp/issues/414)
  collects the book story around edition and chapter identity, enrichment,
  availability, previews, citations, and reusable assets. Refinement
  [#419](https://github.com/pvliesdonk/scholar-mcp/issues/419) must identify a
  coherent package without pulling unrelated maintenance into the story.

### Structural health

- **[evidenced: [epic #234](https://github.com/pvliesdonk/scholar-mcp/issues/234)]**
  The diff gate prevents new structural debt while existing findings are
  removed independently. The direction is complete when the whole-tree
  exemption can be removed; refinement
  [#416](https://github.com/pvliesdonk/scholar-mcp/issues/416) checks that the
  recorded children still cover that outcome.

## Packages

- **[derived] [010 stabilization](https://github.com/pvliesdonk/scholar-mcp/milestone/14)
  (patch):** finish the correctness, operational, and template follow-ups that
  make the v2 base dependable before broadening the product surface.
- **[evidenced: [epic #353](https://github.com/pvliesdonk/scholar-mcp/issues/353)]
  [020 corpus foundations](https://github.com/pvliesdonk/scholar-mcp/milestone/16)
  (minor):** follow stabilization with the manifest, record attachment, and
  pointer path because those three form a useful operator workflow without the
  optional semantic subsystem.

Do not copy item lists or progress here. An issue with no milestone is
backlog; commit it to a package when it should ship in that cut.

## Known unknowns

- **[derived] Which domain story should follow corpus foundations?** Resolved
  by the standards, patent, and books refinement issues
  [#417](https://github.com/pvliesdonk/scholar-mcp/issues/417),
  [#418](https://github.com/pvliesdonk/scholar-mcp/issues/418), and
  [#419](https://github.com/pvliesdonk/scholar-mcp/issues/419). The answer does
  not change the two committed packages.
- **[evidenced: [#357](https://github.com/pvliesdonk/scholar-mcp/issues/357)]
  When is semantic context over an identified corpus document viable?** The
  issue carries the external dependency that resolves it. The answer does not
  block the three-feature corpus foundation.
- **[evidenced: [#234](https://github.com/pvliesdonk/scholar-mcp/issues/234)]
  Do the recorded structural children still cover removal of the exemption?**
  Resolved by refinement
  [#416](https://github.com/pvliesdonk/scholar-mcp/issues/416); it can proceed
  independently of the package sequence.

## Revisions

- **2026-09-12 — [derived]:** Adopted the v8.2 roadmapping convention. Kept
  only the stabilization and corpus-foundation cuts as packages; converted the
  broader standards, patents, books, and structural buckets into story epics
  with backlog children because each theme exceeded one credible release cut.
