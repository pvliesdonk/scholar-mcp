# Background jobs

Some calls take longer than a client should wait on one response: PDF download and conversion, a citation graph walk, a patent lookup while EPO is busy. Those calls answer with a job handle instead of blocking. A result already in the cache comes back directly, and that includes a Markdown conversion done earlier.

## When a call becomes a job

A tool that runs past `SCHOLAR_MCP_JOBS_SOFT_DEADLINE_S` (25 seconds by default) returns a handle:

```
{"status": "working", "job_id": "hwex4wg6taLmasPZWPM7gQ", "poll_with": "get_job_result",
 "retry_after_s": 5.0, "message": "..."}
```

Poll it with [`get_job_result`](https://pvliesdonk.github.io/scholar-mcp/3.2/reference/tools/jobs/index.md). Job records expire `SCHOLAR_MCP_JOBS_RESULT_TTL_S` after they're created (1 hour by default); settling a job doesn't extend that. Clients that use native MCP tasks get the same result through their task handle instead.

## Semantic Scholar throttling

When Semantic Scholar throttles a tool that calls it, a plain MCP call returns a handle straight away, with a `retry_after_s` hint and a `reason` telling the caller to keep polling. The work may run for up to five sixths of `SCHOLAR_MCP_JOBS_RESULT_TTL_S` (about 50 minutes by default), and the reason gives that bound in minutes. It also says that a job still running means no answer yet, not an empty one. The original work keeps going inside the job, and a graph walk resumes at the node it had reached. If Semantic Scholar keeps refusing, the job completes before its record expires with `{"error": "rate_limited", "retryable": true}`. Other HTTP errors from Semantic Scholar come back as the tool's usual error response.

Every client of the server shares one Semantic Scholar rate budget, because the server paces its requests and backs off as a single Semantic Scholar client, not per caller. Several agents searching in parallel through one server each wait longer; they don't finish sooner. The server's instructions say this at session start, so an agent can plan for it before the first throttle rather than learn it from a deferral.

## EPO traffic light

When EPO reports its traffic light amber or red, the patent tools wait for it to clear, so they often return a `job_id`. If it hasn't cleared by the time the retries run out, they answer with `{"error": "rate_limited", "retryable": true}` and a hint rather than failing with no explanation.
