# CHANGELOG

<!-- version list -->

## v1.4.0 (2026-04-05)

### Bug Fixes

- Address Gemini review feedback on citation generation
  ([`d4d48f4`](https://github.com/pvliesdonk/scholar-mcp/commit/d4d48f41d04fa224b31dddb3fa9f22aafef6d23e))

- Address PR #38 review feedback (suffix ordering, URL escaping, archivePrefix casing, parameter
  rename)
  ([`74997f9`](https://github.com/pvliesdonk/scholar-mcp/commit/74997f9b74084392c0943ed2b9e3ac1f5f386458))

- Address PR review — max_nodes early-exit, warning test, comment
  ([`954a1d1`](https://github.com/pvliesdonk/scholar-mcp/commit/954a1d1ed86c63c20bfe25f18d22de07858e1e81))

- Address PR review — pagination, metadata stripping, null guard
  ([`dff1b8d`](https://github.com/pvliesdonk/scholar-mcp/commit/dff1b8d88f71b41cca69a8890268a11a9531e475))

- Address review feedback for BibTeX formatter
  ([`74200eb`](https://github.com/pvliesdonk/scholar-mcp/commit/74200eb768a993e7d9fffb0cd819c88792f9e9db))

- Address review feedback for citation formatter helpers
  ([`747dfdc`](https://github.com/pvliesdonk/scholar-mcp/commit/747dfdc30098b5e419e09388e26cf7ad0b87ff64))

- Address review feedback for citation tool
  ([`2079f9e`](https://github.com/pvliesdonk/scholar-mcp/commit/2079f9e04a58d6759462b0e115242793e7fd9aae))

- Address review feedback for name parser
  ([`a20f723`](https://github.com/pvliesdonk/scholar-mcp/commit/a20f72386556a93272232c686d6414e09f1718cc))

- Bound concurrent OpenAlex enrichment with semaphore
  ([`91341b5`](https://github.com/pvliesdonk/scholar-mcp/commit/91341b56499f5bc116b0177248d487eb638ba54c))

- Handle null S2 data and add client-side min_citations filter to get_citations
  ([`b98c597`](https://github.com/pvliesdonk/scholar-mcp/commit/b98c59745356ad70cde3c630e5593acbb0debf68))

- Paginate S2 citations when min_citations filter is active
  ([`63614a3`](https://github.com/pvliesdonk/scholar-mcp/commit/63614a3f696ef9644b8b73ce6f7bb66aee88edaf))

### Chores

- Update server.json and uv.lock to v1.3.0 [skip ci]
  ([`e997ab2`](https://github.com/pvliesdonk/scholar-mcp/commit/e997ab2c6ab69169fe8ba247d591ce23cecb698a))

### Code Style

- Fix ruff formatting in test_tools_graph.py
  ([`166269b`](https://github.com/pvliesdonk/scholar-mcp/commit/166269b5b2fc12809055c9c8e0dbc249c73f0c70))

### Documentation

- Add generate_citations tool documentation
  ([`f26e924`](https://github.com/pvliesdonk/scholar-mcp/commit/f26e924e3249aa64477981c345d49c7d099b49f9))

- Add high-citation seed paper advisory to graph tool docstrings
  ([`36a85cb`](https://github.com/pvliesdonk/scholar-mcp/commit/36a85cb9ebd8806563bb1c4eaf079297415e9442))

- Fix parameter name in generate_citations docs (format -> citation_format)
  ([`4ad1481`](https://github.com/pvliesdonk/scholar-mcp/commit/4ad1481519cc4aeea12be6b4d3dbd7bc3fbc5d3c))

### Features

- Add author name parser for citation formatting
  ([`b232200`](https://github.com/pvliesdonk/scholar-mcp/commit/b2322007d461a1e6e8afb9c8a2d2dd6f6fcbfafa))

- Add BibTeX citation formatter
  ([`4954695`](https://github.com/pvliesdonk/scholar-mcp/commit/495469586940d99473b32ffb54e71047cbbb1bca))

- Add BibTeX key generation, type inference, and escaping
  ([`b34c63b`](https://github.com/pvliesdonk/scholar-mcp/commit/b34c63b9c9c24e46701ee8fec0623cac4fe324e7))

- Add CSL-JSON citation formatter
  ([`96998ef`](https://github.com/pvliesdonk/scholar-mcp/commit/96998efb74e996508b82156f4af00a80a3a03e4b))

- Add generate_citations MCP tool
  ([`00adb81`](https://github.com/pvliesdonk/scholar-mcp/commit/00adb8192764e0ed7e199a3167e663891e2b227d))

- Add RIS citation formatter
  ([`55f5c0b`](https://github.com/pvliesdonk/scholar-mcp/commit/55f5c0bdc282d23ee99863ed8866020c33a19f2d))


## v1.3.0 (2026-04-05)

### Bug Fixes

- Apply min_citations filter client-side for citations in graph BFS
  ([`123b92e`](https://github.com/pvliesdonk/scholar-mcp/commit/123b92ee80c475fc38cda6395002255b7f3b4d6f))

- Broaden client-filter check, add null citationCount test
  ([`1bb7c16`](https://github.com/pvliesdonk/scholar-mcp/commit/1bb7c16f59d73ce068bbf517533a936726d8f5e3))

- Expose VLM skip reason instead of silent fallback
  ([`3306b09`](https://github.com/pvliesdonk/scholar-mcp/commit/3306b09a8113a1c2aee6d1771358d7e603fd746b))

- Fetch larger candidate pool when client-side filters are active
  ([`4758126`](https://github.com/pvliesdonk/scholar-mcp/commit/47581263bef407f9ee697050b56717278696b3db))

- Remove misleading minCitationCount param from S2 citations client
  ([`27d825a`](https://github.com/pvliesdonk/scholar-mcp/commit/27d825ab60e1f3b05b8fe99a965a48d5e098ee12))

- Resolve CI lint and type check failures
  ([`4e06568`](https://github.com/pvliesdonk/scholar-mcp/commit/4e06568e76eb2c195230cf53bdf2d0c25c7c19fb))

- Return None from vlm_skip_reason when VLM not requested; add skip_reason to cache-hit path
  ([`d7d7320`](https://github.com/pvliesdonk/scholar-mcp/commit/d7d732086e3c522c095e8508e799ab1317bcc11a))

- Use separate cache paths for VLM vs standard markdown conversion
  ([`31db91d`](https://github.com/pvliesdonk/scholar-mcp/commit/31db91d92cba1a5a9532a04a817efd8b9238bf08))

### Chores

- Update server.json and uv.lock to v1.2.2 [skip ci]
  ([`3a1f4a7`](https://github.com/pvliesdonk/scholar-mcp/commit/3a1f4a7d2d86b4e4a948359c4f8be637d8df7bba))

### Documentation

- Document VLM caching convention and recommend standard-first usage
  ([`5f6f641`](https://github.com/pvliesdonk/scholar-mcp/commit/5f6f64145b1c0ae67d9ae6c66a1b03e650389508))

### Features

- Add elapsed time and duration hints to task poll responses
  ([`673ed5f`](https://github.com/pvliesdonk/scholar-mcp/commit/673ed5f02763ad8f7b8fdcc51571cbd1f312e9b2))

### Testing

- Add coverage for vlm_skip_reason and task poll context fields
  ([`4627c25`](https://github.com/pvliesdonk/scholar-mcp/commit/4627c25add3e2941bf9b28c4eef1a685128e6aef))

- Add unit tests for vlm_skip_reason and VLM-not-configured cache/non-cache paths
  ([`4e56e0d`](https://github.com/pvliesdonk/scholar-mcp/commit/4e56e0daadb1aaaae29a3dffa969958b90aec0c6))


## v1.2.2 (2026-04-04)

### Bug Fixes

- Remove broken citingPaper/citedPaper field prefix from S2 client
  ([`d210cac`](https://github.com/pvliesdonk/scholar-mcp/commit/d210cacca02e83fae502cbd0db8205ed9d65ac6e))

### Chores

- Update server.json and uv.lock to v1.2.1 [skip ci]
  ([`23e28f2`](https://github.com/pvliesdonk/scholar-mcp/commit/23e28f22de10ee17af42a1414054f19230866615))


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
