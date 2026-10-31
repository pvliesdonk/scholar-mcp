# Citations

## `generate_citations`

**Generate Citations.** Read-only. Reaches outside the server.

Generate formatted citations for one or more papers.

Papers are resolved through Semantic Scholar and can be enriched with OpenAlex metadata. The output is BibTeX, CSL-JSON or RIS.

Enrichment fans out per paper, so a large batch can take a while; such a call answers with a job handle to poll using `get_job_result` instead of the citations themselves.

**Parameters**

| Name              | Type                        | Default    | Description                                                                          |
| ----------------- | --------------------------- | ---------- | ------------------------------------------------------------------------------------ |
| `paper_ids`       | `array of string`           | required   | List of paper identifiers (S2 IDs, DOIs, arXiv IDs, etc.). Maximum 100.              |
| `citation_format` | `bibtex \| csl-json \| ris` | `"bibtex"` | Output format: `bibtex`, `csl-json` or `ris`.                                        |
| `enrich`          | `boolean`                   | `true`     | If True, attempt OpenAlex enrichment for missing venue data when a DOI is available. |

**Returns**

`{"format": ..., "output": ...}` where `output` is the formatted text, with unresolved identifiers included as comments in the comment style of the chosen format. An error mapping on failure.

The key is `output` rather than `citations` because the CSL-JSON formatter emits its own `citations` key, which would collide.

**BibTeX output** includes entry type inference (`@article`, `@inproceedings`, `@misc`, `@book`), proper author formatting (`{Last}, First`), title casing preservation, DOI, arXiv eprint fields, and special character escaping. Papers with `book_metadata` (ISBN or publisher) are emitted as `@book` entries with `publisher`, `edition`, and `isbn` fields.

A paper is emitted as `@inproceedings` when Semantic Scholar reports it as a conference paper, and otherwise when its venue name contains conference, proceedings, workshop, or symposium. The first rule matters because venue names such as "Neural Information Processing Systems" and "Computer Vision and Pattern Recognition" contain none of those words. The same inference drives the CSL-JSON `paper-conference` type and the RIS `CONF` tag.

**CSL-JSON output** puts a JSON document in `output`, so reaching the entries means parsing that string: it is `{"citations": [...], "errors": [...]}`, whose citations array contains standard CSL-JSON objects compatible with Zotero, Mendeley, Pandoc, and other CSL processors. Book entries use `type: "book"` with `publisher` and `ISBN` fields.

**RIS output** uses standard RIS tags (`TY`, `AU`, `TI`, `PY`, `JO`/`BT`, `DO`, `UR`, `AB`, `ER`). Book entries use `TY - BOOK` with `PB` (publisher) and `SN` (ISBN) tags.

In CSL-JSON output, papers that fail to resolve go in the errors array. When all papers fail, a structured error is returned: `{"error": "no_papers_resolved", "failed": [...]}`.
