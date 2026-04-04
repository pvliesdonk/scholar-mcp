#!/bin/bash
# Post-remove script: clean up venv and optionally remove system user.
# State data in /var/lib/scholar-mcp is intentionally preserved.
set -eu

INSTALL_DIR="/opt/scholar-mcp"
SERVICE_USER="scholar-mcp"

# Remove the venv and install directory (not state data)
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
fi

# Reload systemd after unit file removal
systemctl daemon-reload 2>/dev/null || true

# Remove system user only on purge (.deb) or full remove (.rpm).
# $1 is "purge" on dpkg, or "0" (final remove) on rpm.
case "${1:-}" in
    purge|0)
        if getent passwd "$SERVICE_USER" >/dev/null 2>&1; then
            userdel "$SERVICE_USER" 2>/dev/null || true
        fi
        if getent group "$SERVICE_USER" >/dev/null 2>&1; then
            groupdel "$SERVICE_USER" 2>/dev/null || true
        fi
        ;;
esac
