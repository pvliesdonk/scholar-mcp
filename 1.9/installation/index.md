# Installation

## As a Claude Code plugin

```
/plugin marketplace add pvliesdonk/claude-plugins
/plugin install scholar-mcp@pvliesdonk
```

See [Claude Code Plugin guide](https://pvliesdonk.github.io/scholar-mcp/1.9/guides/claude-code-plugin/index.md) for configuration and details.

## With `uvx` (recommended)

[`uvx`](https://docs.astral.sh/uv/) runs the server in an isolated environment without installing anything globally:

```
uvx --from pvliesdonk-scholar-mcp scholar-mcp serve
```

Package name vs. command

The PyPI package is `pvliesdonk-scholar-mcp`. The CLI command installed is `scholar-mcp`. The `--from` flag is needed because the package and command names differ.

## With `pip`

```
pip install 'pvliesdonk-scholar-mcp[mcp]'
scholar-mcp serve
```

The `[mcp]` extra installs FastMCP and uvicorn. Without it, you get only the library (API clients and cache) without the MCP server.

## With Docker

```
docker run -v scholar-mcp-data:/data/scholar-mcp \
           ghcr.io/pvliesdonk/scholar-mcp:latest
```

The image is available for `linux/amd64` and `linux/arm64`. See [Docker deployment](https://pvliesdonk.github.io/scholar-mcp/1.9/deployment/docker/index.md) for Docker Compose with docling-serve.

For early adopters who want to try the latest release candidate, an `:unstable` tag is published by the release workflow's pre-release mode. It tracks the latest `rc` build and may include in-progress features. Pre-releases are Docker-only, they are not published to PyPI or as Linux packages. The floating `:latest`, `:vN`, and `:vN.M` tags only move on stable releases.

```
docker run -v scholar-mcp-data:/data/scholar-mcp \
           ghcr.io/pvliesdonk/scholar-mcp:unstable
```

## Linux packages

Download `.deb` or `.rpm` from the [latest release](https://github.com/pvliesdonk/scholar-mcp/releases/latest):

```
sudo dpkg -i scholar-mcp_*.deb
sudo systemctl enable --now scholar-mcp
```

```
sudo rpm -i scholar-mcp-*.rpm
sudo systemctl enable --now scholar-mcp
```

The package installs:

- A systemd service (`scholar-mcp.service`)
- A Python venv at `/opt/scholar-mcp/venv/`
- An example config at `/etc/scholar-mcp/env.example`
- A dedicated `scholar-mcp` system user

See [systemd deployment](https://pvliesdonk.github.io/scholar-mcp/1.9/deployment/systemd/index.md) for configuration details.

## From source

```
git clone https://github.com/pvliesdonk/scholar-mcp.git
cd scholar-mcp
uv sync --extra dev --extra mcp
uv run scholar-mcp serve
```
