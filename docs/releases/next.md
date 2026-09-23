# Next release

<!-- notes-range-end: 751313ed7c15eac7c6b2aa4be739eb7fb74a47ef -->

<!-- RELEASE-SUMMARY NEXT START -->
Scholar MCP 3.0 corrects wrong or incomplete answers across its research tools
and repairs affected cached rows on upgrade. Semantic Scholar throttling becomes
background work, while converted documents arrive in pages that clients can
receive. Packaged systemd deployments and two Python library call paths need
migration steps described below.
<!-- RELEASE-SUMMARY NEXT END -->

## Correct answers, including cached records

The stabilization package set out to make Scholar MCP "answer correctly where
2.0 answered wrongly or not at all," including for rows cached before an upgrade
([epic #429](https://github.com/pvliesdonk/scholar-mcp/issues/429)). The fixes
include a one-shot cache repair system. On startup, each repair deletes
only rows made invalid by its corresponding fix and records that it ran. Operators
do not need to clear the cache or discard downloaded PDFs and converted Markdown
([#440](https://github.com/pvliesdonk/scholar-mcp/issues/440),
[#441](https://github.com/pvliesdonk/scholar-mcp/pull/441)).

Paper and book workflows now return the requested data instead of leaking quirks
from their upstream sources. `get_author` applies `limit` to live and cached
direct-ID lookups, even when Semantic Scholar ignores the requested limit
([#367](https://github.com/pvliesdonk/scholar-mcp/issues/367),
[#431](https://github.com/pvliesdonk/scholar-mcp/pull/431)). Citation generation
uses Semantic Scholar's conference publication type for BibTeX `@inproceedings`,
CSL-JSON `paper-conference`, and RIS `CONF` output
([#404](https://github.com/pvliesdonk/scholar-mcp/issues/404),
[#432](https://github.com/pvliesdonk/scholar-mcp/pull/432)). ISBN lookups can fill
an empty author list from an already-cached Open Library work record
([#403](https://github.com/pvliesdonk/scholar-mcp/issues/403),
[#449](https://github.com/pvliesdonk/scholar-mcp/pull/449)).

`fetch_paper_pdf` and `fetch_and_convert` now use the same 30-day paper cache as
`get_paper`. They resolve identifier aliases before reading the cache, write a
fresh record and alias on a miss, and make no Semantic Scholar request when the
metadata and converted files are already present
([#373](https://github.com/pvliesdonk/scholar-mcp/issues/373),
[#435](https://github.com/pvliesdonk/scholar-mcp/pull/435),
[#467](https://github.com/pvliesdonk/scholar-mcp/pull/467)).

Patent records now include the abstract and the country associated with each EPO
legal event. Patent numbers also normalize spacing, punctuation, and letter case
before cache lookup, so equivalent spellings reuse one metadata row and one PDF
([#399](https://github.com/pvliesdonk/scholar-mcp/issues/399),
[#405](https://github.com/pvliesdonk/scholar-mcp/issues/405),
[#402](https://github.com/pvliesdonk/scholar-mcp/issues/402),
[#444](https://github.com/pvliesdonk/scholar-mcp/issues/444)).

Standards lookups match NIST identifiers exactly rather than by substring. ETSI
failures are no longer reported as missing standards: direct lookup returns a
rate-limit or upstream-error payload, identifier resolution preserves the
canonical value with a warning, and multi-body search identifies partial results
without caching them
([#400](https://github.com/pvliesdonk/scholar-mcp/issues/400),
[#401](https://github.com/pvliesdonk/scholar-mcp/issues/401),
[#452](https://github.com/pvliesdonk/scholar-mcp/pull/452),
[#455](https://github.com/pvliesdonk/scholar-mcp/pull/455)). The
[tool reference](../tools/index.md) documents the final response shapes and
identifier rules.

## Semantic Scholar throttling becomes a job

All Semantic Scholar traffic from one server process now passes through one gate
with at least 1.1 seconds between requests. A 429 extends a shared cooldown, so a
refusal slows concurrent Graph and Recommendations calls instead of starting an
independent retry ladder in each call
([#408](https://github.com/pvliesdonk/scholar-mcp/issues/408),
[#462](https://github.com/pvliesdonk/scholar-mcp/pull/462)). Separate server
processes are not coordinated.

For MCP callers, throttled work continues through the existing jobs system. A
plain call promptly returns a handle with the reason `Semantic Scholar is
throttling requests; work continues.` Poll `get_job_result`; the running body
resumes from where it paused rather than restarting. With the default one-hour
result TTL, retries may continue for 50 minutes before the job settles as
`{"error":"rate_limited","retryable":true}`
([#409](https://github.com/pvliesdonk/scholar-mcp/issues/409),
[#463](https://github.com/pvliesdonk/scholar-mcp/pull/463)). Native MCP task
clients keep their native task handle.

No new setting is required. The existing defaults remain 25 seconds for
`SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S`, 3,600 seconds for
`SCHOLAR_MCP_JOBS_RESULT_TTL_S`, and 256 retained jobs per subject. See
[rate limiting and background jobs](../configuration.md#rate-limiting) for the
operator contract.

The server still depends on the live Semantic Scholar service. Research found
that papers plus abstracts alone require about 82 GB of compressed source data,
before authors, so the project chose shared pacing and deferred jobs rather than
an offline store
([#406](https://github.com/pvliesdonk/scholar-mcp/issues/406),
[#466](https://github.com/pvliesdonk/scholar-mcp/pull/466)).

## Converted documents arrive in pages

Five document tools used to return the entire conversion in one MCP response.
The reported examples reached 242,042 characters and exceeded the caller's
response limit, so the model could not receive the result
([#372](https://github.com/pvliesdonk/scholar-mcp/issues/372)).

`convert_pdf_to_markdown`, `fetch_and_convert`, `fetch_pdf_by_url`,
`fetch_patent_pdf`, and `get_standard` now return at most 20,000 Markdown or
full-text characters by default. Responses include character counts and
`next_offset` when another page remains. Call the same tool with
`text_offset=next_offset`; the complete conversion stays cached and is not run
again. Clients that can accept the remaining text in one response can set
`max_chars=null` for the previous behavior
([#465](https://github.com/pvliesdonk/scholar-mcp/pull/465)). The
[PDF conversion guide](../guides/pdf-conversion.md) has the paging recipe.

## Upgrading

This release has three compatibility changes against v2.0.0.

### Packaged systemd deployments

The `.deb` and `.rpm` unit no longer supplies `SCHOLAR_MCP_HOST=0.0.0.0`, and
its generated `/etc/scholar-mcp/env.example` is fully commented. Before or
after upgrading, set `SCHOLAR_MCP_CACHE_DIR=/var/lib/scholar-mcp` in
`/etc/scholar-mcp/env`. If the service must accept off-host connections, also
set `SCHOLAR_MCP_HOST=0.0.0.0`. An installation that relied on the old unit
default otherwise binds to `127.0.0.1` after the package restarts it
([#423](https://github.com/pvliesdonk/scholar-mcp/pull/423)). See the
[systemd deployment guide](../deployment/systemd.md) for the complete unit and
file layout.

Container and systemd deployments now default
`FASTMCP_ENABLE_RICH_LOGGING=false`, which produces one-line request records.
Set it to `true` to retain Rich terminal formatting
([template v8.2.0](https://github.com/pvliesdonk/fastmcp-server-template/releases/tag/v8.2.0),
[#420](https://github.com/pvliesdonk/scholar-mcp/pull/420)). Existing explicit
values still win.

### Python library callers

`scholar_mcp.server.build_event_store` now uses the shared core signature
`build_event_store(env_prefix, config)`. Replace calls with no arguments, or
with only a URL, by passing `"SCHOLAR_MCP"` and a `ServerConfig`
([#422](https://github.com/pvliesdonk/scholar-mcp/pull/422)).

`make_server(config=...)` no longer forwards `config.jobs` to tool registration.
Library callers whose explicit jobs configuration differs from the process
environment must set `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S`,
`SCHOLAR_MCP_JOBS_RESULT_TTL_S`, and `SCHOLAR_MCP_JOBS_MAX_PER_SUBJECT` in the
environment instead ([#344](https://github.com/pvliesdonk/scholar-mcp/issues/344),
[#422](https://github.com/pvliesdonk/scholar-mcp/pull/422)).

### MCP callers

Semantic Scholar 429 responses no longer return the immediate error shapes from
v2.0.0; callers receive a job or native task handle while the lookup waits. Code
that interpreted the old error must poll the returned handle instead
([#463](https://github.com/pvliesdonk/scholar-mcp/pull/463)).

Converted-document defaults are compatible rather than removed. Follow
`next_offset` to collect the document in pages, or pass `max_chars=null` when a
client can receive the complete remaining text
([#465](https://github.com/pvliesdonk/scholar-mcp/pull/465)).
