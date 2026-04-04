# Scholar MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `pvliesdonk/scholar-mcp`, a FastMCP server providing structured academic literature access via Semantic Scholar, with OpenAlex enrichment and optional docling-serve PDF conversion.

**Architecture:** FastMCP server instantiated from `pvliesdonk/fastmcp-server-template`. Three `httpx.AsyncClient`s (S2, OpenAlex, docling-serve) plus an `aiosqlite` SQLite cache compose a `ServiceBundle` yielded by the lifespan. Tools are split into five category modules; `_server_tools.py` dispatches to all of them. GitHub issues (labelled by area) are the work queue — close each issue as its tools pass tests.

**Tech Stack:** Python 3.11+, FastMCP 3.x, httpx, aiosqlite, respx, pytest

**Spec:** `/mnt/code/fastmcp-server-template/docs/superpowers/specs/2026-04-04-scholar-mcp-design.md`

---

## File Structure

All paths are relative to the `scholar-mcp` repo root after `rename.sh` runs.

| Action | Path | Responsibility |
|--------|------|---------------|
| Rename | `src/scholar_mcp/__init__.py` | Package init |
| Rename | `src/scholar_mcp/mcp_server.py` | FastMCP factory — **do not modify** |
| **Modify** | `src/scholar_mcp/config.py` | Add S2 API key, docling, VLM, cache dir fields |
| **Modify** | `src/scholar_mcp/cli.py` | Add `cache` subcommand group |
| **Replace** | `src/scholar_mcp/_server_deps.py` | `ServiceBundle` lifespan |
| **Replace** | `src/scholar_mcp/_server_tools.py` | Dispatch to category modules |
| Rename | `src/scholar_mcp/_server_resources.py` | Minimal health resource |
| Rename | `src/scholar_mcp/_server_prompts.py` | Empty for now |
| **Create** | `src/scholar_mcp/_cache.py` | `ScholarCache` (aiosqlite) |
| **Create** | `src/scholar_mcp/_rate_limiter.py` | `RateLimiter` + retry helper |
| **Create** | `src/scholar_mcp/_s2_client.py` | `S2Client` |
| **Create** | `src/scholar_mcp/_openalex_client.py` | `OpenAlexClient` |
| **Create** | `src/scholar_mcp/_docling_client.py` | `DoclingClient` (standard + VLM paths) |
| **Create** | `src/scholar_mcp/_tools_search.py` | `search_papers`, `get_paper`, `get_author` |
| **Create** | `src/scholar_mcp/_tools_graph.py` | `get_citations`, `get_references`, `get_citation_graph`, `find_bridge_papers` |
| **Create** | `src/scholar_mcp/_tools_recommendations.py` | `recommend_papers` |
| **Create** | `src/scholar_mcp/_tools_pdf.py` | `fetch_paper_pdf`, `convert_pdf_to_markdown`, `fetch_and_convert` |
| **Create** | `src/scholar_mcp/_tools_utility.py` | `batch_resolve`, `enrich_paper` |
| **Modify** | `tests/conftest.py` | Add `ServiceBundle`, cache, client fixtures |
| **Create** | `tests/test_cache.py` | `ScholarCache` unit tests |
| **Create** | `tests/test_rate_limiter.py` | `RateLimiter` unit tests |
| **Create** | `tests/test_s2_client.py` | `S2Client` tests with respx |
| **Create** | `tests/test_openalex_client.py` | `OpenAlexClient` tests with respx |
| **Create** | `tests/test_docling_client.py` | `DoclingClient` tests with respx |
| **Create** | `tests/test_tools_search.py` | Search tool integration tests |
| **Create** | `tests/test_tools_graph.py` | Citation graph integration tests |
| **Create** | `tests/test_tools_recommendations.py` | Recommendations integration tests |
| **Create** | `tests/test_tools_pdf.py` | PDF tool integration tests |
| **Create** | `tests/test_tools_utility.py` | Utility tool integration tests |
| **Modify** | `pyproject.toml` | Add `httpx`, `aiosqlite` to core deps; `respx` to dev |

---

### Task 1: Scaffold the repo

**Files:** new repo + all renamed template files

- [ ] **Step 1: Create the repo from the template**

```bash
cd /mnt/code
gh repo create pvliesdonk/scholar-mcp \
  --template pvliesdonk/fastmcp-server-template \
  --public --clone
cd /mnt/code/scholar-mcp
```

- [ ] **Step 2: Run the rename script**

```bash
./scripts/rename.sh scholar-mcp scholar_mcp SCHOLAR_MCP "Scholar MCP Server"
```

- [ ] **Step 3: Remove template scaffolding**

```bash
rm -rf scripts/ TEMPLATE.md SYNC.md
```

- [ ] **Step 4: Copy plan and spec into the new repo**

```bash
mkdir -p docs/superpowers/specs docs/superpowers/plans
cp /mnt/code/fastmcp-server-template/docs/superpowers/specs/2026-04-04-scholar-mcp-design.md \
   docs/superpowers/specs/
cp /mnt/code/fastmcp-server-template/docs/superpowers/plans/2026-04-04-scholar-mcp.md \
   docs/superpowers/plans/
```

- [ ] **Step 5: Install dependencies and verify the template tests pass**

```bash
uv sync --all-extras
uv run pytest
```

Expected: all template tests pass.

- [ ] **Step 6: Commit the scaffold**

```bash
git add -A
git commit -m "chore: scaffold from fastmcp-server-template"
git push -u origin main
```

---

### Task 2: Set up GitHub infrastructure

**Files:** no code changes — GitHub labels, milestones, issues via `gh`

- [ ] **Step 1: Create labels**

```bash
gh label create "area: scaffold"         --color "0075ca" --description "Repo scaffolding"
gh label create "area: core-search"      --color "e4e669" --description "search_papers, get_paper, get_author"
gh label create "area: cache"            --color "d93f0b" --description "SQLite cache + CLI"
gh label create "area: citation-graph"   --color "0e8a16" --description "Citation graph tools"
gh label create "area: recommendations"  --color "5319e7" --description "recommend_papers"
gh label create "area: pdf"              --color "b60205" --description "PDF download + conversion"
gh label create "area: utility"          --color "1d76db" --description "batch_resolve, enrich_paper"
gh label create "area: ops"              --color "cccccc" --description "Docker, deployment docs"
```

- [ ] **Step 2: Create milestones**

```bash
gh api repos/pvliesdonk/scholar-mcp/milestones -f title="v0.1.0" -f description="scaffold + core-search + cache"
gh api repos/pvliesdonk/scholar-mcp/milestones -f title="v0.2.0" -f description="citation graph"
gh api repos/pvliesdonk/scholar-mcp/milestones -f title="v0.3.0" -f description="recommendations + utility"
gh api repos/pvliesdonk/scholar-mcp/milestones -f title="v0.4.0" -f description="PDF tools + ops docs"
```

- [ ] **Step 3: Create issues — v0.1.0**

```bash
gh issue create --title "Implement SQLite cache (ScholarCache)" \
  --label "area: cache" --milestone "v0.1.0" \
  --body "Implement \`_cache.py\`: schema migrations, TTL-based get/set for papers, citations, references, authors, openalex, id_aliases. See spec §Caching."

gh issue create --title "Implement S2 API client with rate limiting" \
  --label "area: core-search" --milestone "v0.1.0" \
  --body "Implement \`_rate_limiter.py\` and \`_s2_client.py\`. Rate limiter: 1.1s delay (no key) / 0.1s (with key), 429 backoff. S2Client wraps all S2 API calls. See spec §Rate Limiting."

gh issue create --title "Implement search_papers tool" \
  --label "area: core-search" --milestone "v0.1.0" \
  --body "Implement \`search_papers\` in \`_tools_search.py\`. Inputs: query, year range, fields_of_study, venue, min_citations, sort, fields preset, limit, offset. See spec §search_papers."

gh issue create --title "Implement get_paper tool" \
  --label "area: core-search" --milestone "v0.1.0" \
  --body "Implement \`get_paper\` in \`_tools_search.py\`. Accepts DOI, S2 ID, arXiv ID, ACM ID, PubMed ID. Returns full metadata. Cache result. See spec §get_paper."

gh issue create --title "Implement get_author tool" \
  --label "area: core-search" --milestone "v0.1.0" \
  --body "Implement \`get_author\` in \`_tools_search.py\`. Accepts S2 author ID or name. Name search returns top 5 candidates. See spec §get_author."

gh issue create --title "Add CLI cache management commands" \
  --label "area: cache" --milestone "v0.1.0" \
  --body "Add \`scholar-mcp cache stats\`, \`scholar-mcp cache clear\`, \`scholar-mcp cache clear --older-than N\` to cli.py. See spec §CLI cache management."
```

- [ ] **Step 4: Create issues — v0.2.0**

```bash
gh issue create --title "Implement get_citations and get_references tools" \
  --label "area: citation-graph" --milestone "v0.2.0" \
  --body "Implement \`get_citations\` and \`get_references\` in \`_tools_graph.py\`. Pagination + filtering. Cache results. See spec §get_citations, §get_references."

gh issue create --title "Implement get_citation_graph tool (multi-hop BFS)" \
  --label "area: citation-graph" --milestone "v0.2.0" \
  --body "Implement \`get_citation_graph\` in \`_tools_graph.py\`. BFS up to depth 3, max_nodes cap, returns node/edge structure. See spec §get_citation_graph."

gh issue create --title "Implement find_bridge_papers tool (shortest path BFS)" \
  --label "area: citation-graph" --milestone "v0.2.0" \
  --body "Implement \`find_bridge_papers\` in \`_tools_graph.py\`. BFS shortest path between two papers. See spec §find_bridge_papers."
```

- [ ] **Step 5: Create issues — v0.3.0**

```bash
gh issue create --title "Implement recommend_papers tool" \
  --label "area: recommendations" --milestone "v0.3.0" \
  --body "Implement \`recommend_papers\` in \`_tools_recommendations.py\`. 1–5 positive IDs, optional negative IDs. Delegates to S2 recommendations endpoint. See spec §recommend_papers."

gh issue create --title "Implement OpenAlex client" \
  --label "area: utility" --milestone "v0.3.0" \
  --body "Implement \`_openalex_client.py\`: resolve by DOI, fetch affiliations/funders/oa_status/concepts. See spec §OpenAlex."

gh issue create --title "Implement batch_resolve tool with OpenAlex fallback" \
  --label "area: utility" --milestone "v0.3.0" \
  --body "Implement \`batch_resolve\` in \`_tools_utility.py\`. Uses S2 batch endpoint; falls back to OpenAlex by DOI; fuzzy title matching with confidence score. See spec §batch_resolve."

gh issue create --title "Implement enrich_paper tool" \
  --label "area: utility" --milestone "v0.3.0" \
  --body "Implement \`enrich_paper\` in \`_tools_utility.py\`. Pulls affiliations, funders, oa_status, concepts from OpenAlex. Cached 30 days. See spec §enrich_paper."
```

- [ ] **Step 6: Create issues — v0.4.0**

```bash
gh issue create --title "Implement docling-serve client (standard + VLM paths)" \
  --label "area: pdf" --milestone "v0.4.0" \
  --body "Implement \`_docling_client.py\`. Standard path: POST /v1/convert/file/async (multipart). VLM path: POST /v1/convert/source/async (base64 JSON with GPT-4o formula/figure enrichment). Both paths: submit → poll /v1/status/poll/{task_id} → fetch /v1/result/{task_id}. Reference implementation: /mnt/docker-volumes/compose.git/40-documents/paperless-docling-md/convert.py. See spec §convert_pdf_to_markdown."

gh issue create --title "Implement fetch_paper_pdf tool" \
  --label "area: pdf" --milestone "v0.4.0" \
  --body "Implement \`fetch_paper_pdf\` in \`_tools_pdf.py\`. Downloads OA PDF from openAccessPdf.url. Skips if file exists. Tagged write. See spec §fetch_paper_pdf."

gh issue create --title "Implement convert_pdf_to_markdown and fetch_and_convert tools" \
  --label "area: pdf" --milestone "v0.4.0" \
  --body "Implement \`convert_pdf_to_markdown\` and \`fetch_and_convert\` in \`_tools_pdf.py\`. Both support use_vlm flag. fetch_and_convert fails gracefully at each stage. See spec §convert_pdf_to_markdown, §fetch_and_convert."

gh issue create --title "Ops documentation: Docker compose, env vars, deployment guide" \
  --label "area: ops" --milestone "v0.4.0" \
  --body "Update README with env var table, Docker compose snippet for homelab (Traefik + Authelia), and docling-serve integration notes."
```

---

### Task 3: Update pyproject.toml and config.py

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/scholar_mcp/config.py`
- Modify: `tests/test_mcp_server.py` (update any prefix references)

- [ ] **Step 1: Add dependencies to pyproject.toml**

In `pyproject.toml`, update the `[project.optional-dependencies]` section:

```toml
[project]
# ... existing fields ...
dependencies = ["httpx", "aiosqlite"]

[project.optional-dependencies]
mcp = ["fastmcp>=3.0,<4", "uvicorn"]
all = ["fastmcp>=3.0,<4", "uvicorn"]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "ruff>=0.1",
    "mypy>=1.0",
    "pip-audit>=2.7",
    "respx>=0.20",
]
```

Note: `httpx` and `aiosqlite` move to core `dependencies` (not extras) — the server needs them at runtime regardless of transport.

- [ ] **Step 2: Run uv sync to verify dependency resolution**

```bash
uv sync --all-extras
```

Expected: resolves without conflicts.

- [ ] **Step 3: Write failing tests for new config fields**

`tests/test_config.py`:

```python
import os
import pytest
from scholar_mcp.config import ServerConfig, load_config

def test_defaults(monkeypatch):
    monkeypatch.delenv("SCHOLAR_MCP_S2_API_KEY", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_DOCLING_URL", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_VLM_API_URL", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_VLM_API_KEY", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_VLM_MODEL", raising=False)
    monkeypatch.delenv("SCHOLAR_MCP_CACHE_DIR", raising=False)
    cfg = load_config()
    assert cfg.s2_api_key is None
    assert cfg.docling_url is None
    assert cfg.vlm_api_url is None
    assert cfg.vlm_api_key is None
    assert cfg.vlm_model == "gpt-4o"
    assert str(cfg.cache_dir) == "/data/scholar-mcp"

