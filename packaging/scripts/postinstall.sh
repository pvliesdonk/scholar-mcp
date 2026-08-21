#!/bin/bash
# Post-install script: create venv and install pvliesdonk-scholar-mcp from PyPI.
set -eu

INSTALL_DIR="/opt/scholar-mcp"
VENV_DIR="${INSTALL_DIR}/venv"
SERVICE_USER="scholar-mcp"

# Determine package version — set by nfpm via VERSION env var, or read
# from the installed package metadata as fallback.
PKG_VERSION="${VERSION:-}"

# Create install directory
mkdir -p "$INSTALL_DIR"

# Create or update the virtual environment
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

# Upgrade pip and install the package
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip

# The `[all]` extra is a deliberate local edit to a template-owned file.
# The template renders these three installs bare, but this project ships
# `fastmcp[tasks]` under the `all` extra and the Dockerfile pulls it in both
# layers via `--extra all` (DOCKERFILE-UV-EXTRAS). Dropping it here would
# give the deb/rpm a different install profile than every other channel.
# postinstall.sh has no extras sentinel; requested upstream.
if [ -n "$PKG_VERSION" ]; then
    case "$PKG_VERSION" in
        *-rc.*)
            # Pre-releases never reach PyPI; install the wheel attached to
            # this version's own GitHub release. The wheel filename carries
            # the PEP 440 canonical spelling (-rc.N -> rcN).
            canonical="$(printf '%s' "$PKG_VERSION" | sed 's/-rc\./rc/')"
            "${VENV_DIR}/bin/pip" install --quiet \
                "pvliesdonk-scholar-mcp[all] @ https://github.com/pvliesdonk/scholar-mcp/releases/download/v${PKG_VERSION}/pvliesdonk_scholar_mcp-${canonical}-py3-none-any.whl"
            ;;
        *)
            "${VENV_DIR}/bin/pip" install --quiet "pvliesdonk-scholar-mcp[all]==${PKG_VERSION}"
            ;;
    esac
else
    "${VENV_DIR}/bin/pip" install --quiet "pvliesdonk-scholar-mcp[all]"
fi

# Ensure config directory exists
mkdir -p /etc/scholar-mcp

# Copy example env if no config exists yet
if [ ! -f /etc/scholar-mcp/env ]; then
    if [ -f /etc/scholar-mcp/env.example ]; then
        cp /etc/scholar-mcp/env.example /etc/scholar-mcp/env
    fi
fi

# Restrict env file permissions — it may contain secrets (tokens, API keys).
if [ -f /etc/scholar-mcp/env ]; then
    chmod 600 /etc/scholar-mcp/env
fi

# Reload systemd to pick up the unit file.
# Note: the service is intentionally NOT enabled here — start-on-boot requires
# explicit opt-in by the administrator via: systemctl enable scholar-mcp
systemctl daemon-reload 2>/dev/null || true

# On upgrade, restart the service if it's already running so the new version is loaded.
if systemctl is-active --quiet scholar-mcp 2>/dev/null; then
    systemctl restart scholar-mcp
fi
