# systemd Deployment

Scholar MCP provides `.deb` and `.rpm` packages with a pre-configured systemd service.

## Installation

Download the latest package from the [releases page](https://github.com/pvliesdonk/scholar-mcp/releases/latest):

=== "Debian / Ubuntu"

    ```bash
    sudo dpkg -i scholar-mcp_*.deb
    ```

=== "RHEL / Fedora"

    ```bash
    sudo rpm -i scholar-mcp-*.rpm
    ```

The package installs:

| Path | Description |
|---|---|
| `/usr/lib/systemd/system/scholar-mcp.service` | systemd unit file |
| `/opt/scholar-mcp/venv/` | Python virtual environment with the server |
| `/etc/scholar-mcp/env.example` | Example configuration file |
| `/var/lib/scholar-mcp/` | State directory (cache, PDFs) |

A dedicated `scholar-mcp` system user and group are created automatically.

## Configuration

Copy the example config and edit it:

```bash
sudo cp /etc/scholar-mcp/env.example /etc/scholar-mcp/env
sudo chmod 600 /etc/scholar-mcp/env
sudo nano /etc/scholar-mcp/env
```

Set the cache directory and (optionally) your Semantic Scholar API key:

```bash
SCHOLAR_MCP_CACHE_DIR=/var/lib/scholar-mcp
# Optional but recommended — without a key, requests are limited to ~1 req/s
SCHOLAR_MCP_S2_API_KEY=your-key-here
```

See [Configuration](../configuration.md) for all available variables.

## Starting the service

```bash
# Start the service
sudo systemctl start scholar-mcp

# Enable start on boot
sudo systemctl enable scholar-mcp

# Check status
sudo systemctl status scholar-mcp

# View logs
sudo journalctl -u scholar-mcp -f
```

The service runs in HTTP mode on port 8000 by default.

## Security hardening

The systemd unit includes comprehensive security directives:

| Directive | Effect |
|---|---|
| `ProtectSystem=strict` | Filesystem is read-only except explicit paths |
| `ProtectHome=yes` | Home directories are inaccessible |
| `PrivateTmp=yes` | Private `/tmp` namespace |
| `ReadWritePaths=/var/lib/scholar-mcp` | Only the state directory is writable |
| `NoNewPrivileges=yes` | Cannot gain privileges |
| `PrivateDevices=yes` | No access to physical devices |
| `ProtectKernelTunables=yes` | Kernel tunables are read-only |
| `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6` | Only Unix and IP sockets |
| `SystemCallFilter=@system-service` | Restricted syscall set |
| `MemoryDenyWriteExecute=no` | Required for Python JIT |

## Upgrading

Install the new package version:

=== "Debian / Ubuntu"

    ```bash
    sudo dpkg -i scholar-mcp_*.deb
    ```

=== "RHEL / Fedora"

    ```bash
    sudo rpm -U scholar-mcp-*.rpm
    ```

The post-install script automatically:

1. Creates or updates the virtual environment
2. Installs the matching version from PyPI
3. Reloads systemd
4. Restarts the service if it was running

Your configuration in `/etc/scholar-mcp/env` is preserved.

## Uninstalling

=== "Debian / Ubuntu"

    ```bash
    # Remove package (keeps config and data)
    sudo apt remove scholar-mcp

    # Remove everything including config
    sudo apt purge scholar-mcp
    ```

=== "RHEL / Fedora"

    ```bash
    sudo rpm -e scholar-mcp
    ```

State data in `/var/lib/scholar-mcp/` is intentionally preserved on removal. Delete it manually if no longer needed.

## Troubleshooting

### Service fails to start

Check the logs:

```bash
sudo journalctl -u scholar-mcp --no-pager -n 50
```

Common causes:

- **Missing config**: ensure `/etc/scholar-mcp/env` exists and is readable
- **Permission denied on cache dir**: verify `/var/lib/scholar-mcp/` is owned by `scholar-mcp:scholar-mcp`
- **Port in use**: another service is using port 8000; check with `ss -tlnp | grep 8000`

### FastMCP not installed

If the post-install script failed (e.g. no internet during package install):

```bash
sudo /opt/scholar-mcp/venv/bin/pip install 'pvliesdonk-scholar-mcp[all]'
sudo systemctl restart scholar-mcp
```