def test_env_vars_loaded(monkeypatch):
    monkeypatch.setenv("SCHOLAR_MCP_S2_API_KEY", "test-key")
    monkeypatch.setenv("SCHOLAR_MCP_DOCLING_URL", "http://docling:5001")
    monkeypatch.setenv("SCHOLAR_MCP_VLM_API_URL", "http://litellm:4000")
    monkeypatch.setenv("SCHOLAR_MCP_VLM_API_KEY", "vlm-key")
    monkeypatch.setenv("SCHOLAR_MCP_VLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", "/tmp/scholar-test")
    cfg = load_config()
    assert cfg.s2_api_key == "test-key"
    assert cfg.docling_url == "http://docling:5001"
    assert cfg.vlm_api_url == "http://litellm:4000"
    assert cfg.vlm_api_key == "vlm-key"
    assert cfg.vlm_model == "gpt-4o-mini"
    assert str(cfg.cache_dir) == "/tmp/scholar-test"
```

- [ ] **Step 4: Run test to verify it fails**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `FAIL` — `ServerConfig` has no `s2_api_key` attribute yet.

- [ ] **Step 5: Implement new config fields**

Replace the contents of `src/scholar_mcp/config.py`:

```python
"""Environment-based configuration for Scholar MCP Server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_ENV_PREFIX = "SCHOLAR_MCP"


@dataclass
class ServerConfig:
    """All configuration loaded from environment variables.

    Attributes:
        read_only: When True, write-tagged tools are hidden.
        s2_api_key: Semantic Scholar API key (enables higher rate limits).
        docling_url: Base URL of docling-serve instance. PDF tools return
            ``docling_not_configured`` if unset.
        vlm_api_url: OpenAI-compatible endpoint for VLM enrichment.
        vlm_api_key: API key for the VLM endpoint.
        vlm_model: Model name passed to the VLM endpoint.
        cache_dir: Directory for SQLite DB and downloaded PDFs.
    """

    read_only: bool = True
    s2_api_key: str | None = None
    docling_url: str | None = None
    vlm_api_url: str | None = None
    vlm_api_key: str | None = None
    vlm_model: str = "gpt-4o"
    cache_dir: Path = Path("/data/scholar-mcp")


def load_config() -> ServerConfig:
    """Load :class:`ServerConfig` from environment variables.

    Returns:
        Populated :class:`ServerConfig` instance.
    """
    p = _ENV_PREFIX

    def _bool(key: str, default: bool) -> bool:
        val = os.environ.get(f"{p}_{key}")
        if val is None:
            return default
        return val.lower() not in ("0", "false", "no")

    def _str(key: str) -> str | None:
        return os.environ.get(f"{p}_{key}") or None

    return ServerConfig(
        read_only=_bool("READ_ONLY", True),
        s2_api_key=_str("S2_API_KEY"),
        docling_url=_str("DOCLING_URL"),
        vlm_api_url=_str("VLM_API_URL"),
        vlm_api_key=_str("VLM_API_KEY"),
        vlm_model=os.environ.get(f"{p}_VLM_MODEL", "gpt-4o"),
        cache_dir=Path(os.environ.get(f"{p}_CACHE_DIR", "/data/scholar-mcp")),
    )
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 7: Run full test suite to check nothing regressed**

```bash
uv run pytest
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/scholar_mcp/config.py tests/test_config.py
git commit -m "feat: add scholar-mcp configuration fields"
```

---

### Task 4: Implement ScholarCache

**Files:**
- Create: `src/scholar_mcp/_cache.py`
- Create: `tests/test_cache.py`

Closes issue: "Implement SQLite cache (ScholarCache)" (partial — CLI commands in Task 11)

- [ ] **Step 1: Write failing tests**

`tests/test_cache.py`:

```python
import time
import pytest
from scholar_mcp._cache import ScholarCache

@pytest.fixture
async def cache(tmp_path):
    c = ScholarCache(tmp_path / "test.db")
    await c.open()
    yield c
    await c.close()

async def test_paper_roundtrip(cache):
    data = {"paperId": "abc123", "title": "Test Paper", "year": 2024}
    await cache.set_paper("abc123", data)
    result = await cache.get_paper("abc123")
    assert result == data

async def test_paper_miss(cache):
    assert await cache.get_paper("nonexistent") is None

async def test_paper_ttl_expired(cache):
    data = {"paperId": "xyz", "title": "Old"}
    await cache.set_paper("xyz", data)
    # Manually expire by setting cached_at to the past
    import aiosqlite
    async with aiosqlite.connect(cache._db_path) as db:
        await db.execute(
            "UPDATE papers SET cached_at = ? WHERE paper_id = ?",
            (time.time() - 31 * 86400, "xyz"),
        )
        await db.commit()
    assert await cache.get_paper("xyz") is None

async def test_citations_roundtrip(cache):
    ids = ["p1", "p2", "p3"]
    await cache.set_citations("paper1", ids)
    assert await cache.get_citations("paper1") == ids

async def test_references_roundtrip(cache):
    ids = ["r1", "r2"]
    await cache.set_references("paper1", ids)
    assert await cache.get_references("paper1") == ids

async def test_author_roundtrip(cache):
    data = {"authorId": "auth1", "name": "Ada Lovelace"}
    await cache.set_author("auth1", data)
    assert await cache.get_author("auth1") == data

async def test_openalex_roundtrip(cache):
    data = {"doi": "10.1/test", "affiliations": []}
    await cache.set_openalex("10.1/test", data)
    assert await cache.get_openalex("10.1/test") == data

async def test_alias_roundtrip(cache):
    await cache.set_alias("DOI:10.1/test", "s2id123")
    assert await cache.get_alias("DOI:10.1/test") == "s2id123"

async def test_alias_no_ttl(cache):
    """Aliases never expire."""
    await cache.set_alias("ARXIV:2401.0001", "s2abc")
    import aiosqlite
    async with aiosqlite.connect(cache._db_path) as db:
        # id_aliases table has no cached_at — confirm row persists
        async with db.execute(
            "SELECT s2_paper_id FROM id_aliases WHERE raw_id = ?", ("ARXIV:2401.0001",)
        ) as cur:
            row = await cur.fetchone()
    assert row is not None
    assert row[0] == "s2abc"

async def test_stats(cache):
    await cache.set_paper("p1", {"paperId": "p1"})
    await cache.set_author("a1", {"authorId": "a1"})
    stats = await cache.stats()
    assert stats["papers"] == 1
    assert stats["authors"] == 1

async def test_clear_all(cache):
    await cache.set_paper("p1", {"paperId": "p1"})
    await cache.clear()
    assert await cache.get_paper("p1") is None

async def test_clear_older_than(cache):
    await cache.set_paper("old", {"paperId": "old"})
    await cache.set_paper("new", {"paperId": "new"})
    import aiosqlite
    async with aiosqlite.connect(cache._db_path) as db:
        await db.execute(
            "UPDATE papers SET cached_at = ? WHERE paper_id = ?",
            (time.time() - 10 * 86400, "old"),
        )
        await db.commit()
    await cache.clear(older_than_days=7)
    assert await cache.get_paper("old") is None
    assert await cache.get_paper("new") is not None
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_cache.py -v
```

Expected: `FAIL` — `_cache` module does not exist.

- [ ] **Step 3: Implement ScholarCache**

`src/scholar_mcp/_cache.py`:

```python
"""SQLite-backed cache for Scholar MCP Server."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# TTLs in seconds
_PAPER_TTL = 30 * 86400       # 30 days
_CITATION_TTL = 7 * 86400     # 7 days
_AUTHOR_TTL = 30 * 86400      # 30 days
_OPENALEX_TTL = 30 * 86400    # 30 days

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES (1);

