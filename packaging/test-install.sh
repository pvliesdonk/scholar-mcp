#!/bin/bash
# Test .deb installation in a Debian/Ubuntu container.
#
# Usage:
#   # Build the .deb first:
#   VERSION=0.0.0-test nfpm package --packager deb --target dist/
#
#   # Then run this script inside a Debian 12+ / Ubuntu 22.04+ container:
#   docker run --rm -v "$PWD:/work" -w /work debian:bookworm bash packaging/test-install.sh
#
# The script verifies:
#   1. Package installs without errors
#   2. System user/group created
#   3. Directories exist with correct ownership
#   4. systemd unit file is parseable (systemd-analyze verify)
#   5. Environment example file installed
#   6. Package removes cleanly
set -eu

PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1"; }

echo "=== scholar-mcp .deb install test ==="

# Find the .deb
DEB=$(find dist/ -name 'scholar-mcp*.deb' -print -quit 2>/dev/null || true)
if [ -z "$DEB" ]; then
    echo "ERROR: No .deb found in dist/. Build one first:"
    echo "  VERSION=0.0.0-test nfpm package --packager deb --target dist/"
    exit 1
fi
echo "Testing: $DEB"

# --- Install ---
echo ""
echo "--- Installing package ---"
apt-get update -qq
apt-get install -y -qq python3 python3-venv >/dev/null 2>&1
dpkg -i "$DEB" || apt-get install -f -y -qq

# --- Verify installation ---
echo ""
echo "--- Verifying installation ---"

# 1. System user exists
if getent passwd scholar-mcp >/dev/null 2>&1; then
    pass "System user 'scholar-mcp' exists"
else
    fail "System user 'scholar-mcp' not found"
fi

# 2. System group exists
if getent group scholar-mcp >/dev/null 2>&1; then
    pass "System group 'scholar-mcp' exists"
else
    fail "System group 'scholar-mcp' not found"
fi

# 3. State directory exists with correct ownership and permissions
if [ -d /var/lib/scholar-mcp ]; then
    OWNER=$(stat -c '%U:%G' /var/lib/scholar-mcp)
    MODE=$(stat -c '%a' /var/lib/scholar-mcp)
    if [ "$OWNER" = "scholar-mcp:scholar-mcp" ] && [ "$MODE" = "750" ]; then
        pass "State directory owned by scholar-mcp with mode 0750"
    elif [ "$OWNER" != "scholar-mcp:scholar-mcp" ]; then
        fail "State directory owned by $OWNER (expected scholar-mcp:scholar-mcp)"
    else
        fail "State directory mode $MODE (expected 750)"
    fi
else
    fail "/var/lib/scholar-mcp does not exist"
fi

# 4. Install directory exists
if [ -d /opt/scholar-mcp ]; then
    pass "Install directory /opt/scholar-mcp exists"
else
    fail "Install directory /opt/scholar-mcp does not exist"
fi

# 4b. Venv installed by postinstall
if [ -x /opt/scholar-mcp/venv/bin/python3 ]; then
    pass "venv installed at /opt/scholar-mcp/venv"
else
    fail "venv not found at /opt/scholar-mcp/venv (postinstall may have failed)"
fi

# 5. Unit file exists
if [ -f /usr/lib/systemd/system/scholar-mcp.service ]; then
    pass "systemd unit file installed"
else
    fail "systemd unit file not found"
fi

# 6. Unit file is parseable (systemd-analyze may not be available in containers)
if command -v systemd-analyze >/dev/null 2>&1; then
    if output=$(systemd-analyze verify /usr/lib/systemd/system/scholar-mcp.service 2>&1); then
        pass "systemd unit file passes systemd-analyze verify"
    else
        fail "systemd unit file failed systemd-analyze verify"
        echo "Error from systemd-analyze:" >&2
        echo "$output" >&2
    fi
else
    echo "  SKIP: systemd-analyze not available (expected in minimal containers)"
fi

# 7. Environment example exists
if [ -f /etc/scholar-mcp/env.example ]; then
    pass "Environment example file installed"
else
    fail "Environment example file not found"
fi

# --- Verify removal ---
echo ""
echo "--- Removing package ---"
dpkg -r scholar-mcp

# 8. Install directory removed
if [ ! -d /opt/scholar-mcp ]; then
    pass "Install directory removed after uninstall"
else
    fail "Install directory still exists after uninstall"
fi

# 9. State directory preserved (intentional)
if [ -d /var/lib/scholar-mcp ]; then
    pass "State directory preserved after uninstall (expected)"
else
    fail "State directory removed after uninstall (should be preserved)"
fi

# 10. User preserved (only removed on purge)
if getent passwd scholar-mcp >/dev/null 2>&1; then
    pass "System user preserved after remove (only purged on dpkg --purge)"
else
    fail "System user removed on regular uninstall (should only be removed on purge)"
fi

# --- Verify purge ---
echo ""
echo "--- Purging package ---"
dpkg --purge scholar-mcp

# 11. User removed on purge
if ! getent passwd scholar-mcp >/dev/null 2>&1; then
    pass "System user removed on purge"
else
    fail "System user still exists after purge"
fi

# 12. Group removed on purge
if ! getent group scholar-mcp >/dev/null 2>&1; then
    pass "System group removed on purge"
else
    fail "System group still exists after purge"
fi

# --- Summary ---
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
