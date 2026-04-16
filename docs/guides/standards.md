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

## Common Criteria

Common Criteria metadata is sync-only — there's no live API for the CC portal. Run:

```bash
scholar-mcp sync-standards --body CC
```

to populate the local cache. Two record categories load:

### Framework documents (~15 records)

The CC framework — `CC:2022`, `CC:2017` (CC 3.1 Revision 5), and the Common Evaluation Methodology (CEM) — ships as a hard-coded table in `_sync_cc.py`. Updates land manually when CCRA publishes a new release (every ~5 years).

CC framework documents that are also published as ISO/IEC 15408 / 18045 (parts 1-3) write **two records** under one `source="CC"` sync — one with `body="CC"` (`CC:2022 Part 1`), one with `body="ISO/IEC"` (`ISO/IEC 15408-1:2022`). Both records share the same free CC PDF as `full_text_url`. The `related` field on each cross-links to the other.

Why two records? CC and ISO/IEC 15408 are **parallel publications**, not a joint committee output. Real-world citations use either form (`CC:2022` or `ISO/IEC 15408`) but never a joined form. To keep returned metadata matching what the LLM looked up, we store one record per publishing body.

To prevent collision with the existing ISO loader, the ISO loader has a small denylist (`_RELATON_SKIP_SLUGS`) covering the 15408 / 18045 family — those records are owned exclusively by the CC loader, which has the freely-downloadable PDFs (vs. ISO's paywalled metadata).

### Protection Profiles (~500 records)

Loaded from `https://www.commoncriteriaportal.org/pps/pps.csv`. Identifier extraction uses per-scheme regex with a composite fallback:

| Scheme | Code | Identifier example |
|---|---|---|
| German BSI | DE | `BSI-CC-PP-0099-V2-2017` |
| Korean KECS | KR | `KECS-PP-0822-2017` |
| French ANSSI | FR | `ANSSI-CC-PP-2014/01` |
| US NIAP | US | `NIAP-PP-...` / `PP_..._v3.1` |
| Spanish CCN | ES | `CCN-PP-0058-2021` |
| Other | * | `CC PP {scheme}-{name}` (composite fallback) |

### Supported identifier forms

- `CC:2022`, `CC:2017`, `CC 3.1 R5`, `CC 3.1 Revision 5`
- `CC:2022 Part 1`, `Common Criteria 2022 Part 1`
- `CEM:2022`, `Common Evaluation Methodology 2022`
- `ISO/IEC 15408-1:2022` (resolves to the CC-owned dual record with free PDF)
- `BSI-CC-PP-0099-V2-2017`, `KECS-PP-0822-2017`, etc.

### Not yet supported (filed follow-ups)

- ~6700 certified product certifications from sec-certs JSON — see [#131](https://github.com/pvliesdonk/scholar-mcp/issues/131)
- CC Supporting Documents and Guidance Documents — see [#132](https://github.com/pvliesdonk/scholar-mcp/issues/132)
- CEM Supplements and Application Notes — see [#133](https://github.com/pvliesdonk/scholar-mcp/issues/133)
- Auto-discovery of new framework documents from the portal HTML — see [#134](https://github.com/pvliesdonk/scholar-mcp/issues/134)

## CEN/CENELEC (European Norms)

CEN/CENELEC harmonised standards metadata is sync-only. Run:

```bash
scholar-mcp sync-standards --body CEN
```

to populate the local cache. Unlike ISO/IEC/IEEE (which sync from upstream Relaton repositories), CEN standards load from a curated hard-coded table covering the most-cited harmonised standards from the major EU directives.

### Covered directives

| Directive | Shorthand | Example standards |
|---|---|---|
| Electromagnetic Compatibility 2014/30/EU | EMC | EN 55032, EN 61000-series |
| Radio Equipment 2014/53/EU | RED | EN 300 328, EN 301 489-series |
| Machinery 2006/42/EC | Machinery | EN ISO 12100, EN ISO 13849-1 |
| Medical Devices 2017/745 | MDR | EN ISO 13485, EN 62304 |
| Cyber Resilience Act | CRA | EN IEC 62443-series |
| General Product Safety | GPSR | EN 71-series (toys) |
| Low Voltage 2014/35/EU | LVD | EN 62368-1, EN 60335-1 |

### Supported identifier forms

- `EN 55032:2015` — plain European Norm
- `EN ISO 13849-1:2023` — ISO standard adopted as EN
- `EN IEC 62443-3-3:2020` — IEC standard adopted as EN
- `EN ISO/IEC 27001:2022` — ISO/IEC joint adopted as EN

All dispatch to `body="CEN"`. No cross-linking to the ISO/IEC records — the `EN ISO` / `EN IEC` prefix is self-documenting.

### Table maintenance

The `_HARMONISED_STANDARDS` table in `_sync_cen.py` needs periodic review when the EU Commission publishes new implementing decisions. See [#139](https://github.com/pvliesdonk/scholar-mcp/issues/139) for the quarterly cadence. If EUR-Lex infrastructure stabilises, [#137](https://github.com/pvliesdonk/scholar-mcp/issues/137) would automate this via Formex XML parsing.

### Not yet supported

- Full CEN/CENELEC catalogue beyond harmonised standards
- Live scrape fallback from `standards.cencenelec.eu` — see [#138](https://github.com/pvliesdonk/scholar-mcp/issues/138)
- EUR-Lex Formex XML automated sync — see [#137](https://github.com/pvliesdonk/scholar-mcp/issues/137)
