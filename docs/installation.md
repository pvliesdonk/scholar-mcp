# Installation

## From PyPI

```bash
pip install pvliesdonk-scholar-mcp
```

## From Docker

```bash
docker pull ghcr.io/pvliesdonk/scholar-mcp:latest
```

The `latest` tag is the newest stable release. The rolling `edge` tag tracks every merge to `main` and carries no version identity; see [Image tags](deployment/docker.md#image-tags) for the full list.

## From source

```bash
git clone https://github.com/pvliesdonk/scholar-mcp
cd scholar-mcp
uv sync --all-extras --all-groups
```

<!-- DOMAIN-INSTALL-EXTRA-START -->
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
<!-- DOMAIN-INSTALL-EXTRA-END -->
