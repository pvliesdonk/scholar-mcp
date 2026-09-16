# Installation

## From PyPI

```
pip install pvliesdonk-scholar-mcp
```

## From Docker

```
docker pull ghcr.io/pvliesdonk/scholar-mcp:latest
```

The `latest` tag is the newest stable release. The rolling `edge` tag tracks every merge to `main` and carries no version identity; see [Image tags](https://pvliesdonk.github.io/scholar-mcp/unstable/deployment/docker/#image-tags) for the full list.

## From source

```
git clone https://github.com/pvliesdonk/scholar-mcp
cd scholar-mcp
uv sync --all-extras --all-groups
```

## As a Claude Code plugin

```
/plugin marketplace add pvliesdonk/claude-plugins
/plugin install scholar-mcp@pvliesdonk
```

See [Claude Code Plugin guide](https://pvliesdonk.github.io/scholar-mcp/unstable/guides/claude-code-plugin/index.md) for configuration and details.

## With `uvx` (recommended)

[`uvx`](https://docs.astral.sh/uv/) runs the server in an isolated environment without installing anything globally:

```
uvx --from pvliesdonk-scholar-mcp scholar-mcp serve
```

Package name vs. command

The PyPI package is `pvliesdonk-scholar-mcp`. The CLI command installed is `scholar-mcp`. The `--from` flag is needed because the package and command names differ.

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

See [systemd deployment](https://pvliesdonk.github.io/scholar-mcp/unstable/deployment/systemd/index.md) for configuration details.
