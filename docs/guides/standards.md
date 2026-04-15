# Tier 2 standards sync -- ISO, IEC & IEEE

Scholar MCP caches ISO, IEC, and IEEE standards metadata locally. The source of truth
is the community-maintained Relaton YAML dumps at
[`relaton/relaton-data-iso`](https://github.com/relaton/relaton-data-iso),
[`relaton/relaton-data-iec`](https://github.com/relaton/relaton-data-iec), and
[`relaton/relaton-data-ieee`](https://github.com/relaton/relaton-data-ieee).

## Running a sync

```
scholar-mcp sync-standards            # all registered bodies
scholar-mcp sync-standards --body ISO # only ISO
scholar-mcp sync-standards --body IEEE # only IEEE
scholar-mcp sync-standards --force    # re-sync even if upstream SHA is unchanged
```

Exit codes: `0` on success (or no-op), `1` on hard failure, `3` on partial failure
(some bodies succeeded, some did not).

## Cron / systemd scheduling

Daily resync is plenty -- Relaton dumps move slowly and the SHA check skips the
tarball fetch when nothing has changed.

```cron
0 3 * * *  /usr/local/bin/scholar-mcp sync-standards >> /var/log/scholar-mcp-sync.log 2>&1
```

Or with systemd:

```
# /etc/systemd/system/scholar-mcp-sync.service
[Unit]
Description=Sync scholar-mcp Tier 2 standards
[Service]
Type=oneshot
ExecStart=/usr/local/bin/scholar-mcp sync-standards
```

```
# /etc/systemd/system/scholar-mcp-sync.timer
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
```

## GitHub rate limiting

The sync makes 2 GitHub API calls per body (`/commits/{branch}` and `/tarball/{sha}`).
Unauthenticated clients get 60 requests per hour per IP -- more than enough for daily
cron. For repeated `--force` testing, set `SCHOLAR_GITHUB_TOKEN` to a personal access
token (no scopes required for public-repo reads) to lift the limit to 5,000 req/hr:

```
export SCHOLAR_GITHUB_TOKEN=ghp_...
```

## Live-fetch fallback

A `get_standard("ISO 9001:2015")` call on an unsynced cache triggers a single-file
fetch from `raw.githubusercontent.com`. Results are cached with a 90-day TTL (standards
rarely change) and can be replaced by running `sync-standards` to populate the full
synced copy.

## Joint ISO/IEC standards

Standards like `ISO/IEC 27001:2022` and `ISO/IEC 15408:2022` appear in both dumps. The
loader detects joint documents from the YAML structure (both `type=ISO` and `type=IEC`
`docidentifier` entries) and stores them once with `body="ISO/IEC"`. The `source` column
on the row reflects the body that last wrote it.

## Troubleshooting

### "withdrawal pass aborted"

When a sync sees more than 50% of prior identifiers missing from a new tarball, it skips
the withdrawal pass to avoid flipping the whole cache to `status="withdrawn"`. Run
`--force` after confirming upstream state is sane.

### Rate-limit errors (HTTP 403)

Indicates the unauthenticated limit has been exhausted. Set `SCHOLAR_GITHUB_TOKEN` or
wait an hour.

### Inspecting last sync

Open the SQLite cache database (default `$SCHOLAR_MCP_CACHE_DIR/scholar.db`) and query
the `standards_sync_runs` table:

```sql
SELECT body, upstream_ref, added, updated, unchanged, withdrawn, errors,
       datetime(started_at, 'unixepoch') AS started,
       datetime(finished_at, 'unixepoch') AS finished
FROM standards_sync_runs;
```

To see how many standards are cached per body:

```sql
SELECT source, COUNT(*) AS count, datetime(MAX(synced_at), 'unixepoch') AS last_synced
FROM standards
WHERE source IS NOT NULL
GROUP BY source;
```

## IEEE

IEEE metadata comes from the [`relaton/relaton-data-ieee`](https://github.com/relaton/relaton-data-ieee) repository.

### Supported identifier forms

- `IEEE 1003.1-2024`, `IEEE 802.11-2020` — plain IEEE standards
- `IEEE Std 1588-2019` — the `Std` token is accepted (upstream convention)
- `IEC/IEEE 61588-2021` — joint standards hosted in the IEEE repo
- `ISO/IEC/IEEE 42010-2011` — triple-joint standards (ISO + IEC + IEEE committees)

For joint standards the stored `body` field reflects the true joint nature (e.g. `"ISO/IEC/IEEE"`), while dispatch still routes through the `"IEEE"` fetcher key. Per-body filename conventions differ between repositories: ISO/IEC use lowercase-hyphen (`iso-9001-2015.yaml`), IEEE uses uppercase-underscore (`IEEE_1003.1-2024.yaml`, `ISO_IEC_IEEE_42010-2011.yaml`).

### Not yet supported (filed follow-ups)

- `ANSI/IEEE Std 754-1985` and other historical ANSI-co-branded identifiers — see [#127](https://github.com/pvliesdonk/scholar-mcp/issues/127)
- `AIEE 11-1937` and other pre-IEEE AIEE identifiers — see [#127](https://github.com/pvliesdonk/scholar-mcp/issues/127)
- `IEEE P802.11-REVme` unpublished drafts — see [#128](https://github.com/pvliesdonk/scholar-mcp/issues/128)
- Explicit `body="IEC/IEEE"` / `body="ISO/IEC/IEEE"` search dispatch — see [#129](https://github.com/pvliesdonk/scholar-mcp/issues/129). Today, use identifier lookup or `body="IEEE"` which returns joints too.
- IEEE Xplore authenticated full-text — see [#92](https://github.com/pvliesdonk/scholar-mcp/issues/92)
