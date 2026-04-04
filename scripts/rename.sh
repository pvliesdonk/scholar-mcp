#!/usr/bin/env bash
# rename.sh — bootstrap a new MCP server from this template.
#
# Usage:
#   ./scripts/rename.sh <repo-name> <python_module> <ENV_PREFIX> "Human Name"
#
# Example:
#   ./scripts/rename.sh my-weather-service my_weather_service WEATHER_MCP "Weather MCP Server"
#
# What it replaces (case-sensitive, across all text files):
#   fastmcp-server-template  → <repo-name>
#   fastmcp_server_template  → <python_module>
#   MCP_SERVER               → <ENV_PREFIX>
#   FastMCP Server Template  → <Human Name>
#   mcp-server               → <repo-name>  (CLI command)
#
# Safe to run multiple times (idempotent after first run).

set -euo pipefail

if [ "$#" -ne 4 ]; then
    echo "Usage: $0 <repo-name> <python_module> <ENV_PREFIX> \"Human Name\""
    echo "Example: $0 my-weather-service my_weather_service WEATHER_MCP \"Weather MCP Server\""
    exit 1
fi

REPO_NAME="$1"
PYTHON_MODULE="$2"
ENV_PREFIX="$3"
HUMAN_NAME="$4"
CLI_CMD="$REPO_NAME"

echo "Renaming template:"
echo "  repo name    : fastmcp-server-template → $REPO_NAME"
echo "  python module: fastmcp_server_template → $PYTHON_MODULE"
echo "  env prefix   : MCP_SERVER → $ENV_PREFIX"
echo "  human name   : FastMCP Server Template → $HUMAN_NAME"
echo "  CLI command  : mcp-server → $CLI_CMD"
echo

# Text files to update (exclude binary, .git, __pycache__, site, uv.lock)
FILES=$(git ls-files | grep -v -E '\.(png|jpg|gif|ico|woff|woff2|eot|ttf|svg)$' | grep -v 'uv\.lock')

for f in $FILES; do
    if [ -f "$f" ]; then
        sed -i \
            -e "s|fastmcp-server-template|$REPO_NAME|g" \
            -e "s|fastmcp_server_template|$PYTHON_MODULE|g" \
            -e "s|MCP_SERVER|$ENV_PREFIX|g" \
            -e "s|FastMCP Server Template|$HUMAN_NAME|g" \
            -e "s|mcp-server|$CLI_CMD|g" \
            "$f"
    fi
done

# Rename the source directory
if [ -d "src/fastmcp_server_template" ] && [ ! -d "src/$PYTHON_MODULE" ]; then
    mv "src/fastmcp_server_template" "src/$PYTHON_MODULE"
    echo "Renamed src/fastmcp_server_template → src/$PYTHON_MODULE"
fi

echo
echo "Done. Next steps:"
echo "  1. Review changes: git diff"
echo "  2. Delete this template: rm -rf scripts/"
echo "  3. Update README.md and TEMPLATE.md with your service details"
echo "  4. Add your domain logic in src/$PYTHON_MODULE/_server_tools.py"
echo "  5. Update src/$PYTHON_MODULE/_server_deps.py with your service init"
echo "  6. Run: uv sync && uv run pytest"
