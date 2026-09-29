# Security model

This page states what scholar-mcp protects and what it leaves to the operator. [Authentication](authentication.md) covers how to configure each mode, and `SECURITY.md` in the repository covers how to report a vulnerability.

## Authentication is the boundary

Over HTTP, authentication is the only access control: a bearer token, a mapped bearer token file, or OIDC. A request without a valid credential is refused before it reaches a tool. It is the same model as any other MCP server reached over HTTP.

## Running without authentication

With no authentication variables set, the server starts in mode `none` and logs `auth_mode_resolved` at warning level with `mode=none`. Every client that can open a connection to the port then has the full tool surface. Turning authentication off is a decision to trust everything that can reach the port.

The bind address decides which machines reach the port, and nothing more. Binding to `127.0.0.1` keeps other machines out. It does not keep out other processes on the host, nor a web page in a browser on the host that uses DNS rebinding. Without authentication, run the server only where everything that reaches the port is trusted, such as a single-user workstation or a private network you control.

## stdio

Over stdio there is no network listener and no authentication. The MCP client starts the server as a child process, and the server trusts that client. Authentication variables have no effect there, and the server logs `auth_configured_but_stdio_skips_enforcement` when they are set.

## What an authenticated caller can reach

An authenticated caller has every tool the instance exposes. Each tool runs with the server's own privileges: its filesystem and network access, and any credential in its configuration. `SCHOLAR_MCP_TOOLS_ALLOW` and `SCHOLAR_MCP_TOOLS_DENY` trim that set for an instance; see [Configuration](../configuration.md).

<!-- DOMAIN-SECURITY-MODEL-SURFACE-START — what THIS server's tools reach; kept across copier update -->
This server's tools make outbound HTTPS requests on the caller's behalf and
keep what they fetch in a local cache.

- **Outbound requests.** Paper, citation and author tools call Semantic
  Scholar, OpenAlex, Crossref and Unpaywall. PDF lookups also try arXiv and
  PubMed Central. Book tools call Open Library and the Google Books API.
  Patent tools call EPO Open Patent Services. Standards tools call the IETF
  (`datatracker.ietf.org`), the RFC Editor, W3C, ETSI, the Common Criteria portal, the
  European Commission's harmonised-standards pages and GitHub (the Relaton
  datasets and the NIST catalogue releases). Every request carries the
  caller's query terms to that service.
- **Caller-chosen URLs.** `fetch_pdf_by_url` downloads whatever URL the
  caller passes and follows redirects. The server does not filter private or
  internal addresses, so the tool can reach anything the server's network can
  reach. It is a write tool: `SCHOLAR_MCP_READ_ONLY=true`, the default, hides
  it along with the other download and conversion tools.
- **PDF conversion.** When `SCHOLAR_MCP_DOCLING_URL` is set, conversion tools
  send downloaded PDFs to that docling-serve instance. When
  `SCHOLAR_MCP_VLM_API_URL` is set, the server passes that URL and
  `SCHOLAR_MCP_VLM_API_KEY` to docling-serve, which sends page images to the
  VLM endpoint.
- **Local data.** Tools read and write the SQLite cache, downloaded PDFs,
  converted Markdown and book covers under `SCHOLAR_MCP_CACHE_DIR`, and write
  nothing outside it.
- **Credentials.** Upstream calls use the server's own keys, never the
  caller's: `SCHOLAR_MCP_S2_API_KEY`, `SCHOLAR_MCP_EPO_CONSUMER_KEY` and
  `SCHOLAR_MCP_EPO_CONSUMER_SECRET`, `SCHOLAR_MCP_GOOGLE_BOOKS_API_KEY`,
  `SCHOLAR_GITHUB_TOKEN`, and the VLM key above. `SCHOLAR_MCP_CONTACT_EMAIL`
  is sent to OpenAlex and Unpaywall as the polite-pool contact.
<!-- DOMAIN-SECURITY-MODEL-SURFACE-END -->

## What answers without a credential

Some routes answer anyone who can reach the port, with authentication on or off:

- `/health` and `/health/ready`. `SCHOLAR_MCP_HEALTH_DETAIL` decides how much they say; see [Health](../deployment/docker.md#health).
- In the OIDC modes, the OAuth metadata and sign-in routes a client uses before it holds a token.

## What the operator is responsible for

- **TLS.** The server speaks plain HTTP. Terminate TLS at a reverse proxy in front of it.
- **Exposure.** Which interfaces and networks can reach the port. [Ports](../deployment/docker.md#ports) covers the published port of the Docker deployment.
- **Secrets.** Bearer tokens, OIDC client secrets and the credentials the tools use live in the environment or in files you control. Anyone who can read them can act as the server.
- **The debugger port.** A debug build's debugger port grants code execution to anyone who reaches it; see [Remote debugging](../deployment/docker.md#remote-debugging).

## Host and Origin validation

FastMCP can refuse requests whose `Host` or `Origin` header does not name the server, which blocks DNS rebinding against a server running without authentication. It is off by default, and the model above does not depend on it. To turn it on, set `FASTMCP_HTTP_HOST_ORIGIN_PROTECTION` to `auto`, which checks requests that reach the server on a local address, or to `true`, which checks every request against `FASTMCP_HTTP_ALLOWED_HOSTS` (a JSON list of host names). Behind a reverse proxy, test it before relying on it: a request whose headers do not match is refused.

## Reporting a vulnerability

Read this page before reporting. A finding that depends on authentication being off describes the configuration above rather than a flaw in the server. `SECURITY.md` covers the reporting channel, scope and response targets.

<!-- DOMAIN-SECURITY-MODEL-EXTRA-START -->
<!-- Project-specific security notes go here; kept across copier update. -->
<!-- DOMAIN-SECURITY-MODEL-EXTRA-END -->
