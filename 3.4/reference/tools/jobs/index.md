# Jobs

## `get_job_result`

**Get Job Result.** Read-only. Tags: `jobs`.

Get the status of a background job started by a long-running tool on this server; returns status (working, completed or failed) with the result or error once it finishes. Job records expire, so fetch a finished job's result promptly. Scholar MCP promotes slow work to a background job. PDF download and docling conversion usually take 1-5 minutes, a busy EPO traffic light is waited out, citation formatting enriches one paper after another, and graph traversal makes one rate-limited request per node. Semantic Scholar throttling defers the same work immediately and adds a reason to the handle. Those calls commonly answer with a `job_id` rather than a result; a cache hit answers inline, with no job.

**Parameters**

| Name     | Type     | Default  | Description                                                                    |
| -------- | -------- | -------- | ------------------------------------------------------------------------------ |
| `job_id` | `string` | required | The `job_id` a long-running tool returned when it continued in the background. |

**Returns**

`object`
