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
  template drift shared the first package, `010 stabilization`, now closed,
  because each makes later feature work harder to evaluate in production. The template adoption itself is tracked by
  [#411](https://github.com/pvliesdonk/scholar-mcp/issues/411).
- **[evidenced: [ADR 0001](../decisions/0001-do-not-build-an-offline-semantic-scholar-store.md)]**
  Keep Semantic Scholar resilience on the live API path. An offline Datasets
  store is not planned because the measured storage and maintenance cost does
  not justify the lookup coverage it could provide.

### Library access routes

- **[stated]** When Scholar MCP cannot fetch a paper, it should hand the user
  links into their own library's systems, opt-in and configured by the
  operator, without the server ever following them. Shadow libraries may be
  configured the same way but are never fetched or shipped as a default.
- **[evidenced: [epic #538](https://github.com/pvliesdonk/scholar-mcp/issues/538)
  and `docs/design/access-links.md`]** One generic template list covers
  OpenURL link resolvers (both OpenURL versions), inter-library loan forms,
  login redirectors and publisher links, with a bare doi.org link when nothing
  is configured. The epic is closed; its outcome shipped in the
  `v3.1.0 access-links` cut.
- **[derived]** Agents running on a licensed network can open those links
  where the server cannot. Bringing such a PDF back into the server for
  conversion is [#546](https://github.com/pvliesdonk/scholar-mcp/issues/546),
  a standalone feature rather than a new epic: the story it continues is
  done, and the open question is sizing, not direction.

### Hardening shipped tools

- **[derived]** Defects on tools that already shipped go ahead of new
  capability. The lead item is
  [#514](https://github.com/pvliesdonk/scholar-mcp/issues/514):
  `fetch_pdf_by_url` fetches caller-chosen URLs with no private-address
  filter, a security gap on a deployed server that should not wait for a
  minor cut.

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

- **[stated] [015 hardening](https://github.com/pvliesdonk/scholar-mcp/milestone/22)
  (patch):** defects on shipped tools, led by
  [#514](https://github.com/pvliesdonk/scholar-mcp/issues/514). The
  maintainer chose to ship these before corpus foundations.
- **[evidenced: [epic #353](https://github.com/pvliesdonk/scholar-mcp/issues/353)]
  [020 corpus foundations](https://github.com/pvliesdonk/scholar-mcp/milestone/16)
  (minor):** the manifest, record attachment, and pointer path, because those
  three form a useful operator workflow without the optional semantic
  subsystem.
- **[stated] [030 agent-fetched-pdfs](https://github.com/pvliesdonk/scholar-mcp/milestone/23)
  (minor):** upload-then-convert for PDFs an agent fetched through a library
  link ([#546](https://github.com/pvliesdonk/scholar-mcp/issues/546)). It
  follows corpus foundations at the maintainer's choice. **[derived]** It may
  split into several features once sized; they stay in this package.

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
- **[derived] Is caching licensed full text on a shared server acceptable?**
  Raised in [#546](https://github.com/pvliesdonk/scholar-mcp/issues/546); it
  decides whether an upload is cached for everyone. It is an operator policy
  call, resolved when #546 is sized, before `030 agent-fetched-pdfs` is
  committed to code.
- **[evidenced: [#234](https://github.com/pvliesdonk/scholar-mcp/issues/234)]
  Do the recorded structural children still cover removal of the exemption?**
  Resolved by refinement
  [#416](https://github.com/pvliesdonk/scholar-mcp/issues/416); it can proceed
  independently of the package sequence.

## Revisions

- **2026-11-05 — [stated] package order; [derived] the rest:** Access links
  shipped in v3.1.0, so its package left the list and the direction now
  records it as delivered. Added `015 hardening` ahead of corpus foundations
  and `030 agent-fetched-pdfs` after it, both at the maintainer's request.
  The v3.1.1 patch cut had stamped and closed the corpus-foundations
  milestone although none of its items shipped; it was reopened and renamed
  back to `020 corpus foundations`. Backlog issues titled `feat` moved from the
  legacy `enhancement` label to the form label `feature`.

- **2026-11-02 — [stated]:** Added the library access routes direction (epic
  [#538](https://github.com/pvliesdonk/scholar-mcp/issues/538)) and its
  package, `010 access-links`, ahead of corpus foundations at the
  maintainer's request. Dropped `010 stabilization` from the package list:
  that milestone is closed.

- **2026-09-22 — [evidenced: [#406](https://github.com/pvliesdonk/scholar-mcp/issues/406)
  and [ADR 0001](../decisions/0001-do-not-build-an-offline-semantic-scholar-store.md)]:**
  Recorded the maintainer's no-go decision on an offline Semantic Scholar
  store. Live API pacing and deferred jobs remain the chosen resilience path.
- **2026-09-12 — [derived]:** Adopted the v8.2 roadmapping convention. Kept
  only the stabilization and corpus-foundation cuts as packages; converted the
  broader standards, patents, books, and structural buckets into story epics
  with backlog children because each theme exceeded one credible release cut.
