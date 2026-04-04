# FastMCP Server Template

A production-ready FastMCP server scaffold. Replace this page with your service's documentation.

## What's included

- **FastMCP server** with `create_server()` factory, full auth wiring, and read-only mode
- **Authentication** — bearer token, OIDC, and multi-auth (both simultaneously)
- **CI/CD** — test matrix (Python 3.11–3.14), linting, type checking, dependency audit, secret scanning
- **Release pipeline** — semantic-release → PyPI + Docker (GHCR), SBOM attestation
- **Docker** — multi-arch build, `gosu` privilege dropping, configurable PUID/PGID
- **MkDocs** — GitHub Pages docs site with Material theme

## Quick start

See [TEMPLATE.md](https://github.com/pvliesdonk/fastmcp-server-template/blob/main/TEMPLATE.md)
for the step-by-step guide to customising this template for your own MCP server.

## Authentication

See [Authentication guide](guides/authentication.md) for bearer token, OIDC,
and multi-auth setup — this guide is generic and applies to all servers built
from this template.
