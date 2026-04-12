# Installation

## As a Claude Code plugin

```bash
/plugin marketplace add pvliesdonk/claude-plugins
/plugin install scholar-mcp@pvliesdonk
```

See [Claude Code Plugin guide](guides/claude-code-plugin.md) for configuration and details.

## With `uvx` (recommended)

[`uvx`](https://docs.astral.sh/uv/) runs the server in an isolated environment without installing anything globally:

```bash
uvx --from pvliesdonk-scholar-mcp scholar-mcp serve
```

!!! note "Package name vs. command"
    The PyPI package is `pvliesdonk-scholar-mcp`. The CLI command installed is `scholar-mcp`.
    The `--from` flag is needed because the package and command names differ.

## With `pip`

```bash
pip install 'pvliesdonk-scholar-mcp[mcp]'
scholar-mcp serve
```

The `[mcp]` extra installs FastMCP and uvicorn. Without it, you get only the library (API clients and cache) without the MCP server.

## With Docker

```bash
docker run -v scholar-mcp-data:/data/scholar-mcp \
           ghcr.io/pvliesdonk/scholar-mcp:latest
```

The image is available for `linux/amd64` and `linux/arm64`. See [Docker deployment](deployment/docker.md) for Docker Compose with docling-serve.

For early adopters who want to test unreleased changes, an `:unstable` tag is published by the release workflow's pre-release mode. It tracks the latest release candidate and may include in-progress features. The floating `:latest`, `:vN`, and `:vN.M` tags only move on stable releases.

```bash
docker pull ghcr.io/pvliesdonk/scholar-mcp:unstable
```

## Linux packages

Download `.deb` or `.rpm` from the [latest release](https://github.com/pvliesdonk/scholar-mcp/releases/latest):

=== "Debian / Ubuntu"

    ```bash
    sudo dpkg -i scholar-mcp_*.deb
    sudo systemctl enable --now scholar-mcp
    ```

=== "RHEL / Fedora"

    ```bash
    sudo rpm -i scholar-mcp-*.rpm
    sudo systemctl enable --now scholar-mcp
    ```

The package installs:

- A systemd service (`scholar-mcp.service`)
- A Python venv at `/opt/scholar-mcp/venv/`
- An example config at `/etc/scholar-mcp/env.example`
- A dedicated `scholar-mcp` system user

See [systemd deployment](deployment/systemd.md) for configuration details.

## From source

```bash
git clone https://github.com/pvliesdonk/scholar-mcp.git
cd scholar-mcp
uv sync --extra dev --extra mcp
uv run scholar-mcp serve
```
