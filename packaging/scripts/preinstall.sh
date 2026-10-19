#!/bin/sh
# Pre-install script: create system user and group for scholar-mcp.
# POSIX sh, not bash: rpm runs every scriptlet under /bin/sh whatever its
# shebang (nfpm's rpmpack sets the interpreter), and dpkg honours this line,
# so one dialect behaves the same in both packages.
# Idempotent — safe to run multiple times.
set -eu

SERVICE_USER="scholar-mcp"

if ! getent group "$SERVICE_USER" >/dev/null 2>&1; then
    groupadd --system "$SERVICE_USER"
fi

if ! getent passwd "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system \
        --gid "$SERVICE_USER" \
        --no-create-home \
        --home-dir /var/lib/scholar-mcp \
        --shell /usr/sbin/nologin \
        --comment "Scholar MCP Server" \
        "$SERVICE_USER"
fi
