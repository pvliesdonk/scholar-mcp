---
description: "Every way to install Scholar MCP, by where it runs, with a check of what you installed."
kind: how-to
---

# Installation

The client tutorials each install the server one way. This page lists every way, so you can pick by where the server runs, and ends with how to check what you installed. Which channel each release reaches is on the [Upgrade](../upgrade/index.md#release-channels) page.

Before you expose the server beyond your own machine, read the [security model](../security-model.md).

## As a command on your machine

For a client that starts the server itself (Claude Desktop, or Claude Code over stdio), install it as a command with [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
uv tool install "pvliesdonk-scholar-mcp"
```

uv gives the server its own environment and finds a Python for it, downloading one when your machine has none. The `scholar-mcp` command lands in uv's executable directory, `~/.local/bin` unless you configured another (`uv tool dir --bin` prints it). `uv tool upgrade pvliesdonk-scholar-mcp` moves to the newest release; `uv tool install "pvliesdonk-scholar-mcp==X.Y.Z"` pins one, a release candidate included (`X.Y.ZrcN`).

In an environment you manage yourself, `pip install "pvliesdonk-scholar-mcp"` installs the same package. To run a release without installing anything:

```bash
uvx --from "pvliesdonk-scholar-mcp" scholar-mcp serve
```

Quote the package name whenever it carries an extra, `"pvliesdonk-scholar-mcp[extra]"`: without the quotes, zsh, the default shell on macOS, reads the brackets as a pattern and the command fails. The extras this server defines are under [Notes for this server](#notes-for-this-server).

## Claude Desktop

Each release ships a `.mcpb` bundle on the [releases page](https://github.com/pvliesdonk/scholar-mcp/releases). Open it with Claude Desktop, or choose **Settings** › **Extensions** › **Advanced settings** › **Install Extension…**; Claude Desktop asks for the settings this server declares and configures itself. The bundle carries no code: it pins the released package at its own version and fetches it from PyPI with `uvx` on first launch, so the machine needs network access then. A release candidate's bundle installs the same way. The [Claude Desktop](claude-desktop.md) tutorial takes it from there.

## Claude Code

Two commands inside Claude Code install the plugin, which runs the released package:

```text
/plugin marketplace add pvliesdonk/claude-plugins
/plugin install scholar-mcp@pvliesdonk
```

The marketplace entry follows stable releases only. The [Claude Code](claude-code.md) tutorial covers the scope question, settings and the command-line route.

## Docker

```bash
docker pull ghcr.io/pvliesdonk/scholar-mcp:latest
```

`latest` is the newest stable release. The image's other tags (exact versions, `rc`, `edge`) are on the [Docker](../deploy/docker.md#image-tags) page, which is where a deployment continues.

## Linux packages

Each release ships a `.deb` and an `.rpm`. The names below carry no version and fetch the newest stable release:

```bash
curl -LO https://github.com/pvliesdonk/scholar-mcp/releases/latest/download/scholar-mcp_latest.deb
sudo apt install ./scholar-mcp_latest.deb
```

```bash
curl -LO https://github.com/pvliesdonk/scholar-mcp/releases/latest/download/scholar-mcp_latest.rpm
sudo dnf install ./scholar-mcp_latest.rpm
```

The package needs `python3` 3.11 or newer with `venv`. It creates a virtual environment under `/opt/scholar-mcp/venv` and installs `pvliesdonk-scholar-mcp` at the package's own version from PyPI, so the machine needs network access during the install; a release candidate's package installs the wheel attached to its own GitHub release instead. The package also installs:

- `/etc/scholar-mcp/env`, copied from `env.example` on first install, readable by root only and never overwritten by an upgrade: the server's configuration, read by the service.
- `/var/lib/scholar-mcp`, the state directory, owned by the `scholar-mcp` system user the package creates.
- The systemd unit `scholar-mcp.service`, which runs `scholar-mcp serve --transport http` as that user. It is installed but not enabled; to start it now and on every boot:

```bash
sudo systemctl enable --now scholar-mcp
```

An upgrade restarts a running service. [Deploy](../deploy/index.md) covers the environment file and the service from here.

## From source

```bash
git clone https://github.com/pvliesdonk/scholar-mcp
cd scholar-mcp
uv sync --all-extras --all-groups
uv run scholar-mcp serve
```

This is the setup for changing the project; [Contribute](../contribute/index.md) continues from here.

## Check what you installed

- The command: `scholar-mcp --help` lists its commands and options; the [command line](../reference/cli.md) reference describes them.
- A connected client, local or remote: ask Claude which version is running. The `get_server_info` tool reports `server_version`.

## Notes for this server

<!-- DOMAIN-INSTALL-EXTRA-START -->
## As a Claude Code plugin

```bash
/plugin marketplace add pvliesdonk/claude-plugins
/plugin install scholar-mcp@pvliesdonk
```

See [Claude Code Plugin guide](../guides/claude-code-plugin.md) for configuration and details.

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

See [systemd deployment](../deployment/systemd.md) for configuration details.
<!-- DOMAIN-INSTALL-EXTRA-END -->
