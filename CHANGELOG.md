# CHANGELOG

<!-- version list -->

## v1.2.1 (2026-04-04)

### Bug Fixes

- Add mcp-name to README for MCP registry validation
  ([`469b64c`](https://github.com/pvliesdonk/scholar-mcp/commit/469b64c2b78978ec44ad6e98031c4184b4a8da43))

- Address review — broader exception handling, consistent min_citations check
  ([`1e351e5`](https://github.com/pvliesdonk/scholar-mcp/commit/1e351e5d1521aa342945e7a096d122c7a38e40af))

- Drop strict zip, sync uv.lock, fix release workflow lock regeneration
  ([`876f432`](https://github.com/pvliesdonk/scholar-mcp/commit/876f4327587e7f86ff9dd2d0ea272cffdad8e2f2))

- Resolve seed node metadata, apply filters to references, clean docstrings
  ([`265c51f`](https://github.com/pvliesdonk/scholar-mcp/commit/265c51f2004addaf5ee85837b90fd149b9dd2c1a))

### Chores

- Update server.json to v1.2.0 [skip ci]
  ([`f0a0a5f`](https://github.com/pvliesdonk/scholar-mcp/commit/f0a0a5f49bce3254d1691ceacb075d376d2e0810))


## v1.2.0 (2026-04-04)

### Bug Fixes

- Address PR review comments for remote auth
  ([`1130c2a`](https://github.com/pvliesdonk/scholar-mcp/commit/1130c2a0fc6c7deb715a85010aa58bde68d6fdb4))

- Remove dead warning block, fix docs scope default, fix formatting
  ([`7424634`](https://github.com/pvliesdonk/scholar-mcp/commit/7424634bea5b12a2928194f47badeb0438a08c1f))

- Shorten server.json description to fit MCP registry 100-char limit
  ([`549df65`](https://github.com/pvliesdonk/scholar-mcp/commit/549df650172f81a69e36cb6b492734de9388f9c3))

### Chores

- Update server.json to v1.1.0 [skip ci]
  ([`efba0a1`](https://github.com/pvliesdonk/scholar-mcp/commit/efba0a1af4283884c3e4c72d3184a1ba01367537))

### Features

- Add remote auth mode (RemoteAuthProvider + JWTVerifier)
  ([`31f41ee`](https://github.com/pvliesdonk/scholar-mcp/commit/31f41eec1ca095614cc5348f8355933190be114d))

### Testing

- Add tests for remote auth mode and auth mode resolution
  ([`02b55f3`](https://github.com/pvliesdonk/scholar-mcp/commit/02b55f3afa41b282e6a60e6cae48fd8eaa33c5c8))


## v1.1.0 (2026-04-04)

### Bug Fixes

- Address PR #30 review comments
  ([`99b523d`](https://github.com/pvliesdonk/scholar-mcp/commit/99b523d5e71d7db8d6e2ec3cadb51e0255ab0f86))

- Remove stray superpowers plan files, pin pygments!=2.20.0
  ([`2f93c2a`](https://github.com/pvliesdonk/scholar-mcp/commit/2f93c2a51babd0d8cec7395b1bbddcdb70a94df5))

- Server.json packageArguments --port default must be string
  ([`f3f0316`](https://github.com/pvliesdonk/scholar-mcp/commit/f3f031605de74c93c6330a1e33f903655998dcc9))

### Chores

- Update server.json to v1.0.1 [skip ci]
  ([`5ca8a21`](https://github.com/pvliesdonk/scholar-mcp/commit/5ca8a21e35769711605c0079e39df4cf5062a1a2))

### Documentation

- Add documentation maintenance rule to CLAUDE.md
  ([`e90e783`](https://github.com/pvliesdonk/scholar-mcp/commit/e90e7830eb6db885b5891742f2cf9d1d07aadf2b))

- Address PR review comments
  ([`b5b88be`](https://github.com/pvliesdonk/scholar-mcp/commit/b5b88be44dcb0c876160db63be98ec2eaa50d92c))

- Clarify S2 API key is optional but recommended
  ([`af25966`](https://github.com/pvliesdonk/scholar-mcp/commit/af25966f9bfb034457fed7726d98855698290e77))

- Comprehensive rewrite of README and all documentation
  ([`f576e4a`](https://github.com/pvliesdonk/scholar-mcp/commit/f576e4a842e8e0f634961124e9a3691c18cc0a3a))

- Fix review issues — log message, OIDC vars, VLM prefix, extra name
  ([`f7aea27`](https://github.com/pvliesdonk/scholar-mcp/commit/f7aea279033dd798668abc42ce8bdea9df348bb9))

- Fix tool parameter types and defaults from code review
  ([`0d78c6c`](https://github.com/pvliesdonk/scholar-mcp/commit/0d78c6cbf7143d5c7b83f60b941f2afcb8314080))

### Features

- Add tool annotations, async task queue, and polling tools
  ([`7aa2eed`](https://github.com/pvliesdonk/scholar-mcp/commit/7aa2eed7c70b7912193963819c20089403f68919))

### Testing

- Raise patch coverage to 95%
  ([`c73c177`](https://github.com/pvliesdonk/scholar-mcp/commit/c73c1776433c669df741c8018f18322ad0682532))


## v1.0.1 (2026-04-04)

### Bug Fixes

- Address packaging and workflow review comments
  ([`1bc9726`](https://github.com/pvliesdonk/scholar-mcp/commit/1bc9726fa047130d44d0b4ade56b18b790824bbb))

### Chores

- Adopt workflows and packaging from markdown-mcp template
  ([`b517e01`](https://github.com/pvliesdonk/scholar-mcp/commit/b517e011779abb6b4fc1817fceb7ba198ba864cb))

- Update server.json to v1.0.0 [skip ci]
  ([`fadce9d`](https://github.com/pvliesdonk/scholar-mcp/commit/fadce9de53a3f47acbac78e1c30c5b7e4d8bea31))


## v1.0.0 (2026-04-04)

- Initial Release
