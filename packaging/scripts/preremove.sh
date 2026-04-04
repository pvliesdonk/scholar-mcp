#!/bin/bash
# Pre-remove script: stop and disable the service.
# Skips stop/disable during upgrades — postinstall handles restart.
set -eu

SERVICE_NAME="scholar-mcp"

# During an upgrade, skip stopping/disabling so postinstall can restart cleanly.
# Debian: $1 = "upgrade"; RPM: $1 = "1" (packages remaining after operation).
case "${1:-}" in
    upgrade|1)
        exit 0
        ;;
esac

# Stop the service if running or in failed state
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null || systemctl is-failed --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl stop "$SERVICE_NAME"
fi

# Disable the service
if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl disable "$SERVICE_NAME"
fi
