# Command line

Scholarly papers, patents, books, standards and PDF conversion

## `scholar-mcp serve`

Run the MCP server.

| Option        | Env var | Default | Description                                                        |
| ------------- | ------- | ------- | ------------------------------------------------------------------ |
| `--transport` |         | stdio   | MCP transport (stdio / http / sse).                                |
| `--host`      |         |         | Bind host (http only; default: $`SCHOLAR_MCP_HOST` or 127.0.0.1).  |
| `--port`      |         |         | Bind port (http only; default: $`SCHOLAR_MCP_PORT` or 8000).       |
| `--http-path` |         |         | Mount path (http only, default: $`SCHOLAR_MCP_HTTP_PATH` or /mcp). |

## `scholar-mcp sync-standards`

Sync Tier 2 standards catalogue data into the local cache.

Safe to schedule under cron / launchd / systemd timers.

Exit codes: 0: no changes, or synced with updates 1: hard failure (no body synced) 3: partial failure (some bodies succeeded, some did not)

| Option        | Env var | Default | Description                                       |
| ------------- | ------- | ------- | ------------------------------------------------- |
| `--body`      |         | all     | Body to sync. 'all' runs every registered loader. |
| `--force`     |         | False   | Bypass upstream-freshness checks and re-sync.     |
| `--cache-dir` |         |         | Override cache directory.                         |

## `scholar-mcp cache`

Manage the Scholar MCP local cache.
