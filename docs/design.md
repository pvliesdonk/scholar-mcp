# Scholar MCP Design

<Document your service's design here.  See MV's design.md as a
structural reference.>

## Shared Infrastructure

Generic FastMCP infrastructure (auth providers, middleware stack,
logging bootstrap, server-factory helpers, artifact store, CLI helpers)
lives in the `fastmcp-pvl-core` PyPI package.  Scholar MCP
composes this library via ``ServerConfig`` (never inheritance) — see
`src/scholar_mcp/server.py:make_server` for the assembled call
graph.
