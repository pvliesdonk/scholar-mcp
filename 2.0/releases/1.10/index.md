# 1.10

Scholar MCP 1.10 replaces its two separate background-task systems with one: every tool whose work can run long now promotes to a background job on the same schedule and is polled with a single new tool, `get_job_result`. The patent tools gain a real retry against EPO's throttling instead of one that never actually asked EPO again, two gaps in the advertised tool metadata are closed, and `fetch_and_convert` stops re-running its most expensive step when a cached result already exists.

## One background-job queue instead of two

The server used to carry two background-task systems that had drifted apart: a bespoke, in-process queue that did the actual work behind `get_task_result` and `list_tasks`, and a separate `fastmcp-pvl-core` task backend that `make_server()` configured but that no tool in the domain code used. As [the tracking issue](https://github.com/pvliesdonk/scholar-mcp/issues/264) put it, an operator who pointed `SCHOLAR_MCP_KV_STORE_URL` at Redis would silently gain a Redis-backed core queue while `list_tasks` stayed in-process and lost every job on restart, and any future improvement to task durability or cancellation would land in the system the domain tools never touched.

1.10 consolidates onto one queue. Every tool whose work can run long, covering PDF download and conversion, patent search, paper, book and citation lookups, citation-graph traversal, cross-source identifier resolution, and standards lookups, is promoted to a background job once it runs past `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S` (25 seconds by default) rather than branching on which upstream error it hit. A promoted call returns a handle:

```
{"status": "working", "job_id": "hwex4wg6taLmasPZWPM7gQ", "poll_with": "get_job_result",
 "retry_after_s": 5.0, "message": "..."}
```

and the new `get_job_result` tool polls it through to `completed` or `failed`. `get_task_result` and `list_tasks` are gone. If you restrict the exposed tool surface with `SCHOLAR_MCP_TOOLS_ALLOW` (or an equivalent allowlist elsewhere) and named either of those, add `get_job_result` in their place: an allowlist matches by name, so a name that no longer resolves to anything is silently ignored rather than rejected, and a job handle with no tool able to poll it becomes unresolvable.

Two new variables round out the tuning surface, both documented in the [configuration guide](https://pvliesdonk.github.io/scholar-mcp/2.0/configuration/#long-running-tools-and-get_job_result): `SCHOLAR_MCP_JOBS_RESULT_TTL_S` (how long a job record is kept, one hour by default) and `SCHOLAR_MCP_JOBS_MAX_PER_SUBJECT` (the live-job cap per caller, 256 by default). Job records live in `SCHOLAR_MCP_KV_STORE_URL`, the same backend as everything else stateful; that is a different variable from `SCHOLAR_MCP_TASKS_URL`, which configured the old queue. A restart does not resume promoted work: a poll afterward reports `working` until the record's TTL runs out, rather than inventing a result.

Several tools now return a JSON object where they used to return a JSON string (`generate_citations`, `batch_resolve`, and others); the [tools reference](https://pvliesdonk.github.io/scholar-mcp/2.0/tools/index.md) documents the new shape for each. That is a change to the MCP tool surface, not a breaking one: a fresh client connection re-discovers it automatically.

## More accurate error reporting for patents and rate-limited papers

Wrapping the patent tools in the same jobs mechanism surfaced something the old queue had never actually fixed: EPO Open Patent Services fails within milliseconds when its traffic light is not green, so a queued retry ran immediately against the same 60-second-cached light and failed again without ever asking EPO a second time. 1.10 gives the patent tools a real backoff whose waits are deliberately longer than that 60-second cache lifetime, so a retry asks EPO again instead of re-reading a stale answer. An exhausted daily quota is now its own error, reported at once with `"retryable": false`, since it will not clear before tomorrow and waiting would only cost the caller time for a known answer.

Two related reporting gaps are fixed alongside it. `batch_resolve`, which resolves identifiers across patents and papers in one call, used to fold an exhausted EPO quota into a generic failure for that entry; it now reports the same `retryable` shape as the dedicated patent tools, for that entry only, without failing the rest of the batch. And `enrich_paper` used to report a rate-limited Semantic Scholar lookup as `not_found`, which told a calling model to stop asking about a paper that exists; it now reports `{"error": "rate_limited", "retryable": true}`.

## Tool surface fixes

Two mismatches between what the tool registry advertised and what the code actually did are fixed:

- `fetch_patent_pdf` was missing the `patent` tag its three sibling patent tools carry, so it stayed listed, and callable, when no EPO credentials were configured, where it could only ever answer with an error. It now carries both tags and is hidden along with the rest of the patent surface when EPO is unconfigured.
- `get_book`'s `include_editions` parameter was accepted and documented but read by nothing. It is dropped rather than implemented, since nothing referenced it; a client that still passes it now gets a clear validation error instead of a silently ignored argument.

A new test enumerates the full tool registry, not just the shorter listing a read-only or credential-free server exposes, and asserts every tool carries a title and a `readOnlyHint`. All 29 currently registered tools already carried a title by the time this landed; the test is what keeps that true for tools added later.

## `fetch_and_convert` reuses its cached Markdown

`fetch_and_convert` downloads a paper's PDF and converts it to Markdown in one call. Its sibling conversion tools, `convert_pdf_to_markdown` and `fetch_pdf_by_url`, have always reused an existing Markdown file instead of re-running the conversion on a repeat call; `fetch_and_convert` never did, so calling it twice for the same paper paid for a second docling conversion, the most expensive operation this server performs, and overwrote an identical file. It now checks for a cached Markdown file the same way its siblings do. Nothing in the tool forces a fresh conversion yet: deleting the cached `.md` file remains how to get one, for all four conversion tools alike.

## MCP registry listing catches up

`v1.9.1` published everywhere except the [MCP Registry](https://registry.modelcontextprotocol.io/): the publish step rejected it because the server's advertised description had grown past the registry's 100-character cap, to 128 characters. 1.10 shortens the description to 93 characters (`FastMCP server for scholarly papers, patents, books and standards with docling PDF conversion`), keeping the broader scope the longer wording was meant to convey. Since the registry entry is a rolling pointer to the newest release rather than a per-version record, this release is what closes the gap; nothing needed publishing by hand.

## Upgrading

No environment variable, configuration file, or public Python import was removed or changed in this release; every new variable above is additive. The one action item is the tool-allowlist note under [One background-job queue instead of two](#one-background-job-queue-instead-of-two): add `get_job_result` to any allowlist that used to name `get_task_result` or `list_tasks`.
