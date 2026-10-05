---
description: "Run Scholar MCP as a systemd service from the .deb or .rpm package, from the environment file to upgrades."
kind: how-to
---

# systemd and the Linux packages

The `.deb` and `.rpm` on the [releases page](https://github.com/pvliesdonk/scholar-mcp/releases) install the server as a systemd service. [Installation](../get-started/installation.md#linux-packages) has the install commands; this page is what comes after. The unit confines the process, which is defence in depth: authentication stays the boundary, and the [security model](../security-model.md) says what an authenticated caller then reaches.

## What the package installed

| Path | What it is | Owner |
|---|---|---|
| `/opt/scholar-mcp/venv` | The server, installed from PyPI at the package's own version (a release candidate installs the wheel attached to its GitHub release) | root |
| `/usr/lib/systemd/system/scholar-mcp.service` | The unit | root |
| `/etc/scholar-mcp/env.example` | Every variable, commented out, generated from the server's configuration surface; replaced by an upgrade | root |
| `/etc/scholar-mcp/env` | Your configuration, copied from `env.example` on first install, readable by root only (`600`), never touched by an upgrade | root |
| `/var/lib/scholar-mcp` | The state directory, the one path the service may write | `scholar-mcp:scholar-mcp` |

The package also creates the `scholar-mcp` system user and group the service runs as, with `/var/lib/scholar-mcp` as home and no login shell.

## Configure

Edit `/etc/scholar-mcp/env`. It holds deviations from the defaults only: every line arrives commented out, and the server starts on its defaults when nothing is set. Remove the `#` from the lines you change. The unit reads the file at start (`EnvironmentFile=`), so an edit needs a restart to take effect. Secrets belong here and nowhere else; the file is already mode `600`.

```ini { .config data-expect="server_name='notes'" }
# /etc/scholar-mcp/env
SCHOLAR_MCP_SERVER_NAME=notes
SCHOLAR_MCP_LOG_LEVEL=INFO
```

The unit starts `scholar-mcp serve --transport http`, so the server listens on `SCHOLAR_MCP_HOST` and `SCHOLAR_MCP_PORT`, `127.0.0.1:8000` unless set. To serve other machines, configure [authentication](authentication.md) first and put a [reverse proxy](reverse-proxy.md) in front; the [configuration reference](../reference/configuration.md) lists every variable.

## Start and watch

The package installs the unit but does not enable it; starting on boot is your decision:

```bash
sudo systemctl enable --now scholar-mcp
systemctl status scholar-mcp
journalctl -u scholar-mcp -f
sudo systemctl restart scholar-mcp    # after editing the env file
```

Under journald each record is one JSON object: the unit sets no log format, so the server picks its JSON renderer because journald is not a terminal. `SCHOLAR_MCP_LOG_FORMAT=rich` in the env file switches to the coloured renderer. `Restart=on-failure` brings a crashed server back after five seconds.

## What the unit allows

The unit runs the server as the `scholar-mcp` user with these directives, among others:

| Directive | Effect |
|---|---|
| `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes` | The filesystem is read-only except the paths listed below; `/home`, `/root` and `/run/user` are not visible; a private `/tmp` |
| `StateDirectory=scholar-mcp`, `ReadWritePaths=/var/lib/scholar-mcp` | The one writable path, created and owned for the service |
| `NoNewPrivileges=yes`, an empty `CapabilityBoundingSet=` | No privilege escalation and no capabilities |
| `PrivateDevices=yes`, `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6` | No devices; only Unix, IPv4 and IPv6 sockets, so outbound connections to other services work |
| `SystemCallFilter=@system-service` | Only the system calls an ordinary service needs |
| `MemoryDenyWriteExecute=no` | Left open because Python needs writable, executable memory |
| `UMask=0027` | New files are group-readable, so an administrator in the `scholar-mcp` group can inspect the state directory |

To let the server read or write a path outside `/var/lib/scholar-mcp`, add a drop-in rather than editing the unit, which the next package upgrade replaces:

```bash
sudo systemctl edit scholar-mcp
```

```ini
[Service]
ReadWritePaths=/srv/scholar-mcp
```

`systemctl edit` reloads the unit definitions; restart the service afterwards. The other directives stay as they are. On a host with SELinux enforcing, the directory also needs a label the service may use (`semanage fcontext`, then `restorecon`).

## Upgrade

Install the new package the same way as the first one. Its `postinstall` installs the new version into the existing virtual environment and restarts the service when it is running. `/etc/scholar-mcp/env` is left alone; `env.example` is replaced, so compare the two for variables the release added:

```bash
diff /etc/scholar-mcp/env.example /etc/scholar-mcp/env
```

What a release changes for your clients and your data is on the [Upgrade](../upgrade/index.md) page.

## Without a package

On a distribution the packages do not cover, mirror what the package does. The unit and the environment template live in the repository's `packaging/` directory at every release tag. Before you run the block, set `EXTRAS` to the value `packaging/scripts/postinstall.sh` gives it at the same tag: the package installs those extras, and an install without them lacks the features they bring.

```bash
sudo groupadd --system scholar-mcp
sudo useradd --system --gid scholar-mcp --no-create-home \
  --home-dir /var/lib/scholar-mcp --shell /usr/sbin/nologin scholar-mcp
sudo mkdir -p /opt/scholar-mcp /etc/scholar-mcp /var/lib/scholar-mcp
sudo python3 -m venv /opt/scholar-mcp/venv
EXTRAS=""  # set from packaging/scripts/postinstall.sh first, such as "[all]"
sudo /opt/scholar-mcp/venv/bin/pip install "pvliesdonk-scholar-mcp${EXTRAS}==X.Y.Z"
sudo curl -fsSL -o /usr/lib/systemd/system/scholar-mcp.service \
  https://raw.githubusercontent.com/pvliesdonk/scholar-mcp/vX.Y.Z/packaging/scholar-mcp.service
sudo curl -fsSL -o /etc/scholar-mcp/env.example \
  https://raw.githubusercontent.com/pvliesdonk/scholar-mcp/vX.Y.Z/packaging/env.example
sudo cp /etc/scholar-mcp/env.example /etc/scholar-mcp/env
sudo chmod 600 /etc/scholar-mcp/env
sudo chown scholar-mcp:scholar-mcp /var/lib/scholar-mcp
sudo systemctl daemon-reload
```

Then configure and start as above. Python 3.11 or newer with the `venv` module is the one system requirement.

## If it does not start

- `journalctl -u scholar-mcp -n 50 --no-pager` shows the last records; a configuration error names the variable.
- Run the command as the service user to see the error directly: `sudo -u scholar-mcp /opt/scholar-mcp/venv/bin/scholar-mcp serve --transport http`.
- A permission error on a path outside `/var/lib/scholar-mcp` is the confinement above: add the drop-in, or move the data.
- `systemd-analyze verify /usr/lib/systemd/system/scholar-mcp.service` checks the unit after an edit.

<!-- DOMAIN-SYSTEMD-EXTRA-START -->
<!-- What this server needs on a package install: data paths to open with ReadWritePaths, the variables that must be set before the first start, services it reaches; kept across copier update. -->
<!-- DOMAIN-SYSTEMD-EXTRA-END -->
