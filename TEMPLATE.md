# Using This Template

This is a production-ready FastMCP server scaffold. Follow these steps to turn it into your own MCP server.

## Step 1: Create your repo

Click **"Use this template"** on GitHub (or `gh repo create --template pvliesdonk/fastmcp-server-template`).

## Step 2: Rename everything

Run the bootstrap script to replace all template identifiers in one pass:

```bash
./scripts/rename.sh <repo-name> <python_module> <ENV_PREFIX> "Human Name"

# Example:
./scripts/rename.sh my-weather-service my_weather_service WEATHER_MCP "Weather MCP Server"
```

This replaces:
- `fastmcp-server-template` → your repo name (also used as CLI command)
- `fastmcp_server_template` → your Python module name
- `MCP_SERVER` → your env var prefix
- `FastMCP Server Template` → your human-readable name

Review with `git diff`, then commit.

## Step 3: Add your domain logic

### Service initialisation (`_server_deps.py`)

Replace the placeholder dict with your actual service object:

```python
# Before (placeholder):
service: dict[str, Any] = {"ready": True}

# After (example):
from my_service import MyDatabase
service = MyDatabase(config.data_dir)
await service.connect()
```

Add teardown in the `finally` block.

### Configuration (`config.py`)

Add your domain env vars to `ServerConfig` and `load_config()`:

```python
@dataclass
class ServerConfig:
    read_only: bool = True
    data_dir: Path = Path("/data/service")   # your field
    api_key: str | None = None               # your field
```

### Tools (`_server_tools.py`)

Replace the example tools with your domain tools. Tag write tools with `tags={"write"}`:

```python
@mcp.tool()
def get_weather(city: str, ctx: Any = Depends(get_service)) -> dict:
    """Get current weather for a city."""
    return ctx.fetch_weather(city)

@mcp.tool(tags={"write"})
def set_alert(city: str, threshold_c: float, ctx: Any = Depends(get_service)) -> str:
    """Set a temperature alert."""
    ctx.add_alert(city, threshold_c)
    return f"Alert set for {city} at {threshold_c}°C"
```

### Resources and prompts

Add domain resources to `_server_resources.py` and prompts to `_server_prompts.py`.

## Step 4: Configure GitHub

1. Set up secrets: `RELEASE_TOKEN` (PAT with repo+packages write), `CODECOV_TOKEN`
2. Enable GitHub Pages (Settings → Pages → Source: GitHub Actions)
3. Create PyPI trusted publisher for the release workflow
4. Enable "Template repository" (Settings → General → Template repository) if you want
   others to use this as a template

## Step 5: Verify

```bash
uv sync
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

All checks should pass before you start building.

## What's included

| Component | File | Notes |
|-----------|------|-------|
| FastMCP server factory | `mcp_server.py` | Auth wiring, read-only mode — don't modify |
| Service lifespan | `_server_deps.py` | Replace placeholder with your service init |
| Config | `config.py` | Add your domain env vars |
| CLI | `cli.py` | `serve` command — extend if needed |
| Tools | `_server_tools.py` | Your domain tools go here |
| Resources | `_server_resources.py` | Your domain resources go here |
| Prompts | `_server_prompts.py` | Your domain prompts go here |
| CI | `.github/workflows/ci.yml` | Test matrix, lint, audit — no changes needed |
| Release | `.github/workflows/release.yml` | semantic-release → PyPI + Docker |
| Docker | `Dockerfile` + `docker-entrypoint.sh` | Multi-arch, PUID/PGID support |

## Authentication

All auth is wired in `mcp_server.py` and needs no changes. Configure via env vars:

- Bearer token: set `<YOUR_PREFIX>_BEARER_TOKEN`
- OIDC: set `<YOUR_PREFIX>_BASE_URL`, `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`
- Both: multi-auth (either credential accepted)

See [docs/guides/authentication.md](docs/guides/authentication.md) for the full guide.
