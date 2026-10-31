# Deploy

These pages are for an operator running the server for others over HTTP, as a container or a system service, with every caller authenticated. Each page covers one task. Start with [Docker](https://pvliesdonk.github.io/scholar-mcp/unstable/deploy/docker/index.md) for a container or [systemd](https://pvliesdonk.github.io/scholar-mcp/unstable/deploy/systemd/index.md) for the `.deb`/`.rpm` package; then [Authentication](https://pvliesdonk.github.io/scholar-mcp/unstable/deploy/authentication/index.md), then the [reverse proxy](https://pvliesdonk.github.io/scholar-mcp/unstable/deploy/reverse-proxy/index.md) that exposes it.

- [Docker](https://pvliesdonk.github.io/scholar-mcp/unstable/deploy/docker/index.md): the image, Compose, ports, volumes and health checks.
- [systemd and the Linux packages](https://pvliesdonk.github.io/scholar-mcp/unstable/deploy/systemd/index.md): the package's contents and the environment file; the unit's confinement; upgrades.
- [Authentication](https://pvliesdonk.github.io/scholar-mcp/unstable/deploy/authentication/index.md): bearer tokens or OIDC, and when to use which.
- [OIDC](https://pvliesdonk.github.io/scholar-mcp/unstable/deploy/oidc/index.md): which of the two OIDC modes to run, and how to configure it.
- [OIDC providers](https://pvliesdonk.github.io/scholar-mcp/unstable/deploy/oidc-providers/index.md): Authelia, Keycloak, Google, and GitHub through a broker.
- [Reverse proxy](https://pvliesdonk.github.io/scholar-mcp/unstable/deploy/reverse-proxy/index.md): TLS, its own hostname or a path prefix, and the routing OAuth discovery needs.
- [Transfer links](https://pvliesdonk.github.io/scholar-mcp/unstable/deploy/transfer-links/index.md): one-time download and upload URLs, for the person holding one and for the operator.

Before exposing the server, read the [security model](https://pvliesdonk.github.io/scholar-mcp/unstable/security-model/index.md): an authenticated caller has every tool the instance exposes, and under OIDC the identity provider alone decides who gets in.

Scholar MCP needs one writable path, `SCHOLAR_MCP_CACHE_DIR`, for its SQLite cache, downloaded PDFs and converted Markdown. It calls public scholarly APIs over HTTPS and, when configured, a docling-serve for PDF conversion and EPO OPS for patents; the [security model](https://pvliesdonk.github.io/scholar-mcp/unstable/security-model/index.md) lists every service.
