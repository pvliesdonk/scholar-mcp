#!/usr/bin/env bash
# Build a scholar-mcp .mcpb bundle locally.
#
# Usage:
#   VERSION=1.6.0 ./packaging/mcpb/build.sh
#
# With no VERSION set, builds a "dev" bundle for validation only.
set -euo pipefail

VERSION="${VERSION:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BUILD_DIR="${REPO_ROOT}/packaging/mcpb/build"
DIST_DIR="${REPO_ROOT}/packaging/mcpb/dist"

command -v mcpb >/dev/null 2>&1 || {
  echo "error: mcpb CLI not found. Install with:" >&2
  echo "  npm install -g @anthropic-ai/mcpb@2.1.2" >&2
  exit 1
}

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/src" "${DIST_DIR}"

# Restrict substitution to ${VERSION} only — other ${...} tokens in the template
# (e.g. ${DOCUMENTS}, ${user_config.*}) are runtime placeholders for the host.
VERSION="${VERSION}" envsubst '${VERSION}' < "${SCRIPT_DIR}/manifest.json.in" \
  > "${BUILD_DIR}/manifest.json"
VERSION="${VERSION}" envsubst '${VERSION}' < "${SCRIPT_DIR}/pyproject.toml.in" \
  > "${BUILD_DIR}/pyproject.toml"
cp "${SCRIPT_DIR}/src/server.py" "${BUILD_DIR}/src/server.py"

mcpb validate "${BUILD_DIR}/manifest.json"
mcpb pack "${BUILD_DIR}" "${DIST_DIR}/scholar-mcp-${VERSION}.mcpb"

echo "built ${DIST_DIR}/scholar-mcp-${VERSION}.mcpb"
