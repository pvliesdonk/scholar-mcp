# Citation Generation — Design Spec

## Overview

Add a `generate_citations` tool to scholar-mcp that produces formatted
citations from Semantic Scholar paper metadata. Supports BibTeX, CSL-JSON,
and RIS output formats.

## Tool Interface

**Tool:** `generate_citations`

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `paper_ids` | `list[str]` | (required) | S2 IDs, DOIs, arXiv IDs, etc. 1–100 papers. |
| `format` | `str` | `"bibtex"` | One of `bibtex`, `csl-json`, `ris`. |
| `enrich` | `bool` | `True` | Attempt OpenAlex enrichment for missing fields when DOI available. |

**Returns:** Formatted citation string. BibTeX/RIS: concatenated entries
separated by blank lines. CSL-JSON: `{"citations": [...], "errors": [...]}`.

**MCP annotations:** `readOnlyHint=True`, `destructiveHint=False`,
`openWorldHint=True`.

**Rate limiting:** Follows existing try-once pattern. On 429 from
`batch_resolve`, the whole operation queues as a background task.

## Module Structure

### `_tools_citation.py`

Tool registration and dispatch. Thin layer following the existing category
module pattern (like `_tools_search.py`). Registers `generate_citations` on
the MCP server, resolves papers, orchestrates enrichment, delegates to
formatters.

### `_citation_formatter.py`

Pure formatting logic with no MCP/API dependencies:

- `format_bibtex(papers: list[dict], errors: list[dict]) -> str`
- `format_csl_json(papers: list[dict], errors: list[dict]) -> str`
- `format_ris(papers: list[dict], errors: list[dict]) -> str`
- `generate_bibtex_key(paper: dict, seen_keys: set[str]) -> str`
- `infer_entry_type(paper: dict) -> str`
- `escape_bibtex(text: str) -> str`

All functions are pure — no side effects, easy to unit test with fixture
dicts.

### `_citation_names.py`

Author name parsing utility:

- `parse_author_name(name: str) -> AuthorName`
- `AuthorName = NamedTuple("AuthorName", first=str, last=str, prefix=str, suffix=str)`

Handles: prefixes ("van", "de", "von", "de la"), suffixes ("Jr.", "III"),
hyphenated names, compound surnames. Fallback: if parsing is ambiguous, the
full string becomes `last` with empty `first`.

## Data Flow

1. Tool receives `paper_ids` list.
2. Batch-resolve via `bundle.s2.batch_resolve()` (uses cache).
3. If `enrich=True` and DOI present on a paper, call
   `bundle.openalex.get_by_doi()` to fill venue/publisher gaps.
4. Pass resolved paper dicts + error list to the appropriate formatter.
5. Return formatted string.

## BibTeX Entry Type Inference

S2 doesn't provide explicit document types. Inferred from metadata:

| Condition | BibTeX type |
|-----------|-------------|
| `venue` contains "conference", "proceedings", "workshop", "symposium" | `@inproceedings` |
| `venue` matches journal patterns or DOI from journal publisher | `@article` |
| `externalIds` has `ArXiv` and no strong venue signal | `@misc` |
| Fallback | `@article` |

CSL-JSON equivalents: `paper-conference`, `article-journal`, `article`.
RIS equivalents: `CONF`, `JOUR`, `GEN`.

## Field Mapping

### BibTeX

| BibTeX field | Source |
|--------------|--------|
| `author` | S2 `authors[].name` parsed via `_citation_names.py` -> `{Last}, First and ...` |
| `title` | S2 `title` wrapped in `{}` to preserve casing |
| `year` | S2 `year` |
| `booktitle` | S2 `venue` (for `@inproceedings`) |
| `journal` | S2 `venue` (for `@article`) |
| `doi` | S2 `externalIds.DOI` |
| `url` | S2 `openAccessPdf.url` or `https://doi.org/{DOI}` |
| `abstract` | S2 `abstract` |
| `eprint` | S2 `externalIds.ArXiv` |
| `archiveprefix` | `arXiv` (when eprint present) |

### CSL-JSON

| CSL-JSON field | Source |
|----------------|--------|
| `type` | Inferred (see above) |
| `id` | Same as BibTeX key |
| `title` | S2 `title` |
| `author` | `[{"family": "Last", "given": "First", "non-dropping-particle": "van"}]` |
| `issued` | `{"date-parts": [[year]]}` |
| `container-title` | S2 `venue` |
| `DOI` | S2 `externalIds.DOI` |
| `URL` | S2 `openAccessPdf.url` or `https://doi.org/{DOI}` |
| `abstract` | S2 `abstract` |

### RIS

| RIS tag | Source |
|---------|--------|
| `TY` | `CONF` / `JOUR` / `GEN` |
| `AU` | One tag per author, `Last, First` format |
| `TI` | S2 `title` |
| `PY` | S2 `year` + `///` |
| `JO` / `BT` | S2 `venue` (journal vs. conference) |
| `DO` | DOI |
| `UR` | URL |
| `AB` | Abstract |
| `ER` | End of record |

## BibTeX Key Generation

Strategy: `authorYear` — first author's last name (lowercased, ASCII-folded)
+ publication year.

- Deduplication: tracked via `seen_keys` set within a single tool call.
  `smith2024` -> `smith2024a` -> `smith2024b`.
- No cross-call state.
- Missing author: key starts with `anon`.
- Missing year: year omitted from key.

## Special Character Handling

**BibTeX:** Escape `& % # _ $ { } ~ ^`. Unicode-to-LaTeX mapping for common
accented characters (a -> `{\"a}`, e -> `{\'e}`, etc.).

**CSL-JSON:** Standard JSON encoding (no special handling needed).

**RIS:** Plain text (no special handling needed).

## Error Handling

- **Per-paper errors don't fail the batch.** Unresolvable papers are reported
  inline: BibTeX as `%` comments, CSL-JSON in the `errors` array, RIS as
  comment lines.
- **Empty result:** If zero papers resolve, return a clear error message.
- **Name parsing fallback:** Ambiguous single-word names use full string as
  `last` with empty `first`.
- **OpenAlex enrichment failure:** Silent. Enrichment is best-effort.
- **Rate limiting:** `batch_resolve` 429 queues the entire operation as a
  background task via `bundle.tasks.submit()`.

## Future Considerations

- **File export:** Output is structured for future file-write capability
  (planned cache-based file export feature). No file I/O in this iteration.
- **Additional formats:** The formatter architecture (one function per format)
  makes adding new formats straightforward.