CREATE TABLE IF NOT EXISTS papers (
    paper_id  TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS citation_counts (
    paper_id       TEXT PRIMARY KEY,
    citation_count INTEGER NOT NULL,
    reference_count INTEGER NOT NULL,
    cached_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS citations (
    paper_id   TEXT PRIMARY KEY,
    citing_ids TEXT NOT NULL,
    cached_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS refs (
    paper_id       TEXT PRIMARY KEY,
    referenced_ids TEXT NOT NULL,
    cached_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS authors (
    author_id TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS openalex (
    doi       TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    cached_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS id_aliases (
    raw_id     TEXT PRIMARY KEY,
    s2_paper_id TEXT NOT NULL
);
"""


class ScholarCache:
    """Async SQLite cache with TTL-based expiry.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        """Open database connection and apply schema."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("cache_opened path=%s", self._db_path)

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Papers
    # ------------------------------------------------------------------

    async def get_paper(self, paper_id: str) -> dict | None:
        """Return cached paper data or None if missing/stale."""
        assert self._db
        async with self._db.execute(
            "SELECT data, cached_at FROM papers WHERE paper_id = ?", (paper_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        if time.time() - row[1] > _PAPER_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_paper(self, paper_id: str, data: dict) -> None:
        """Cache paper data."""
        assert self._db
        await self._db.execute(
            "INSERT OR REPLACE INTO papers (paper_id, data, cached_at) VALUES (?, ?, ?)",
            (paper_id, json.dumps(data), time.time()),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Citations (list of citing paper IDs)
    # ------------------------------------------------------------------

    async def get_citations(self, paper_id: str) -> list[str] | None:
        """Return cached list of citing paper IDs or None if missing/stale."""
        assert self._db
        async with self._db.execute(
            "SELECT citing_ids, cached_at FROM citations WHERE paper_id = ?", (paper_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _CITATION_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_citations(self, paper_id: str, ids: list[str]) -> None:
        """Cache list of citing paper IDs."""
        assert self._db
        await self._db.execute(
            "INSERT OR REPLACE INTO citations (paper_id, citing_ids, cached_at) VALUES (?, ?, ?)",
            (paper_id, json.dumps(ids), time.time()),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # References (list of referenced paper IDs)
    # ------------------------------------------------------------------

    async def get_references(self, paper_id: str) -> list[str] | None:
        """Return cached list of referenced paper IDs or None if missing/stale."""
        assert self._db
        async with self._db.execute(
            "SELECT referenced_ids, cached_at FROM refs WHERE paper_id = ?", (paper_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _CITATION_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_references(self, paper_id: str, ids: list[str]) -> None:
        """Cache list of referenced paper IDs."""
        assert self._db
        await self._db.execute(
            "INSERT OR REPLACE INTO refs (paper_id, referenced_ids, cached_at) VALUES (?, ?, ?)",
            (paper_id, json.dumps(ids), time.time()),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Authors
    # ------------------------------------------------------------------

    async def get_author(self, author_id: str) -> dict | None:
        """Return cached author data or None if missing/stale."""
        assert self._db
        async with self._db.execute(
            "SELECT data, cached_at FROM authors WHERE author_id = ?", (author_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _AUTHOR_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_author(self, author_id: str, data: dict) -> None:
        """Cache author data."""
        assert self._db
        await self._db.execute(
            "INSERT OR REPLACE INTO authors (author_id, data, cached_at) VALUES (?, ?, ?)",
            (author_id, json.dumps(data), time.time()),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # OpenAlex enrichment
    # ------------------------------------------------------------------

    async def get_openalex(self, doi: str) -> dict | None:
        """Return cached OpenAlex data for a DOI or None if missing/stale."""
        assert self._db
        async with self._db.execute(
            "SELECT data, cached_at FROM openalex WHERE doi = ?", (doi,)
        ) as cur:
            row = await cur.fetchone()
        if row is None or time.time() - row[1] > _OPENALEX_TTL:
            return None
        return json.loads(row[0])  # type: ignore[no-any-return]

    async def set_openalex(self, doi: str, data: dict) -> None:
        """Cache OpenAlex enrichment data for a DOI."""
        assert self._db
        await self._db.execute(
            "INSERT OR REPLACE INTO openalex (doi, data, cached_at) VALUES (?, ?, ?)",
            (doi, json.dumps(data), time.time()),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Identifier aliases (no TTL)
    # ------------------------------------------------------------------

    async def get_alias(self, raw_id: str) -> str | None:
        """Return the S2 paper ID for a raw identifier, or None if unknown."""
        assert self._db
        async with self._db.execute(
            "SELECT s2_paper_id FROM id_aliases WHERE raw_id = ?", (raw_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def set_alias(self, raw_id: str, s2_paper_id: str) -> None:
        """Map a raw identifier to a canonical S2 paper ID."""
        assert self._db
        await self._db.execute(
            "INSERT OR REPLACE INTO id_aliases (raw_id, s2_paper_id) VALUES (?, ?)",
            (raw_id, s2_paper_id),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def stats(self) -> dict:
        """Return row counts and file size for all tables.

        Returns:
            Dict with keys: papers, citations, refs, authors, openalex,
            id_aliases, db_size_bytes.
        """
        assert self._db
        counts: dict[str, int] = {}
        for table in ("papers", "citations", "refs", "authors", "openalex", "id_aliases"):
            async with self._db.execute(f"SELECT COUNT(*) FROM {table}") as cur:
                row = await cur.fetchone()
                counts[table] = row[0] if row else 0
        counts["db_size_bytes"] = self._db_path.stat().st_size if self._db_path.exists() else 0
        return counts

    async def clear(self, older_than_days: int | None = None) -> None:
        """Clear cache entries.

        Args:
            older_than_days: If set, only evict entries older than this many
                days. If None, wipes all entries in all TTL-bearing tables.
        """
        assert self._db
        if older_than_days is None:
            for table in ("papers", "citation_counts", "citations", "refs", "authors", "openalex"):
                await self._db.execute(f"DELETE FROM {table}")
        else:
            cutoff = time.time() - older_than_days * 86400
            for table in ("papers", "citation_counts", "citations", "refs", "authors", "openalex"):
                await self._db.execute(f"DELETE FROM {table} WHERE cached_at < ?", (cutoff,))
        await self._db.commit()
        logger.info("cache_cleared older_than_days=%s", older_than_days)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cache.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/scholar_mcp/_cache.py tests/test_cache.py
git commit -m "feat: implement ScholarCache with aiosqlite"
```

---

### Task 5: Implement RateLimiter and S2Client

**Files:**
- Create: `src/scholar_mcp/_rate_limiter.py`
- Create: `src/scholar_mcp/_s2_client.py`
- Create: `tests/test_rate_limiter.py`
- Create: `tests/test_s2_client.py`

Closes issue: "Implement S2 API client with rate limiting"

- [ ] **Step 1: Write failing rate limiter tests**

`tests/test_rate_limiter.py`:

```python
import asyncio
import pytest
import httpx
from scholar_mcp._rate_limiter import RateLimiter, with_s2_retry

async def test_delay_between_requests():
    limiter = RateLimiter(delay=0.05)
    t0 = asyncio.get_event_loop().time()
    await limiter.acquire()
    await limiter.acquire()
    elapsed = asyncio.get_event_loop().time() - t0
    assert elapsed >= 0.04  # at least one delay cycle

async def test_retry_on_429(respx_mock):
    limiter = RateLimiter(delay=0.0)
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.HTTPStatusError(
                "rate limited",
                request=httpx.Request("GET", "http://x"),
                response=httpx.Response(429),
            )
        return "ok"

    result = await with_s2_retry(flaky, limiter, max_retries=3, base_delay=0.01)
    assert result == "ok"
    assert call_count == 3

async def test_retry_exhausted():
    limiter = RateLimiter(delay=0.0)

    async def always_429():
        raise httpx.HTTPStatusError(
            "rate limited",
            request=httpx.Request("GET", "http://x"),
            response=httpx.Response(429),
        )

    with pytest.raises(httpx.HTTPStatusError):
        await with_s2_retry(always_429, limiter, max_retries=2, base_delay=0.01)
```

- [ ] **Step 2: Implement RateLimiter**

`src/scholar_mcp/_rate_limiter.py`:

```python
"""Rate limiter and retry helper for external API calls."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RateLimiter:
    """Inter-request delay enforcer.

    Args:
        delay: Minimum seconds between requests.
    """

    delay: float
    _last: float = field(default=0.0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def acquire(self) -> None:
        """Wait until the minimum inter-request delay has elapsed."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait = self._last + self.delay - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = asyncio.get_event_loop().time()


async def with_s2_retry(
    coro_func: Callable[[], Awaitable[Any]],
    limiter: RateLimiter,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> Any:
    """Call an async function with exponential backoff on HTTP 429.

    Args:
        coro_func: Zero-argument async callable to invoke.
        limiter: Rate limiter to acquire before each attempt.
        max_retries: Maximum number of retry attempts after the first failure.
        base_delay: Base delay in seconds for exponential backoff.

    Returns:
        The return value of ``coro_func`` on success.

    Raises:
        httpx.HTTPStatusError: If retries are exhausted or a non-429 error occurs.
    """
    for attempt in range(max_retries + 1):
        await limiter.acquire()
        try:
            return await coro_func()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < max_retries:
                wait = base_delay * (2 ** attempt)
                logger.warning(
                    "s2_rate_limited attempt=%d/%d waiting=%.1fs",
                    attempt + 1, max_retries + 1, wait,
                )
                await asyncio.sleep(wait)
            else:
                raise
    raise RuntimeError("unreachable")  # pragma: no cover
```

- [ ] **Step 3: Run rate limiter tests**

```bash
uv run pytest tests/test_rate_limiter.py -v
```

Expected: all pass.

- [ ] **Step 4: Write failing S2 client tests**

`tests/test_s2_client.py`:

```python
import pytest
import respx
import httpx
from scholar_mcp._s2_client import S2Client, FIELD_SETS

S2_BASE = "https://api.semanticscholar.org/graph/v1"

@pytest.fixture
def client():
    return S2Client(api_key=None, delay=0.0)

@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper(respx_mock, client):
    respx_mock.get("/paper/abc123").mock(return_value=httpx.Response(
        200, json={"paperId": "abc123", "title": "Test Paper", "year": 2024}
    ))
    result = await client.get_paper("abc123")
    assert result["paperId"] == "abc123"
    assert result["title"] == "Test Paper"

@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_not_found(respx_mock, client):
    respx_mock.get("/paper/missing").mock(return_value=httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_paper("missing")

@pytest.mark.respx(base_url=S2_BASE)
async def test_search_papers(respx_mock, client):
    respx_mock.get("/paper/search").mock(return_value=httpx.Response(
        200, json={"data": [{"paperId": "p1", "title": "Result 1"}], "total": 1}
    ))
    result = await client.search_papers("machine learning", fields="compact", limit=10, offset=0)
    assert result["total"] == 1
    assert result["data"][0]["paperId"] == "p1"

@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citations(respx_mock, client):
    respx_mock.get("/paper/p1/citations").mock(return_value=httpx.Response(
        200, json={"data": [{"citingPaper": {"paperId": "c1", "title": "Citer"}}]}
    ))
    result = await client.get_citations("p1", fields="compact", limit=10, offset=0)
    assert result["data"][0]["citingPaper"]["paperId"] == "c1"

@pytest.mark.respx(base_url=S2_BASE)
async def test_batch_resolve(respx_mock, client):
    respx_mock.post("/paper/batch").mock(return_value=httpx.Response(
        200, json=[{"paperId": "p1", "title": "Paper 1"}, None]
    ))
    result = await client.batch_resolve(["p1", "unknown"], fields="standard")
    assert result[0]["paperId"] == "p1"
    assert result[1] is None

def test_field_sets_exist():
    for preset in ("compact", "standard", "full"):
        assert preset in FIELD_SETS
        assert "title" in FIELD_SETS[preset]
```

- [ ] **Step 5: Implement S2Client**

`src/scholar_mcp/_s2_client.py`:

```python
"""Semantic Scholar API client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ._rate_limiter import RateLimiter, with_s2_retry

logger = logging.getLogger(__name__)

_S2_BASE = "https://api.semanticscholar.org/graph/v1"

FIELD_SETS: dict[str, str] = {
    "compact": "title,year,venue,citationCount,paperId",
    "standard": "title,year,venue,citationCount,paperId,authors,externalIds,abstract",
    "full": (
        "title,year,venue,citationCount,paperId,authors,externalIds,"
        "abstract,tldr,openAccessPdf,fieldsOfStudy,referenceCount"
    ),
}


class S2Client:
    """Async client for the Semantic Scholar Graph API.

    Args:
        api_key: Optional S2 API key. Enables higher rate limits.
        delay: Inter-request delay in seconds. Defaults based on api_key
            presence: 1.1s without key, 0.1s with key.
    """

    def __init__(self, api_key: str | None, delay: float | None = None) -> None:
        self._api_key = api_key
        if delay is None:
            delay = 0.1 if api_key else 1.1
        self._limiter = RateLimiter(delay=delay)
        headers: dict[str, str] = {"User-Agent": "scholar-mcp/0.1"}
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.AsyncClient(base_url=_S2_BASE, headers=headers, timeout=30.0)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def _get(self, path: str, **params: Any) -> dict:
        async def _call() -> dict:
            r = await self._client.get(path, params={k: v for k, v in params.items() if v is not None})
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
        return await with_s2_retry(_call, self._limiter)  # type: ignore[return-value]

    async def get_paper(self, identifier: str, fields: str = FIELD_SETS["full"]) -> dict:
        """Fetch full metadata for a single paper.

        Args:
            identifier: DOI, S2 paper ID, arXiv ID (prefix ``ARXIV:``), etc.
            fields: Comma-separated S2 field names or a preset from FIELD_SETS.

        Returns:
            Paper metadata dict.
        """
        return await self._get(f"/paper/{identifier}", fields=fields)

    async def search_papers(
        self,
        query: str,
        *,
        fields: str,
        limit: int,
        offset: int,
        year: str | None = None,
        fieldsOfStudy: str | None = None,
        venue: str | None = None,
        minCitationCount: int | None = None,
        sort: str | None = None,
    ) -> dict:
        """Search the S2 corpus.

        Returns:
            Dict with ``data`` (list of paper dicts) and ``total``.
        """
        return await self._get(
            "/paper/search",
            query=query,
            fields=fields,
            limit=limit,
            offset=offset,
            year=year,
            fieldsOfStudy=fieldsOfStudy,
            venue=venue,
            minCitationCount=minCitationCount,
            sort=sort,
        )

    async def get_citations(
        self,
        paper_id: str,
        *,
        fields: str,
        limit: int,
        offset: int,
        year: str | None = None,
        fieldsOfStudy: str | None = None,
        minCitationCount: int | None = None,
    ) -> dict:
        """Fetch papers that cite the given paper.

        Returns:
            Dict with ``data`` (list of ``{"citingPaper": {...}}`` dicts).
        """
        return await self._get(
            f"/paper/{paper_id}/citations",
            fields=f"citingPaper.{fields}",
            limit=limit,
            offset=offset,
            year=year,
            fieldsOfStudy=fieldsOfStudy,
            minCitationCount=minCitationCount,
        )

    async def get_references(
        self,
        paper_id: str,
        *,
        fields: str,
        limit: int,
        offset: int,
    ) -> dict:
        """Fetch papers referenced by the given paper.

        Returns:
            Dict with ``data`` (list of ``{"citedPaper": {...}}`` dicts).
        """
        return await self._get(
            f"/paper/{paper_id}/references",
            fields=f"citedPaper.{fields}",
            limit=limit,
            offset=offset,
        )

    async def search_authors(self, name: str, limit: int = 5) -> list[dict]:
        """Search for authors by name.

        Returns:
            List of author dicts with name, affiliations, hIndex, paperCount.
        """
        result = await self._get(
            "/author/search",
            query=name,
            fields="name,affiliations,hIndex,paperCount",
            limit=limit,
        )
        return result.get("data", [])  # type: ignore[return-value]

    async def get_author(
        self, author_id: str, *, limit: int = 20, offset: int = 0
    ) -> dict:
        """Fetch author profile with paginated publications.

        Returns:
            Author dict with ``papers`` list.
        """
        return await self._get(
            f"/author/{author_id}",
            fields="name,affiliations,hIndex,paperCount,papers.paperId,papers.title,papers.year,papers.citationCount",
            limit=limit,
            offset=offset,
        )

    async def recommend(
        self,
        positive_ids: list[str],
        *,
        negative_ids: list[str] | None = None,
        limit: int = 10,
        fields: str,
    ) -> list[dict]:
        """Fetch paper recommendations from S2 recommendations endpoint.

        Returns:
            List of recommended paper dicts.
        """
        async def _call() -> list[dict]:
            body: dict[str, Any] = {
                "positivePaperIds": positive_ids,
                "negativePaperIds": negative_ids or [],
            }
            r = await self._client.post(
                "https://api.semanticscholar.org/recommendations/v1/papers",
                json=body,
                params={"fields": fields, "limit": limit},
            )
            r.raise_for_status()
            return r.json().get("recommendedPapers", [])  # type: ignore[no-any-return]
        await self._limiter.acquire()
        return await _call()

    async def batch_resolve(self, ids: list[str], *, fields: str) -> list[dict | None]:
        """Resolve a batch of paper IDs using the S2 batch endpoint.

        Args:
            ids: List of S2 paper IDs or DOIs (prefixed with ``DOI:``).
            fields: Comma-separated field names.

        Returns:
            List of paper dicts (None for unresolved items, preserving order).
        """
        async def _call() -> list[dict | None]:
            r = await self._client.post(
                "/paper/batch",
                json={"ids": ids},
                params={"fields": fields},
            )
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
        await self._limiter.acquire()
        return await _call()
```

- [ ] **Step 6: Run S2 client tests**

```bash
uv run pytest tests/test_s2_client.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/scholar_mcp/_rate_limiter.py src/scholar_mcp/_s2_client.py \
        tests/test_rate_limiter.py tests/test_s2_client.py
git commit -m "feat: implement RateLimiter and S2Client"
```

---

### Task 6: Wire up ServiceBundle lifespan

**Files:**
- Replace: `src/scholar_mcp/_server_deps.py`
- Replace: `src/scholar_mcp/_server_tools.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Replace `_server_deps.py`**

```python
"""Service bundle lifespan and dependency injection for Scholar MCP Server."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from .config import ServerConfig, load_config
from ._cache import ScholarCache
from ._s2_client import S2Client

logger = logging.getLogger(__name__)

_OPENALEX_BASE = "https://api.openalex.org"


@dataclass
class ServiceBundle:
    """All shared services passed to tools via FastMCP dependency injection.

    Attributes:
        s2: Semantic Scholar API client.
        openalex: OpenAlex API client (httpx.AsyncClient pointed at OpenAlex).
        docling: docling-serve httpx client, or None if not configured.
        cache: SQLite cache.
        config: Server configuration.
    """

    s2: S2Client
    openalex: httpx.AsyncClient  # NOTE: refined to OpenAlexClient in Task 11 Step 3
    docling: httpx.AsyncClient | None  # NOTE: refined to DoclingClient in Task 12 Step 4
    cache: ScholarCache
    config: ServerConfig


@asynccontextmanager
async def make_service_lifespan(
    app: FastMCP,
) -> AsyncGenerator[dict[str, ServiceBundle], None]:
    """FastMCP lifespan: create all clients, open cache, yield bundle.

    Args:
        app: The FastMCP application instance (unused but required by protocol).

    Yields:
        Dict mapping ``"bundle"`` to the :class:`ServiceBundle`.
    """
    config = load_config()
    config.cache_dir.mkdir(parents=True, exist_ok=True)

    s2 = S2Client(api_key=config.s2_api_key)
    openalex = httpx.AsyncClient(
        base_url=_OPENALEX_BASE,
        headers={"User-Agent": "scholar-mcp/0.1 (mailto:scholar-mcp@pvliesdonk.nl)"},
        timeout=30.0,
    )
    docling: httpx.AsyncClient | None = None
    if config.docling_url:
        docling = httpx.AsyncClient(base_url=config.docling_url, timeout=300.0)
        logger.info("docling_configured url=%s", config.docling_url)
    else:
        logger.info("docling_not_configured pdf_tools_disabled")

    cache = ScholarCache(config.cache_dir / "cache.db")
    await cache.open()

    bundle = ServiceBundle(
        s2=s2, openalex=openalex, docling=docling, cache=cache, config=config
    )
    try:
        yield {"bundle": bundle}
    finally:
        await s2.aclose()
        await openalex.aclose()
        if docling:
            await docling.aclose()
        await cache.close()


def get_bundle(ctx: Context = Depends(Context)) -> ServiceBundle:
    """FastMCP dependency: extract ServiceBundle from lifespan context.

    Args:
        ctx: FastMCP request context (injected automatically).

    Returns:
        The :class:`ServiceBundle` created during lifespan.
    """
    return ctx.request_context.lifespan_context["bundle"]  # type: ignore[return-value]
```

- [ ] **Step 2: Replace `_server_tools.py` with dispatch stub**

```python
"""MCP tool registrations — dispatches to category modules."""

from __future__ import annotations

from fastmcp import FastMCP


def register_tools(mcp: FastMCP, *, transport: str = "stdio") -> None:
    """Register all MCP tools on *mcp*.

    Args:
        mcp: The FastMCP instance.
        transport: Active transport (unused currently, kept for compatibility).
    """
    # Category modules are imported here to avoid circular imports.
    # Each module registers its tools onto `mcp` and accesses the
    # ServiceBundle via Depends(get_bundle).
    from ._tools_search import register_search_tools
    register_search_tools(mcp)

    # Remaining categories are added as their tasks are implemented:
    # from ._tools_graph import register_graph_tools; register_graph_tools(mcp)
    # from ._tools_recommendations import register_recommendation_tools; register_recommendation_tools(mcp)
    # from ._tools_pdf import register_pdf_tools; register_pdf_tools(mcp)
    # from ._tools_utility import register_utility_tools; register_utility_tools(mcp)
```

- [ ] **Step 3: Update `mcp_server.py` to use the new lifespan**

In `src/scholar_mcp/mcp_server.py`, find the lifespan import and update it to:

```python
from ._server_deps import make_service_lifespan
```

Verify the `create_server()` function already passes `lifespan=make_service_lifespan` — if the template wires this automatically, no change is needed. Run `grep -n lifespan src/scholar_mcp/mcp_server.py` to confirm.

- [ ] **Step 4: Add ServiceBundle fixture to conftest.py**

```python
# tests/conftest.py — add these fixtures (keep any existing ones)
import pytest
import httpx
import respx
from pathlib import Path
from scholar_mcp._cache import ScholarCache
from scholar_mcp._s2_client import S2Client
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp.config import ServerConfig

@pytest.fixture
async def cache(tmp_path: Path) -> ScholarCache:
    c = ScholarCache(tmp_path / "test.db")
    await c.open()
    yield c
    await c.close()

@pytest.fixture
def test_config(tmp_path: Path) -> ServerConfig:
    return ServerConfig(cache_dir=tmp_path, docling_url=None)

@pytest.fixture
def bundle(cache: ScholarCache, test_config: ServerConfig) -> ServiceBundle:
    s2 = S2Client(api_key=None, delay=0.0)
    openalex = httpx.AsyncClient(base_url="https://api.openalex.org")
    return ServiceBundle(
        s2=s2,
        openalex=openalex,
        docling=None,
        cache=cache,
        config=test_config,
    )
```

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest -v
```

Expected: all pass (ping/example_write tests may now fail — delete the example tool tests that reference removed tools).

- [ ] **Step 6: Commit**

```bash
git add src/scholar_mcp/_server_deps.py src/scholar_mcp/_server_tools.py \
        tests/conftest.py
git commit -m "feat: wire ServiceBundle lifespan and tool dispatch"
```

---

### Task 7: Implement search tools (v0.1.0)

**Files:**
- Create: `src/scholar_mcp/_tools_search.py`
- Create: `tests/test_tools_search.py`
- Modify: `src/scholar_mcp/_server_tools.py` (uncomment registration if needed)

Closes issues: "Implement search_papers tool", "Implement get_paper tool", "Implement get_author tool"

- [ ] **Step 1: Write failing tests**

`tests/test_tools_search.py`:

```python
import pytest
import respx
import httpx
from fastmcp import FastMCP
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_search import register_search_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"

@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    app = FastMCP("test")
    # Inject bundle into lifespan context for Depends(get_bundle)
    app._lifespan_context = {"bundle": bundle}
    register_search_tools(app)
    return app

@pytest.mark.respx(base_url=S2_BASE)
async def test_search_papers_returns_results(respx_mock, mcp):
    respx_mock.get("/paper/search").mock(return_value=httpx.Response(200, json={
        "data": [{"paperId": "p1", "title": "Attention is All You Need", "year": 2017,
                  "venue": "NeurIPS", "citationCount": 50000}],
        "total": 1,
    }))
    async with mcp.test_client() as client:
        result = await client.call_tool("search_papers", {"query": "attention transformer"})
    assert result[0].text  # has content
    import json
    data = json.loads(result[0].text)
    assert data["total"] == 1
    assert data["data"][0]["paperId"] == "p1"

@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_returns_full_metadata(respx_mock, mcp):
    respx_mock.get("/paper/abc123").mock(return_value=httpx.Response(200, json={
        "paperId": "abc123",
        "title": "Test Paper",
        "year": 2024,
        "abstract": "An abstract.",
        "citationCount": 42,
    }))
    async with mcp.test_client() as client:
        result = await client.call_tool("get_paper", {"identifier": "abc123"})
    import json
    data = json.loads(result[0].text)
    assert data["paperId"] == "abc123"

@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_not_found(respx_mock, mcp):
    respx_mock.get("/paper/missing").mock(return_value=httpx.Response(404))
    async with mcp.test_client() as client:
        result = await client.call_tool("get_paper", {"identifier": "missing"})
    import json
    data = json.loads(result[0].text)
    assert data["error"] == "not_found"

@pytest.mark.respx(base_url=S2_BASE)
async def test_get_author_by_id(respx_mock, mcp):
    respx_mock.get("/author/auth1").mock(return_value=httpx.Response(200, json={
        "authorId": "auth1",
        "name": "Ada Lovelace",
        "hIndex": 42,
        "paperCount": 100,
        "papers": [{"paperId": "p1", "title": "Paper 1", "year": 2020, "citationCount": 5}],
    }))
    async with mcp.test_client() as client:
        result = await client.call_tool("get_author", {"identifier": "auth1"})
    import json
    data = json.loads(result[0].text)
    assert data["name"] == "Ada Lovelace"

@pytest.mark.respx(base_url=S2_BASE)
async def test_get_author_by_name_returns_candidates(respx_mock, mcp):
    respx_mock.get("/author/search").mock(return_value=httpx.Response(200, json={
        "data": [
            {"authorId": "a1", "name": "John Smith", "hIndex": 10, "paperCount": 50},
            {"authorId": "a2", "name": "John Smith", "hIndex": 5, "paperCount": 20},
        ]
    }))
    async with mcp.test_client() as client:
        result = await client.call_tool("get_author", {"identifier": "John Smith"})
    import json
    data = json.loads(result[0].text)
    assert data["candidates"] is not None
    assert len(data["candidates"]) == 2
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_tools_search.py -v
```

Expected: `FAIL` — `_tools_search` module does not exist.

- [ ] **Step 3: Implement search tools**

`src/scholar_mcp/_tools_search.py`:

```python
"""Search and retrieval MCP tools."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._server_deps import ServiceBundle, get_bundle
from ._s2_client import FIELD_SETS

logger = logging.getLogger(__name__)


def register_search_tools(mcp: FastMCP) -> None:
    """Register search and retrieval tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool()
    async def search_papers(
        query: str,
        fields: Literal["compact", "standard", "full"] = "compact",
        limit: int = 10,
        offset: int = 0,
        year_start: int | None = None,
        year_end: int | None = None,
        fields_of_study: list[str] | None = None,
        venue: str | None = None,
        min_citations: int | None = None,
        sort: Literal["relevance", "citations", "year"] = "relevance",
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Search Semantic Scholar for papers matching a query.

        Args:
            query: Keyword or semantic search query.
            fields: Field set preset — compact, standard, or full.
            limit: Maximum results to return (max 100).
            offset: Pagination offset.
            year_start: Earliest publication year (inclusive).
            year_end: Latest publication year (inclusive).
            fields_of_study: Filter by fields, e.g. ["Computer Science"].
            venue: Filter by venue name.
            min_citations: Minimum citation count.
            sort: Sort order — relevance, citations, or year.

        Returns:
            JSON string with ``data`` (list of papers) and ``total``.
        """
        year: str | None = None
        if year_start and year_end:
            year = f"{year_start}-{year_end}"
        elif year_start:
            year = f"{year_start}-"
        elif year_end:
            year = f"-{year_end}"

        s2_sort = {"relevance": None, "citations": "citationCount:desc", "year": "publicationDate:desc"}.get(sort)
        fos = ",".join(fields_of_study) if fields_of_study else None

        try:
            result = await bundle.s2.search_papers(
                query,
                fields=FIELD_SETS[fields],
                limit=limit,
                offset=offset,
                year=year,
                fieldsOfStudy=fos,
                venue=venue,
                minCitationCount=min_citations,
                sort=s2_sort,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return json.dumps({"error": "not_found", "identifier": query})
            return json.dumps({
                "error": "upstream_error",
                "status": exc.response.status_code,
                "detail": exc.response.text[:200],
            })
        return json.dumps(result)

    @mcp.tool()
    async def get_paper(
        identifier: str,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Fetch full metadata for a single paper.

        Args:
            identifier: Paper identifier — DOI, S2 paper ID, arXiv ID
                (prefix with ``ARXIV:``), ACM ID (``ACM:``), or PubMed ID
                (``PMID:``).

        Returns:
            JSON string with full paper metadata (full field set), or
            ``{"error": "not_found", "identifier": "..."}`` if not found.
        """
        cached = await bundle.cache.get_alias(identifier)
        if cached:
            data = await bundle.cache.get_paper(cached)
            if data:
                logger.debug("cache_hit identifier=%s", identifier)
                return json.dumps(data)

        try:
            data = await bundle.s2.get_paper(identifier)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return json.dumps({"error": "not_found", "identifier": identifier})
            return json.dumps({
                "error": "upstream_error",
                "status": exc.response.status_code,
                "detail": exc.response.text[:200],
            })

        paper_id = data.get("paperId", "")
        if paper_id:
            await bundle.cache.set_paper(paper_id, data)
            if identifier != paper_id:
                await bundle.cache.set_alias(identifier, paper_id)

        return json.dumps(data)

    @mcp.tool()
    async def get_author(
        identifier: str,
        limit: int = 20,
        offset: int = 0,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Fetch author profile and publications, or search by name.

        If *identifier* looks like a numeric S2 author ID, fetches the author
        directly. Otherwise performs a name search and returns up to 5 candidates
        for disambiguation.

        Args:
            identifier: S2 author ID (numeric string) or free-text author name.
            limit: Publications per page (only used for direct ID lookup).
            offset: Publication page offset (only used for direct ID lookup).

        Returns:
            JSON with author data and paginated ``papers`` list, or
            ``{"candidates": [...]}`` for name searches.
        """
        is_id = identifier.isdigit()

        if is_id:
            cached = await bundle.cache.get_author(identifier)
            if cached:
                return json.dumps(cached)
            try:
                data = await bundle.s2.get_author(identifier, limit=limit, offset=offset)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    return json.dumps({"error": "not_found", "identifier": identifier})
                return json.dumps({"error": "upstream_error", "status": exc.response.status_code})
            await bundle.cache.set_author(identifier, data)
            return json.dumps(data)

        # Name search — return candidates for disambiguation
        try:
            candidates = await bundle.s2.search_authors(identifier, limit=5)
        except httpx.HTTPStatusError as exc:
            return json.dumps({"error": "upstream_error", "status": exc.response.status_code})
        return json.dumps({"candidates": candidates})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_tools_search.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest
```

- [ ] **Step 6: Commit and close issues**

```bash
git add src/scholar_mcp/_tools_search.py tests/test_tools_search.py \
        src/scholar_mcp/_server_tools.py
git commit -m "feat: implement search_papers, get_paper, get_author tools"
```

Then close the three issues:

```bash
gh issue close <search_papers issue number> --comment "Implemented in _tools_search.py"
gh issue close <get_paper issue number> --comment "Implemented in _tools_search.py"
gh issue close <get_author issue number> --comment "Implemented in _tools_search.py"
```

---

### Task 8: Implement citation tools — get_citations and get_references (v0.2.0)

**Files:**
- Create: `src/scholar_mcp/_tools_graph.py`
- Create: `tests/test_tools_graph.py`
- Modify: `src/scholar_mcp/_server_tools.py`

Closes issue: "Implement get_citations and get_references tools"

- [ ] **Step 1: Write failing tests**

`tests/test_tools_graph.py` (initial):

```python
import json
import pytest
import respx
import httpx
from fastmcp import FastMCP
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_graph import register_graph_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"

@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    app = FastMCP("test")
    app._lifespan_context = {"bundle": bundle}
    register_graph_tools(app)
    return app

@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citations(respx_mock, mcp):
    respx_mock.get("/paper/p1/citations").mock(return_value=httpx.Response(200, json={
        "data": [{"citingPaper": {"paperId": "c1", "title": "Citer", "year": 2022, "citationCount": 5}}]
    }))
    async with mcp.test_client() as client:
        result = await client.call_tool("get_citations", {"identifier": "p1"})
    data = json.loads(result[0].text)
    assert data["data"][0]["citingPaper"]["paperId"] == "c1"

@pytest.mark.respx(base_url=S2_BASE)
async def test_get_references(respx_mock, mcp):
    respx_mock.get("/paper/p1/references").mock(return_value=httpx.Response(200, json={
        "data": [{"citedPaper": {"paperId": "r1", "title": "Foundation", "year": 2015, "citationCount": 1000}}]
    }))
    async with mcp.test_client() as client:
        result = await client.call_tool("get_references", {"identifier": "p1"})
    data = json.loads(result[0].text)
    assert data["data"][0]["citedPaper"]["paperId"] == "r1"

@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citations_not_found(respx_mock, mcp):
    respx_mock.get("/paper/missing/citations").mock(return_value=httpx.Response(404))
    async with mcp.test_client() as client:
        result = await client.call_tool("get_citations", {"identifier": "missing"})
    data = json.loads(result[0].text)
    assert data["error"] == "not_found"
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_tools_graph.py::test_get_citations \
              tests/test_tools_graph.py::test_get_references \
              tests/test_tools_graph.py::test_get_citations_not_found -v
```

Expected: `FAIL`.

- [ ] **Step 3: Implement `_tools_graph.py` with initial tools**

`src/scholar_mcp/_tools_graph.py`:

```python
"""Citation graph MCP tools."""

from __future__ import annotations

import json
import logging
from collections import deque
from typing import Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._server_deps import ServiceBundle, get_bundle
from ._s2_client import FIELD_SETS

logger = logging.getLogger(__name__)


def register_graph_tools(mcp: FastMCP) -> None:
    """Register citation graph tools on *mcp*."""

    @mcp.tool()
    async def get_citations(
        identifier: str,
        fields: Literal["compact", "standard", "full"] = "compact",
        limit: int = 20,
        offset: int = 0,
        year_start: int | None = None,
        year_end: int | None = None,
        fields_of_study: list[str] | None = None,
        min_citations: int | None = None,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Fetch papers that cite the given paper (forward citations).

        Args:
            identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).
            fields: Field set preset for returned paper records.
            limit: Max results (pagination).
            offset: Pagination offset.
            year_start: Filter citing papers published from this year.
            year_end: Filter citing papers published up to this year.
            fields_of_study: Filter by field of study.
            min_citations: Minimum citation count of citing papers.

        Returns:
            JSON with ``data`` list of ``{"citingPaper": {...}}`` dicts.
        """
        year: str | None = None
        if year_start and year_end:
            year = f"{year_start}-{year_end}"
        elif year_start:
            year = f"{year_start}-"
        elif year_end:
            year = f"-{year_end}"

        fos = ",".join(fields_of_study) if fields_of_study else None
        try:
            result = await bundle.s2.get_citations(
                identifier,
                fields=FIELD_SETS[fields],
                limit=limit,
                offset=offset,
                year=year,
                fieldsOfStudy=fos,
                minCitationCount=min_citations,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return json.dumps({"error": "not_found", "identifier": identifier})
            return json.dumps({"error": "upstream_error", "status": exc.response.status_code})
        return json.dumps(result)

    @mcp.tool()
    async def get_references(
        identifier: str,
        fields: Literal["compact", "standard", "full"] = "compact",
        limit: int = 50,
        offset: int = 0,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Fetch papers referenced by the given paper (backward references).

        Args:
            identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).
            fields: Field set preset for returned paper records.
            limit: Max results.
            offset: Pagination offset.

        Returns:
            JSON with ``data`` list of ``{"citedPaper": {...}}`` dicts.
        """
        try:
            result = await bundle.s2.get_references(
                identifier, fields=FIELD_SETS[fields], limit=limit, offset=offset
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return json.dumps({"error": "not_found", "identifier": identifier})
            return json.dumps({"error": "upstream_error", "status": exc.response.status_code})
        return json.dumps(result)

    # get_citation_graph and find_bridge_papers added in Task 9
```

- [ ] **Step 4: Enable graph tools in `_server_tools.py`**

Uncomment (or add) in `_server_tools.py`:

```python
    from ._tools_graph import register_graph_tools
    register_graph_tools(mcp)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_tools_graph.py -v
```

Expected: the three existing tests pass; skip the graph traversal tests (not yet written).

- [ ] **Step 6: Commit and close issue**

```bash
git add src/scholar_mcp/_tools_graph.py tests/test_tools_graph.py \
        src/scholar_mcp/_server_tools.py
git commit -m "feat: implement get_citations and get_references tools"
gh issue close <get_citations issue number> --comment "Implemented in _tools_graph.py"
```

---

### Task 9: Implement citation graph traversal — get_citation_graph and find_bridge_papers (v0.2.0)

**Files:**
- Modify: `src/scholar_mcp/_tools_graph.py`
- Modify: `tests/test_tools_graph.py`

Closes issues: "Implement get_citation_graph tool", "Implement find_bridge_papers tool"

- [ ] **Step 1: Write failing tests**

Add to `tests/test_tools_graph.py`:

```python
@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citation_graph_single_hop(respx_mock, mcp):
    # Seed paper: p1. Depth 1, direction=citations.
    # p1's citations: c1, c2
    respx_mock.get("/paper/p1/citations").mock(return_value=httpx.Response(200, json={
        "data": [
            {"citingPaper": {"paperId": "c1", "title": "C1", "year": 2022, "citationCount": 3}},
            {"citingPaper": {"paperId": "c2", "title": "C2", "year": 2023, "citationCount": 1}},
        ]
    }))
    async with mcp.test_client() as client:
        result = await client.call_tool("get_citation_graph", {
            "seed_ids": ["p1"],
            "direction": "citations",
            "depth": 1,
            "max_nodes": 50,
        })
    data = json.loads(result[0].text)
    node_ids = {n["id"] for n in data["nodes"]}
    assert "p1" in node_ids
    assert "c1" in node_ids
    assert "c2" in node_ids
    assert data["stats"]["truncated"] is False

@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citation_graph_max_nodes_cap(respx_mock, mcp):
    # max_nodes=2 with 3 results should truncate
    respx_mock.get("/paper/p1/citations").mock(return_value=httpx.Response(200, json={
        "data": [
            {"citingPaper": {"paperId": "c1", "title": "C1", "year": 2022, "citationCount": 1}},
            {"citingPaper": {"paperId": "c2", "title": "C2", "year": 2022, "citationCount": 1}},
            {"citingPaper": {"paperId": "c3", "title": "C3", "year": 2022, "citationCount": 1}},
        ]
    }))
    async with mcp.test_client() as client:
        result = await client.call_tool("get_citation_graph", {
            "seed_ids": ["p1"],
            "direction": "citations",
            "depth": 1,
            "max_nodes": 2,
        })
    data = json.loads(result[0].text)
    assert data["stats"]["truncated"] is True
    assert data["stats"]["total_nodes"] <= 2

@pytest.mark.respx(base_url=S2_BASE)
async def test_find_bridge_papers_direct(respx_mock, mcp):
    # Source p1 cites target p2 directly → path is [p1, p2]
    respx_mock.get("/paper/p1/references").mock(return_value=httpx.Response(200, json={
        "data": [{"citedPaper": {"paperId": "p2", "title": "Target", "year": 2020, "citationCount": 5}}]
    }))
    async with mcp.test_client() as client:
        result = await client.call_tool("find_bridge_papers", {
            "source_id": "p1",
            "target_id": "p2",
            "max_depth": 3,
            "direction": "references",
        })
    data = json.loads(result[0].text)
    assert data["found"] is True
    ids = [p["paperId"] for p in data["path"]]
    assert ids == ["p1", "p2"]

@pytest.mark.respx(base_url=S2_BASE)
async def test_find_bridge_papers_not_found(respx_mock, mcp):
    respx_mock.get("/paper/p1/references").mock(return_value=httpx.Response(200, json={"data": []}))
    async with mcp.test_client() as client:
        result = await client.call_tool("find_bridge_papers", {
            "source_id": "p1",
            "target_id": "nowhere",
            "max_depth": 1,
            "direction": "references",
        })
    data = json.loads(result[0].text)
    assert data["found"] is False
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_tools_graph.py::test_get_citation_graph_single_hop \
              tests/test_tools_graph.py::test_find_bridge_papers_direct -v
```

Expected: `FAIL`.

- [ ] **Step 3: Add graph traversal tools to `_tools_graph.py`**

Add these two tools inside `register_graph_tools`, after `get_references`:

```python
    @mcp.tool()
    async def get_citation_graph(
        seed_ids: list[str],
        direction: Literal["citations", "references", "both"] = "citations",
        depth: int = 1,
        max_nodes: int = 100,
        year_start: int | None = None,
        year_end: int | None = None,
        fields_of_study: list[str] | None = None,
        min_citations: int | None = None,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Traverse the citation graph from one or more seed papers.

        Performs BFS up to *depth* hops. Returns nodes (paper records) and
        directed edges. Hard-caps at *max_nodes* to prevent runaway expansion.

        Args:
            seed_ids: 1–10 paper identifiers to start from.
            direction: Expand via citations, references, or both.
            depth: Number of hops (1–3).
            max_nodes: Hard cap on total nodes returned.
            year_start: Filter expanded papers to this year and later.
            year_end: Filter expanded papers to this year and earlier.
            fields_of_study: Filter by field.
            min_citations: Minimum citation count of expanded papers.

        Returns:
            JSON ``{"nodes": [...], "edges": [...], "stats": {...}}``.
        """
        depth = max(1, min(depth, 3))
        nodes: dict[str, dict] = {}  # paper_id → compact record
        edges: list[dict] = []       # {"source": id, "target": id, "direction": "cites"}
        queue: deque[tuple[str, int]] = deque()

        # Seed with compact records for all seeds
        for seed_id in seed_ids[:10]:
            nodes[seed_id] = {"id": seed_id, "title": None, "year": None, "citationCount": None}
            queue.append((seed_id, 0))

        visited: set[str] = set(seed_ids[:10])
        truncated = False

        year: str | None = None
        if year_start and year_end:
            year = f"{year_start}-{year_end}"
        elif year_start:
            year = f"{year_start}-"
        elif year_end:
            year = f"-{year_end}"
        fos = ",".join(fields_of_study) if fields_of_study else None

        while queue:
            paper_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue

            neighbour_batches: list[tuple[str, str]] = []  # (neighbour_id, edge_direction)

            if direction in ("citations", "both"):
                try:
                    result = await bundle.s2.get_citations(
                        paper_id, fields=FIELD_SETS["compact"],
                        limit=50, offset=0,
                        year=year, fieldsOfStudy=fos,
                        minCitationCount=min_citations,
                    )
                    for item in result.get("data", []):
                        p = item.get("citingPaper", {})
                        if pid := p.get("paperId"):
                            neighbour_batches.append((pid, "cites"))
                            nodes.setdefault(pid, {
                                "id": pid, "title": p.get("title"),
                                "year": p.get("year"),
                                "citationCount": p.get("citationCount"),
                            })
                            edges.append({"source": pid, "target": paper_id, "direction": "cites"})
                except httpx.HTTPStatusError:
                    pass

            if direction in ("references", "both"):
                try:
                    result = await bundle.s2.get_references(
                        paper_id, fields=FIELD_SETS["compact"], limit=50, offset=0
                    )
                    for item in result.get("data", []):
                        p = item.get("citedPaper", {})
                        if pid := p.get("paperId"):
                            neighbour_batches.append((pid, "cites"))
                            nodes.setdefault(pid, {
                                "id": pid, "title": p.get("title"),
                                "year": p.get("year"),
                                "citationCount": p.get("citationCount"),
                            })
                            edges.append({"source": paper_id, "target": pid, "direction": "cites"})
                except httpx.HTTPStatusError:
                    pass

            for neighbour_id, _ in neighbour_batches:
                if len(nodes) >= max_nodes:
                    truncated = True
                    break
                if neighbour_id not in visited:
                    visited.add(neighbour_id)
                    queue.append((neighbour_id, current_depth + 1))

            if truncated:
                break

        # Trim nodes to max_nodes
        node_list = list(nodes.values())[:max_nodes]
        node_ids = {n["id"] for n in node_list}
        edge_list = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]

        return json.dumps({
            "nodes": node_list,
            "edges": edge_list,
            "stats": {
                "total_nodes": len(node_list),
                "total_edges": len(edge_list),
                "depth_reached": depth,
                "truncated": truncated,
            },
        })

    @mcp.tool()
    async def find_bridge_papers(
        source_id: str,
        target_id: str,
        max_depth: int = 4,
        direction: Literal["citations", "references", "both"] = "both",
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Find the shortest citation path between two papers.

        Uses BFS over the citation/reference graph. Leverages cached
        citation and reference lists to minimise API calls.

        Args:
            source_id: Starting paper S2 ID.
            target_id: Target paper S2 ID.
            max_depth: Maximum hops to search (default 4).
            direction: Expand via citations, references, or both.

        Returns:
            JSON ``{"found": true, "path": [...]}`` or ``{"found": false}``.
        """
        # BFS: queue holds (paper_id, path_so_far)
        queue: deque[tuple[str, list[str]]] = deque([(source_id, [source_id])])
        visited: set[str] = {source_id}

        async def _get_neighbours(paper_id: str) -> list[str]:
            neighbours: list[str] = []
            if direction in ("references", "both"):
                cached = await bundle.cache.get_references(paper_id)
                if cached is None:
                    try:
                        result = await bundle.s2.get_references(
                            paper_id, fields="paperId", limit=100, offset=0
                        )
                        cached = [
                            item["citedPaper"]["paperId"]
                            for item in result.get("data", [])
                            if item.get("citedPaper", {}).get("paperId")
                        ]
                        await bundle.cache.set_references(paper_id, cached)
                    except httpx.HTTPStatusError:
                        cached = []
                neighbours.extend(cached)
            if direction in ("citations", "both"):
                cached_cit = await bundle.cache.get_citations(paper_id)
                if cached_cit is None:
                    try:
                        result = await bundle.s2.get_citations(
                            paper_id, fields="paperId", limit=100, offset=0
                        )
                        cached_cit = [
                            item["citingPaper"]["paperId"]
                            for item in result.get("data", [])
                            if item.get("citingPaper", {}).get("paperId")
                        ]
                        await bundle.cache.set_citations(paper_id, cached_cit)
                    except httpx.HTTPStatusError:
                        cached_cit = []
                neighbours.extend(cached_cit)
            return neighbours

        while queue:
            current_id, path = queue.popleft()
            if len(path) > max_depth + 1:
                continue

            neighbours = await _get_neighbours(current_id)
            for neighbour_id in neighbours:
                if neighbour_id == target_id:
                    # Found — fetch compact records for the path
                    full_path = path + [target_id]
                    path_records = []
                    for pid in full_path:
                        cached = await bundle.cache.get_paper(pid)
                        if cached:
                            path_records.append(cached)
                        else:
                            path_records.append({"paperId": pid})
                    return json.dumps({"found": True, "path": path_records})
                if neighbour_id not in visited:
                    visited.add(neighbour_id)
                    queue.append((neighbour_id, path + [neighbour_id]))

        return json.dumps({"found": False})
```

- [ ] **Step 4: Run all graph tests**

```bash
uv run pytest tests/test_tools_graph.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit and close issues**

```bash
git add src/scholar_mcp/_tools_graph.py tests/test_tools_graph.py
git commit -m "feat: implement get_citation_graph and find_bridge_papers"
gh issue close <get_citation_graph issue number> --comment "Implemented in _tools_graph.py"
gh issue close <find_bridge_papers issue number> --comment "Implemented in _tools_graph.py"
```

---

### Task 10: Implement recommend_papers (v0.3.0)

**Files:**
- Create: `src/scholar_mcp/_tools_recommendations.py`
- Create: `tests/test_tools_recommendations.py`
- Modify: `src/scholar_mcp/_server_tools.py`

Closes issue: "Implement recommend_papers tool"

- [ ] **Step 1: Write failing tests**

`tests/test_tools_recommendations.py`:

```python
import json
import pytest
import respx
import httpx
from fastmcp import FastMCP
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_recommendations import register_recommendation_tools

@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    app = FastMCP("test")
    app._lifespan_context = {"bundle": bundle}
    register_recommendation_tools(app)
    return app

async def test_recommend_papers(mcp):
    with respx.mock:
        respx.post("https://api.semanticscholar.org/recommendations/v1/papers").mock(
            return_value=httpx.Response(200, json={
                "recommendedPapers": [
                    {"paperId": "r1", "title": "Recommended 1", "year": 2023, "citationCount": 10}
                ]
            })
        )
        async with mcp.test_client() as client:
            result = await client.call_tool("recommend_papers", {
                "positive_ids": ["p1", "p2"],
            })
    data = json.loads(result[0].text)
    assert len(data) == 1
    assert data[0]["paperId"] == "r1"

async def test_recommend_papers_with_negatives(mcp):
    with respx.mock:
        respx.post("https://api.semanticscholar.org/recommendations/v1/papers").mock(
            return_value=httpx.Response(200, json={"recommendedPapers": []})
        )
        async with mcp.test_client() as client:
            result = await client.call_tool("recommend_papers", {
                "positive_ids": ["p1"],
                "negative_ids": ["n1"],
                "limit": 5,
            })
    data = json.loads(result[0].text)
    assert isinstance(data, list)
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_tools_recommendations.py -v
```

- [ ] **Step 3: Implement**

`src/scholar_mcp/_tools_recommendations.py`:

```python
"""Recommendations MCP tool."""

from __future__ import annotations

import json
import logging
from typing import Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._server_deps import ServiceBundle, get_bundle
from ._s2_client import FIELD_SETS

logger = logging.getLogger(__name__)


def register_recommendation_tools(mcp: FastMCP) -> None:
    """Register recommendation tools on *mcp*."""

    @mcp.tool()
    async def recommend_papers(
        positive_ids: list[str],
        negative_ids: list[str] | None = None,
        limit: int = 10,
        fields: Literal["compact", "standard", "full"] = "standard",
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Recommend papers based on positive (and optionally negative) examples.

        Args:
            positive_ids: 1–5 S2 paper IDs to use as positive examples.
            negative_ids: Optional S2 paper IDs to steer away from.
            limit: Number of recommendations to return.
            fields: Field set preset for returned records.

        Returns:
            JSON list of recommended paper records.
        """
        try:
            result = await bundle.s2.recommend(
                positive_ids[:5],
                negative_ids=negative_ids,
                limit=limit,
                fields=FIELD_SETS[fields],
            )
        except httpx.HTTPStatusError as exc:
            return json.dumps({
                "error": "upstream_error",
                "status": exc.response.status_code,
                "detail": exc.response.text[:200],
            })
        return json.dumps(result)
```

- [ ] **Step 4: Enable in `_server_tools.py`**

Add to `register_tools`:

```python
    from ._tools_recommendations import register_recommendation_tools
    register_recommendation_tools(mcp)
```

- [ ] **Step 5: Run tests and commit**

```bash
uv run pytest tests/test_tools_recommendations.py -v
git add src/scholar_mcp/_tools_recommendations.py tests/test_tools_recommendations.py \
        src/scholar_mcp/_server_tools.py
git commit -m "feat: implement recommend_papers tool"
gh issue close <recommend_papers issue number> --comment "Implemented in _tools_recommendations.py"
```

---

### Task 11: Implement OpenAlex client and utility tools (v0.3.0)

**Files:**
- Create: `src/scholar_mcp/_openalex_client.py`
- Create: `tests/test_openalex_client.py`
- Create: `src/scholar_mcp/_tools_utility.py`
- Create: `tests/test_tools_utility.py`
- Modify: `src/scholar_mcp/_server_tools.py`

Closes issues: "Implement OpenAlex client", "Implement batch_resolve tool", "Implement enrich_paper tool"

- [ ] **Step 1: Write failing OpenAlex client tests**

`tests/test_openalex_client.py`:

```python
import pytest
import respx
import httpx
from scholar_mcp._openalex_client import OpenAlexClient

OA_BASE = "https://api.openalex.org"

@pytest.fixture
def client():
    return OpenAlexClient(http_client=httpx.AsyncClient(base_url=OA_BASE))

@pytest.mark.respx(base_url=OA_BASE)
async def test_get_by_doi(respx_mock, client):
    doi = "10.1234/test"
    respx_mock.get(f"/works/https://doi.org/{doi}").mock(return_value=httpx.Response(200, json={
        "id": "https://openalex.org/W1",
        "doi": f"https://doi.org/{doi}",
        "authorships": [{"author": {"display_name": "Ada"}, "institutions": [{"display_name": "MIT"}]}],
        "grants": [],
        "open_access": {"is_oa": True, "oa_status": "gold"},
        "concepts": [{"display_name": "Machine Learning", "score": 0.9}],
    }))
    result = await client.get_by_doi(doi)
    assert result["open_access"]["is_oa"] is True

@pytest.mark.respx(base_url=OA_BASE)
async def test_get_by_doi_not_found(respx_mock, client):
    respx_mock.get("/works/https://doi.org/10.0/missing").mock(
        return_value=httpx.Response(404)
    )
    result = await client.get_by_doi("10.0/missing")
    assert result is None
```

- [ ] **Step 2: Implement `_openalex_client.py`**

```python
"""OpenAlex API client for metadata enrichment."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class OpenAlexClient:
    """Thin async client for the OpenAlex API.

    Args:
        http_client: Pre-configured httpx.AsyncClient pointed at OpenAlex.
    """

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client

    async def get_by_doi(self, doi: str) -> dict | None:
        """Fetch OpenAlex work metadata by DOI.

        Args:
            doi: DOI string (without ``https://doi.org/`` prefix).

        Returns:
            OpenAlex work dict or None if not found.
        """
        url = f"/works/https://doi.org/{doi}"
        try:
            r = await self._client.get(url)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning("openalex_error doi=%s status=%s", doi, r.status_code)
            return None
```

- [ ] **Step 3: Update `_server_deps.py` to expose OpenAlexClient properly**

In `_server_deps.py`, import and use `OpenAlexClient`:

```python
from ._openalex_client import OpenAlexClient

# In ServiceBundle, change openalex type:
@dataclass
class ServiceBundle:
    s2: S2Client
    openalex: OpenAlexClient   # ← was httpx.AsyncClient
    docling: httpx.AsyncClient | None
    cache: ScholarCache
    config: ServerConfig

# In make_service_lifespan, replace:
openalex_http = httpx.AsyncClient(
    base_url=_OPENALEX_BASE,
    headers={"User-Agent": "scholar-mcp/0.1 (mailto:scholar-mcp@pvliesdonk.nl)"},
    timeout=30.0,
)
openalex = OpenAlexClient(openalex_http)

# And in the finally block:
await openalex_http.aclose()
```

Update `conftest.py` accordingly:

```python
from scholar_mcp._openalex_client import OpenAlexClient

# In bundle fixture:
openalex_http = httpx.AsyncClient(base_url="https://api.openalex.org")
openalex = OpenAlexClient(openalex_http)
return ServiceBundle(s2=s2, openalex=openalex, docling=None, cache=cache, config=test_config)
```

- [ ] **Step 4: Write failing utility tool tests**

`tests/test_tools_utility.py`:

```python
import json
import pytest
import respx
import httpx
from fastmcp import FastMCP
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_utility import register_utility_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"
OA_BASE = "https://api.openalex.org"

@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    app = FastMCP("test")
    app._lifespan_context = {"bundle": bundle}
    register_utility_tools(app)
    return app

async def test_batch_resolve_all_found(mcp):
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(return_value=httpx.Response(200, json=[
            {"paperId": "p1", "title": "Paper 1"},
            {"paperId": "p2", "title": "Paper 2"},
        ]))
        async with mcp.test_client() as client:
            result = await client.call_tool("batch_resolve", {
                "identifiers": ["p1", "p2"],
            })
    data = json.loads(result[0].text)
    assert len(data) == 2
    assert data[0]["paper"]["paperId"] == "p1"

async def test_batch_resolve_openalex_fallback(mcp):
    with respx.mock:
        # S2 returns None for the second item
        respx.post(f"{S2_BASE}/paper/batch").mock(return_value=httpx.Response(200, json=[
            None,
        ]))
        # OpenAlex resolves it
        respx.get(f"{OA_BASE}/works/https://doi.org/10.1/test").mock(
            return_value=httpx.Response(200, json={
                "id": "W1", "doi": "https://doi.org/10.1/test",
                "title": "Found via OpenAlex",
            })
        )
        async with mcp.test_client() as client:
            result = await client.call_tool("batch_resolve", {
                "identifiers": ["DOI:10.1/test"],
            })
    data = json.loads(result[0].text)
    assert data[0].get("source") == "openalex"

async def test_enrich_paper(mcp):
    with respx.mock:
        # First get the DOI from S2
        respx.get(f"{S2_BASE}/paper/p1").mock(return_value=httpx.Response(200, json={
            "paperId": "p1", "externalIds": {"DOI": "10.1/test"}
        }))
        respx.get(f"{OA_BASE}/works/https://doi.org/10.1/test").mock(
            return_value=httpx.Response(200, json={
                "open_access": {"is_oa": True, "oa_status": "gold"},
                "grants": [{"funder_display_name": "NSF"}],
                "authorships": [],
                "concepts": [],
            })
        )
        async with mcp.test_client() as client:
            result = await client.call_tool("enrich_paper", {
                "identifier": "p1",
                "fields": ["oa_status", "funders"],
            })
    data = json.loads(result[0].text)
    assert data["oa_status"] == "gold"
    assert data["funders"][0] == "NSF"
```

- [ ] **Step 5: Implement `_tools_utility.py`**

`src/scholar_mcp/_tools_utility.py`:

```python
"""Utility MCP tools: batch_resolve and enrich_paper."""

from __future__ import annotations

import json
import logging
from typing import Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._server_deps import ServiceBundle, get_bundle
from ._s2_client import FIELD_SETS

logger = logging.getLogger(__name__)


def register_utility_tools(mcp: FastMCP) -> None:
    """Register utility tools on *mcp*."""

    @mcp.tool()
    async def batch_resolve(
        identifiers: list[str],
        fields: Literal["compact", "standard", "full"] = "standard",
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Resolve a list of paper identifiers to full records.

        Uses the S2 batch endpoint for IDs/DOIs. Falls back to OpenAlex by DOI
        for papers that S2 cannot resolve. Title-based identifiers are not
        supported by the batch endpoint and are flagged as unresolved.

        Args:
            identifiers: List of S2 IDs, DOIs (prefixed ``DOI:``), or plain DOIs.
            fields: Field set preset.

        Returns:
            JSON list of ``{"identifier": ..., "paper": {...}}`` for resolved,
            ``{"identifier": ..., "error": "not_found"}`` for unresolved,
            ``{"identifier": ..., "paper": {...}, "source": "openalex"}`` for
            OpenAlex fallbacks.
        """
        results: list[dict] = []
        batch_ids: list[str] = []
        doi_map: dict[int, str] = {}  # batch index → raw DOI for OA fallback

        for i, raw in enumerate(identifiers):
            if raw.startswith("DOI:"):
                doi = raw[4:]
                batch_ids.append(raw)
                doi_map[i] = doi
            else:
                batch_ids.append(raw)

        try:
            s2_results = await bundle.s2.batch_resolve(batch_ids, fields=FIELD_SETS[fields])
        except httpx.HTTPStatusError as exc:
            return json.dumps({
                "error": "upstream_error",
                "status": exc.response.status_code,
            })

        for i, (raw, s2_data) in enumerate(zip(identifiers, s2_results)):
            if s2_data is not None:
                results.append({"identifier": raw, "paper": s2_data})
            elif i in doi_map:
                # Try OpenAlex fallback for DOIs S2 missed
                oa = await bundle.openalex.get_by_doi(doi_map[i])
                if oa:
                    results.append({"identifier": raw, "paper": oa, "source": "openalex"})
                else:
                    results.append({"identifier": raw, "error": "not_found"})
            else:
                results.append({"identifier": raw, "error": "not_found"})

        return json.dumps(results)

    @mcp.tool()
    async def enrich_paper(
        identifier: str,
        fields: list[Literal["affiliations", "funders", "oa_status", "concepts"]],
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Fetch OpenAlex metadata to supplement Semantic Scholar data.

        Resolves the paper's DOI from S2, then queries OpenAlex for the
        requested enrichment fields. Results are cached for 30 days.

        Args:
            identifier: S2 paper ID or DOI (prefix ``DOI:``).
            fields: One or more of: affiliations, funders, oa_status, concepts.

        Returns:
            JSON dict with requested fields plus ``paper_id`` and ``doi``.
        """
        # Resolve DOI from S2
        doi: str | None = None
        if identifier.startswith("DOI:"):
            doi = identifier[4:]
        else:
            try:
                paper = await bundle.s2.get_paper(identifier, fields="externalIds,paperId")
                doi = (paper.get("externalIds") or {}).get("DOI")
            except httpx.HTTPStatusError:
                return json.dumps({"error": "not_found", "identifier": identifier})

        if not doi:
            return json.dumps({"error": "no_doi", "identifier": identifier})

        # Check cache
        cached = await bundle.cache.get_openalex(doi)
        oa_data = cached
        if oa_data is None:
            oa_data = await bundle.openalex.get_by_doi(doi)
            if oa_data is None:
                return json.dumps({"error": "not_found_in_openalex", "doi": doi})
            await bundle.cache.set_openalex(doi, oa_data)

        result: dict = {"doi": doi}

        if "affiliations" in fields:
            result["affiliations"] = [
                inst["display_name"]
                for authorship in oa_data.get("authorships", [])
                for inst in authorship.get("institutions", [])
            ]

        if "funders" in fields:
            result["funders"] = [
                g.get("funder_display_name") for g in oa_data.get("grants", [])
            ]

        if "oa_status" in fields:
            oa_info = oa_data.get("open_access", {})
            result["oa_status"] = oa_info.get("oa_status")
            result["is_oa"] = oa_info.get("is_oa")

        if "concepts" in fields:
            result["concepts"] = [
                {"name": c.get("display_name"), "score": c.get("score")}
                for c in oa_data.get("concepts", [])
            ]

        return json.dumps(result)
```

- [ ] **Step 6: Enable in `_server_tools.py`**

```python
    from ._tools_utility import register_utility_tools
    register_utility_tools(mcp)
```

- [ ] **Step 7: Run tests and commit**

```bash
uv run pytest tests/test_openalex_client.py tests/test_tools_utility.py -v
uv run pytest  # full suite
git add src/scholar_mcp/_openalex_client.py src/scholar_mcp/_tools_utility.py \
        tests/test_openalex_client.py tests/test_tools_utility.py \
        src/scholar_mcp/_server_deps.py tests/conftest.py \
        src/scholar_mcp/_server_tools.py
git commit -m "feat: implement OpenAlex client, batch_resolve, and enrich_paper"
gh issue close <openalex issue number> --comment "Implemented in _openalex_client.py"
gh issue close <batch_resolve issue number> --comment "Implemented in _tools_utility.py"
gh issue close <enrich_paper issue number> --comment "Implemented in _tools_utility.py"
```

---

### Task 12: Implement docling client and PDF tools (v0.4.0)

**Files:**
- Create: `src/scholar_mcp/_docling_client.py`
- Create: `src/scholar_mcp/_tools_pdf.py`
- Create: `tests/test_docling_client.py`
- Create: `tests/test_tools_pdf.py`
- Modify: `src/scholar_mcp/_server_tools.py`

Closes issues: "Implement docling-serve client", "Implement fetch_paper_pdf",
"Implement convert_pdf_to_markdown and fetch_and_convert"

Reference implementation for the docling-serve API:
`/mnt/docker-volumes/compose.git/40-documents/paperless-docling-md/convert.py`

- [ ] **Step 1: Write failing docling client tests**

`tests/test_docling_client.py`:

```python
import pytest
import respx
import httpx
from scholar_mcp._docling_client import DoclingClient

DOCLING_BASE = "http://docling:5001"

@pytest.fixture
def client():
    return DoclingClient(
        http_client=httpx.AsyncClient(base_url=DOCLING_BASE, timeout=30.0),
        vlm_api_url=None, vlm_api_key=None, vlm_model="gpt-4o",
    )

@pytest.mark.respx(base_url=DOCLING_BASE)
async def test_standard_convert(respx_mock, client):
    task_id = "task-001"
    respx_mock.post("/v1/convert/file/async").mock(return_value=httpx.Response(
        200, json={"task_id": task_id}
    ))
    respx_mock.get(f"/v1/status/poll/{task_id}").mock(return_value=httpx.Response(
        200, json={"task_status": "success"}
    ))
    respx_mock.get(f"/v1/result/{task_id}").mock(return_value=httpx.Response(
        200, json={"document": {"md_content": "# Paper Title\n\nContent here."}}
    ))
    result = await client.convert(b"%PDF-1.4 fake", "paper.pdf", use_vlm=False)
    assert result == "# Paper Title\n\nContent here."

@pytest.mark.respx(base_url=DOCLING_BASE)
async def test_convert_polls_until_success(respx_mock, client):
    task_id = "task-002"
    respx_mock.post("/v1/convert/file/async").mock(return_value=httpx.Response(
        200, json={"task_id": task_id}
    ))
    call_count = 0
    def _status_side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(200, json={"task_status": "pending"})
        return httpx.Response(200, json={"task_status": "success"})
    respx_mock.get(f"/v1/status/poll/{task_id}").mock(side_effect=_status_side_effect)
    respx_mock.get(f"/v1/result/{task_id}").mock(return_value=httpx.Response(
        200, json={"document": {"md_content": "# Done"}}
    ))
    result = await client.convert(b"pdf", "test.pdf", use_vlm=False, poll_interval=0.01)
    assert result == "# Done"
    assert call_count == 3

@pytest.mark.respx(base_url=DOCLING_BASE)
async def test_convert_task_failure(respx_mock, client):
    task_id = "task-003"
    respx_mock.post("/v1/convert/file/async").mock(return_value=httpx.Response(
        200, json={"task_id": task_id}
    ))
    respx_mock.get(f"/v1/status/poll/{task_id}").mock(return_value=httpx.Response(
        200, json={"task_status": "failure", "error_message": "Bad PDF"}
    ))
    with pytest.raises(RuntimeError, match="failed"):
        await client.convert(b"bad", "bad.pdf", use_vlm=False)
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_docling_client.py -v
```

- [ ] **Step 3: Implement `_docling_client.py`**

The VLM payload structure is taken directly from
`/mnt/docker-volumes/compose.git/40-documents/paperless-docling-md/convert.py`
— the `docling_convert_vlm` function.

```python
"""docling-serve client for PDF-to-Markdown conversion."""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_FORMULA_PROMPT = (
    "Extract the mathematical formula from this image. "
    "Output ONLY the LaTeX expression, nothing else. "
    "Use display math format. Include the equation number in \\tag{} if visible."
)

_PICTURE_PROMPT = (
    "Describe this figure from an academic paper. Include: "
    "axis labels and units, all data series with labels, key trends and intersections, "
    "and the figure caption if visible. Use LaTeX ($...$) for mathematical notation. "
    "Be precise and concise."
)


@dataclass
class DoclingClient:
    """Client for docling-serve async conversion API.

    Args:
        http_client: httpx.AsyncClient pointed at docling-serve.
        vlm_api_url: OpenAI-compatible VLM endpoint URL, or None.
        vlm_api_key: API key for the VLM endpoint.
        vlm_model: Model name for VLM enrichment.
    """

    http_client: httpx.AsyncClient
    vlm_api_url: str | None
    vlm_api_key: str | None
    vlm_model: str

    @property
    def vlm_available(self) -> bool:
        """True if VLM enrichment is configured."""
        return bool(self.vlm_api_url and self.vlm_api_key)

    async def _poll(self, task_id: str, poll_interval: float = 3.0) -> str:
        """Poll task until complete, then fetch and return markdown.

        Args:
            task_id: Task ID returned by the async submit endpoint.
            poll_interval: Seconds between status polls.

        Returns:
            Markdown string.

        Raises:
            RuntimeError: If task fails or no markdown is returned.
        """
        while True:
            await asyncio.sleep(poll_interval)
            r = await self.http_client.get(f"/v1/status/poll/{task_id}", timeout=30)
            r.raise_for_status()
            status_data = r.json()
            status = status_data.get("task_status") or status_data.get("status", "")

            if status.lower() in ("failure", "error"):
                raise RuntimeError(
                    f"docling task {task_id} failed: {status_data.get('error_message', status_data)}"
                )

            if status.lower() == "success":
                result_r = await self.http_client.get(f"/v1/result/{task_id}", timeout=30)
                result_r.raise_for_status()
                result = result_r.json()
                doc = result.get("document") or {}
                md = (
                    doc.get("md_content")
                    or doc.get("markdown")
                    or result.get("md_content")
                    or ""
                )
                if not md:
                    raise RuntimeError(f"docling task {task_id} returned no markdown")
                return md

            logger.debug("docling_polling task_id=%s status=%s", task_id, status)

    async def convert(
        self,
        pdf_bytes: bytes,
        filename: str,
        *,
        use_vlm: bool = False,
        poll_interval: float = 3.0,
    ) -> str:
        """Convert a PDF to Markdown using docling-serve.

        Chooses the VLM-enhanced path if ``use_vlm=True`` and VLM is
        configured; otherwise falls back to the standard path automatically.

        Args:
            pdf_bytes: Raw PDF bytes.
            filename: Filename hint for docling.
            use_vlm: Request VLM enrichment for formulas and figures.
            poll_interval: Seconds between status poll requests.

        Returns:
            Markdown string.
        """
        if use_vlm and self.vlm_available:
            return await self._convert_vlm(pdf_bytes, filename, poll_interval)
        return await self._convert_standard(pdf_bytes, filename, poll_interval)

    async def _convert_standard(
        self, pdf_bytes: bytes, filename: str, poll_interval: float
    ) -> str:
        r = await self.http_client.post(
            "/v1/convert/file/async",
            files={"files": (filename, pdf_bytes, "application/pdf")},
            data={"to_formats": "md", "do_ocr": "true", "image_export_mode": "placeholder"},
            timeout=60,
        )
        r.raise_for_status()
        task_id = r.json().get("task_id") or r.json().get("id")
        if not task_id:
            raise RuntimeError(f"docling did not return task_id: {r.text[:200]}")
        return await self._poll(task_id, poll_interval)

    async def _convert_vlm(
        self, pdf_bytes: bytes, filename: str, poll_interval: float
    ) -> str:
        b64 = base64.b64encode(pdf_bytes).decode("ascii")
        payload = {
            "options": {
                "to_formats": ["md"],
                "pipeline": "standard",
                "do_ocr": True,
                "image_export_mode": "placeholder",
                "pdf_backend": "dlparse_v4",
                "do_formula_enrichment": True,
                "do_code_enrichment": True,
                "code_formula_custom_config": {
                    "engine_options": {
                        "engine_type": "api_openai",
                        "url": f"{self.vlm_api_url}/chat/completions",
                        "headers": {"Authorization": f"Bearer {self.vlm_api_key}"},
                        "params": {"model": self.vlm_model, "max_tokens": 1024},
                        "timeout": 120,
                        "concurrency": 2,
                    },
                    "model_spec": {
                        "name": f"{self.vlm_model}-formula",
                        "default_repo_id": self.vlm_model,
                        "prompt": _FORMULA_PROMPT,
                        "response_format": "markdown",
                        "max_new_tokens": 1024,
                    },
                    "scale": 2.0,
                    "extract_code": True,
                    "extract_formulas": True,
                },
                "do_picture_description": True,
                "do_picture_classification": True,
                "picture_description_custom_config": {
                    "engine_options": {
                        "engine_type": "api_openai",
                        "url": f"{self.vlm_api_url}/chat/completions",
                        "headers": {"Authorization": f"Bearer {self.vlm_api_key}"},
                        "params": {"model": self.vlm_model, "max_tokens": 512},
                        "timeout": 120,
                        "concurrency": 2,
                    },
                    "model_spec": {
                        "name": f"{self.vlm_model}-figures",
                        "default_repo_id": self.vlm_model,
                        "prompt": _PICTURE_PROMPT,
                        "response_format": "markdown",
                        "max_new_tokens": 512,
                    },
                    "scale": 2.0,
                    "batch_size": 1,
                    "prompt": _PICTURE_PROMPT,
                    "generation_config": {"max_new_tokens": 512, "do_sample": False},
                },
            },
            "sources": [{"kind": "file", "base64_string": b64, "filename": filename}],
        }
        r = await self.http_client.post("/v1/convert/source/async", json=payload, timeout=60)
        r.raise_for_status()
        task_id = r.json().get("task_id") or r.json().get("id")
        if not task_id:
            raise RuntimeError(f"docling VLM did not return task_id: {r.text[:200]}")
        md = await self._poll(task_id, poll_interval)
        # Decode common HTML entities that docling VLM output may contain
        return md.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
```

- [ ] **Step 4: Update `_server_deps.py` to use DoclingClient**

```python
from ._docling_client import DoclingClient

# In ServiceBundle:
@dataclass
class ServiceBundle:
    s2: S2Client
    openalex: OpenAlexClient
    docling: DoclingClient | None   # ← typed properly now
    cache: ScholarCache
    config: ServerConfig

# In make_service_lifespan, replace the docling block:
docling: DoclingClient | None = None
if config.docling_url:
    docling_http = httpx.AsyncClient(base_url=config.docling_url, timeout=300.0)
    docling = DoclingClient(
        http_client=docling_http,
        vlm_api_url=config.vlm_api_url,
        vlm_api_key=config.vlm_api_key,
        vlm_model=config.vlm_model,
    )

# In finally, close docling_http (keep reference):
if docling:
    await docling.http_client.aclose()
```

- [ ] **Step 5: Write failing PDF tool tests**

`tests/test_tools_pdf.py`:

```python
import json
import pytest
import respx
import httpx
from pathlib import Path
from fastmcp import FastMCP
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._docling_client import DoclingClient
from scholar_mcp._tools_pdf import register_pdf_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"
DOCLING_BASE = "http://docling:5001"

@pytest.fixture
def bundle_with_docling(bundle: ServiceBundle, tmp_path: Path) -> ServiceBundle:
    docling_http = httpx.AsyncClient(base_url=DOCLING_BASE, timeout=30.0)
    bundle.docling = DoclingClient(
        http_client=docling_http, vlm_api_url=None, vlm_api_key=None, vlm_model="gpt-4o"
    )
    return bundle

@pytest.fixture
def mcp_no_docling(bundle: ServiceBundle) -> FastMCP:
    app = FastMCP("test")
    app._lifespan_context = {"bundle": bundle}
    register_pdf_tools(app)
    return app

@pytest.fixture
def mcp_with_docling(bundle_with_docling: ServiceBundle) -> FastMCP:
    app = FastMCP("test")
    app._lifespan_context = {"bundle": bundle_with_docling}
    register_pdf_tools(app)
    return app

@pytest.mark.respx(base_url=S2_BASE)
async def test_fetch_paper_pdf_no_oa(respx_mock, mcp_no_docling):
    respx_mock.get("/paper/p1").mock(return_value=httpx.Response(200, json={
        "paperId": "p1", "openAccessPdf": None
    }))
    async with mcp_no_docling.test_client() as client:
        result = await client.call_tool("fetch_paper_pdf", {"identifier": "p1"})
    data = json.loads(result[0].text)
    assert data["error"] == "no_oa_pdf"

async def test_convert_no_docling(mcp_no_docling, tmp_path):
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF fake")
    async with mcp_no_docling.test_client() as client:
        result = await client.call_tool("convert_pdf_to_markdown", {
            "file_path": str(pdf)
        })
    data = json.loads(result[0].text)
    assert data["error"] == "docling_not_configured"

@pytest.mark.respx(base_url=DOCLING_BASE)
async def test_convert_standard(respx_mock, mcp_with_docling, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF fake")
    respx_mock.post("/v1/convert/file/async").mock(return_value=httpx.Response(
        200, json={"task_id": "t1"}
    ))
    respx_mock.get("/v1/status/poll/t1").mock(return_value=httpx.Response(
        200, json={"task_status": "success"}
    ))
    respx_mock.get("/v1/result/t1").mock(return_value=httpx.Response(
        200, json={"document": {"md_content": "# Paper\n\nText."}}
    ))
    async with mcp_with_docling.test_client() as client:
        result = await client.call_tool("convert_pdf_to_markdown", {
            "file_path": str(pdf)
        })
    data = json.loads(result[0].text)
    assert "# Paper" in data["markdown"]
    assert data["vlm_used"] is False
```

- [ ] **Step 6: Implement `_tools_pdf.py`**

```python
"""PDF download and conversion MCP tools."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)


def register_pdf_tools(mcp: FastMCP) -> None:
    """Register PDF tools on *mcp*."""

    @mcp.tool(tags={"write"})
    async def fetch_paper_pdf(
        identifier: str,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Download the open-access PDF of a paper.

        Only works for papers with an open-access PDF URL in Semantic Scholar.
        Skips download if the file already exists locally.

        Args:
            identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).

        Returns:
            JSON ``{"path": "..."}`` on success, or a structured error.
        """
        try:
            paper = await bundle.s2.get_paper(identifier, fields="paperId,openAccessPdf,title")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return json.dumps({"error": "not_found", "identifier": identifier})
            return json.dumps({"error": "upstream_error", "status": exc.response.status_code})

        oa_pdf = paper.get("openAccessPdf") or {}
        url = oa_pdf.get("url")
        if not url:
            return json.dumps({
                "error": "no_oa_pdf",
                "paper_id": paper.get("paperId"),
                "title": paper.get("title"),
            })

        paper_id = paper.get("paperId", identifier.replace("/", "_"))
        pdf_dir = bundle.config.cache_dir / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"{paper_id}.pdf"

        if pdf_path.exists():
            logger.info("pdf_already_exists path=%s", pdf_path)
            return json.dumps({"path": str(pdf_path)})

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                r = await client.get(url, follow_redirects=True)
                r.raise_for_status()
            except httpx.HTTPError as exc:
                return json.dumps({"error": "download_failed", "detail": str(exc)})

        pdf_path.write_bytes(r.content)
        logger.info("pdf_downloaded path=%s bytes=%d", pdf_path, len(r.content))
        return json.dumps({"path": str(pdf_path)})

    @mcp.tool()
    async def convert_pdf_to_markdown(
        file_path: str,
        use_vlm: bool = False,
        include_references: bool = True,
        include_figures: bool = False,
        table_format: Literal["markdown", "html"] = "markdown",
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Convert a local PDF to Markdown using docling-serve.

        Works on any local PDF, including manually placed paywalled papers.
        Requires ``SCHOLAR_MCP_DOCLING_URL`` to be configured.

        Args:
            file_path: Absolute path to the local PDF file.
            use_vlm: Use VLM enrichment for formulas and figures (requires
                ``SCHOLAR_MCP_VLM_API_URL`` and ``SCHOLAR_MCP_VLM_API_KEY``).
                Falls back to standard path if VLM is not configured.
            include_references: Include references section (ignored — docling
                includes all content by default; reserved for future filtering).
            include_figures: Include figure placeholders (currently always
                included as placeholders).
            table_format: Not yet used by docling-serve; reserved.

        Returns:
            JSON ``{"markdown": "...", "path": "...", "vlm_used": bool}``.
        """
        if bundle.docling is None:
            return json.dumps({"error": "docling_not_configured"})

        path = Path(file_path)
        if not path.exists():
            return json.dumps({"error": "file_not_found", "path": file_path})

        pdf_bytes = path.read_bytes()
        vlm_used = use_vlm and bundle.docling.vlm_available

        try:
            markdown = await bundle.docling.convert(
                pdf_bytes, path.name, use_vlm=use_vlm
            )
        except Exception as exc:
            logger.exception("docling_convert_failed path=%s", file_path)
            return json.dumps({"error": "docling_error", "detail": str(exc)})

        md_dir = bundle.config.cache_dir / "md"
        md_dir.mkdir(parents=True, exist_ok=True)
        md_path = md_dir / f"{path.stem}.md"
        md_path.write_text(markdown, encoding="utf-8")

        return json.dumps({
            "markdown": markdown,
            "path": str(md_path),
            "vlm_used": vlm_used,
        })

    @mcp.tool()
    async def fetch_and_convert(
        identifier: str,
        use_vlm: bool = False,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Resolve a paper, download its OA PDF, and convert to Markdown.

        Each stage fails gracefully: metadata is always returned if the paper
        resolves, even if PDF download or conversion fails.

        Args:
            identifier: Paper identifier (DOI, S2 ID, ARXIV:, etc.).
            use_vlm: Use VLM enrichment for formula/figure extraction.

        Returns:
            JSON with ``metadata`` and ``markdown`` on full success,
            or ``metadata`` plus an ``error`` key if a stage fails.
        """
        try:
            paper = await bundle.s2.get_paper(identifier)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return json.dumps({"error": "not_found", "identifier": identifier})
            return json.dumps({"error": "upstream_error", "status": exc.response.status_code})

        oa_pdf = paper.get("openAccessPdf") or {}
        url = oa_pdf.get("url")
        if not url:
            return json.dumps({
                "metadata": paper,
                "error": "no_oa_pdf",
            })

        paper_id = paper.get("paperId", identifier.replace("/", "_"))
        pdf_dir = bundle.config.cache_dir / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"{paper_id}.pdf"

        if not pdf_path.exists():
            async with httpx.AsyncClient(timeout=120.0) as client:
                try:
                    r = await client.get(url, follow_redirects=True)
                    r.raise_for_status()
                    pdf_path.write_bytes(r.content)
                except httpx.HTTPError as exc:
                    return json.dumps({"metadata": paper, "error": "download_failed", "detail": str(exc)})

        if bundle.docling is None:
            return json.dumps({
                "metadata": paper,
                "pdf_path": str(pdf_path),
                "error": "docling_not_configured",
            })

        try:
            markdown = await bundle.docling.convert(
                pdf_path.read_bytes(), pdf_path.name, use_vlm=use_vlm
            )
        except Exception as exc:
            return json.dumps({
                "metadata": paper,
                "pdf_path": str(pdf_path),
                "error": "conversion_failed",
                "detail": str(exc),
            })

        md_dir = bundle.config.cache_dir / "md"
        md_dir.mkdir(parents=True, exist_ok=True)
        md_path = md_dir / f"{paper_id}.md"
        md_path.write_text(markdown, encoding="utf-8")

        return json.dumps({
            "metadata": paper,
            "markdown": markdown,
            "pdf_path": str(pdf_path),
            "md_path": str(md_path),
            "vlm_used": use_vlm and bundle.docling.vlm_available,
        })
```

- [ ] **Step 7: Enable in `_server_tools.py`**

```python
    from ._tools_pdf import register_pdf_tools
    register_pdf_tools(mcp)
```

- [ ] **Step 8: Run all tests**

```bash
uv run pytest tests/test_docling_client.py tests/test_tools_pdf.py -v
uv run pytest  # full suite
```

- [ ] **Step 9: Commit and close issues**

```bash
git add src/scholar_mcp/_docling_client.py src/scholar_mcp/_tools_pdf.py \
        tests/test_docling_client.py tests/test_tools_pdf.py \
        src/scholar_mcp/_server_deps.py src/scholar_mcp/_server_tools.py
git commit -m "feat: implement docling client and PDF tools"
gh issue close <docling_client issue number> --comment "Implemented in _docling_client.py"
gh issue close <fetch_paper_pdf issue number> --comment "Implemented in _tools_pdf.py"
gh issue close <convert_pdf issue number> --comment "Implemented in _tools_pdf.py"
```

---

### Task 13: Add CLI cache commands (v0.1.0)

**Files:**
- Modify: `src/scholar_mcp/cli.py`
- Create: `tests/test_cli.py`

Closes issue: "Add CLI cache management commands"

- [ ] **Step 1: Write failing CLI tests**

`tests/test_cli.py`:

```python
import pytest
from click.testing import CliRunner
from scholar_mcp.cli import main

def test_cache_stats_command():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["cache", "stats"])
    # Without a real DB it should fail gracefully, not crash
    assert result.exit_code in (0, 1)

def test_cache_help():
    runner = CliRunner()
    result = runner.invoke(main, ["cache", "--help"])
    assert result.exit_code == 0
    assert "stats" in result.output
    assert "clear" in result.output
```

- [ ] **Step 2: Implement cache commands in `cli.py`**

Open `src/scholar_mcp/cli.py` and add a `cache` command group. The existing `serve` command stays untouched.

```python
import asyncio
import click

# ... existing imports and serve command ...

@main.group()
def cache() -> None:
    """Manage the Scholar MCP local cache."""


@cache.command("stats")
def cache_stats() -> None:
    """Show cache statistics (row counts, file size)."""
    from .config import load_config
    from ._cache import ScholarCache

    async def _run() -> None:
        config = load_config()
        db_path = config.cache_dir / "cache.db"
        if not db_path.exists():
            click.echo("No cache database found.")
            return
        c = ScholarCache(db_path)
        await c.open()
        stats = await c.stats()
        await c.close()
        for key, val in stats.items():
            click.echo(f"{key}: {val}")

    asyncio.run(_run())


@cache.command("clear")
@click.option("--older-than", "older_than", type=int, default=None,
              help="Only remove entries older than this many days.")
def cache_clear(older_than: int | None) -> None:
    """Clear cache entries.

    Without --older-than, wipes all cached data (preserves id_aliases).
    With --older-than N, removes only entries older than N days.
    """
    from .config import load_config
    from ._cache import ScholarCache

    async def _run() -> None:
        config = load_config()
        db_path = config.cache_dir / "cache.db"
        if not db_path.exists():
            click.echo("No cache database found.")
            return
        c = ScholarCache(db_path)
        await c.open()
        await c.clear(older_than_days=older_than)
        await c.close()
        msg = f"Cache cleared (older than {older_than} days)." if older_than else "Cache cleared."
        click.echo(msg)

    asyncio.run(_run())
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_cli.py -v
uv run pytest  # full suite
```

- [ ] **Step 4: Commit and close issue**

```bash
git add src/scholar_mcp/cli.py tests/test_cli.py
git commit -m "feat: add cache CLI commands (stats, clear)"
gh issue close <cache_cli issue number> --comment "Implemented in cli.py"
```

---

### Task 14: Lint, type-check, and ops documentation (v0.4.0)

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml` (ruff per-file ignores for new modules)

Closes issue: "Ops documentation: Docker compose, env vars, deployment guide"

- [ ] **Step 1: Fix ruff per-file ignores in pyproject.toml**

Add the new modules to the ruff ignore list (same pattern as the template):

```toml
[tool.ruff.lint.per-file-ignores]
"src/scholar_mcp/mcp_server.py" = ["B008", "TCH002"]
"src/scholar_mcp/_server_deps.py" = ["B008", "TCH002"]
"src/scholar_mcp/_server_tools.py" = ["ARG001", "B008", "TCH001", "TCH002"]
"src/scholar_mcp/_server_resources.py" = ["B008", "TCH001", "TCH002"]
"src/scholar_mcp/_server_prompts.py" = ["B008", "TCH002"]
"src/scholar_mcp/_tools_search.py" = ["ARG001", "B008", "TCH001", "TCH002"]
"src/scholar_mcp/_tools_graph.py" = ["ARG001", "B008", "TCH001", "TCH002"]
"src/scholar_mcp/_tools_recommendations.py" = ["ARG001", "B008", "TCH001", "TCH002"]
"src/scholar_mcp/_tools_pdf.py" = ["ARG001", "B008", "TCH001", "TCH002"]
"src/scholar_mcp/_tools_utility.py" = ["ARG001", "B008", "TCH001", "TCH002"]
"tests/*.py" = ["TCH002"]
```

Also update `[tool.ruff.lint.isort]`:

```toml
[tool.ruff.lint.isort]
known-first-party = ["scholar_mcp"]
```

- [ ] **Step 2: Run ruff and fix any issues**

```bash
uv run ruff check src/ tests/ --fix
uv run ruff format src/ tests/
```

- [ ] **Step 3: Run mypy and fix type errors**

```bash
uv run mypy src/
```

Fix any type errors. Common ones:
- `asynccontextmanager` return type annotations
- `dict | None` vs `Optional[dict]` for older mypy
- Missing `__all__` (ignore these)

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest --cov=scholar_mcp --cov-report=term-missing
```

Expected: all pass. Note coverage percentage.

- [ ] **Step 5: Update README.md**

Replace the template README with a scholar-mcp README containing:
- Purpose and feature list (all 14 tools, briefly)
- Environment variable table (copy from spec)
- Quick start with `uvx` / `docker run`
- Docker compose snippet:

```yaml
services:
  scholar-mcp:
    image: ghcr.io/pvliesdonk/scholar-mcp:latest
    restart: unless-stopped
    environment:
      SCHOLAR_MCP_S2_API_KEY: "${SCHOLAR_MCP_S2_API_KEY}"
      SCHOLAR_MCP_DOCLING_URL: "http://docling-serve:5001"
      SCHOLAR_MCP_VLM_API_URL: "${VLM_API_URL}"
      SCHOLAR_MCP_VLM_API_KEY: "${VLM_API_KEY}"
      SCHOLAR_MCP_CACHE_DIR: "/data/scholar-mcp"
      SCHOLAR_MCP_READ_ONLY: "false"
    volumes:
      - scholar-mcp-data:/data/scholar-mcp
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.scholar-mcp.rule=Host(`scholar-mcp.yourdomain.com`)"
      - "traefik.http.routers.scholar-mcp.middlewares=authelia@docker"

volumes:
  scholar-mcp-data:
```

- [ ] **Step 6: Commit and close issue**

```bash
git add README.md pyproject.toml
git commit -m "docs: add ops documentation and deployment guide"
gh issue close <ops issue number> --comment "README updated with Docker compose and env var docs"
```

---

### Task 15: Final verification

- [ ] **Step 1: Run the full test suite one last time**

```bash
uv run pytest -v --cov=scholar_mcp
```

Expected: all pass.

- [ ] **Step 2: Run linting and type checking**

```bash
uv run ruff check src/ tests/
uv run mypy src/
```

Expected: no errors.

- [ ] **Step 3: Build the Docker image locally**

```bash
docker build -t scholar-mcp:dev .
```

Expected: builds without error.

- [ ] **Step 4: Smoke-test with MCP Inspector or Claude Desktop**

```bash
SCHOLAR_MCP_CACHE_DIR=/tmp/scholar-test \
uv run scholar-mcp serve --transport stdio
```

Connect via MCP Inspector and call `search_papers` with a simple query.

- [ ] **Step 5: Tag v0.1.0**

```bash
git tag v0.1.0
git push origin main --tags
```

The CI release workflow will build and publish the Docker image.
