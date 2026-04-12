# CHANGELOG

<!-- version list -->

## v1.7.0-rc.1 (2026-04-12)

### Bug Fixes

- Add missing tools and correct VLM scope in SKILL.md
  ([`97b0748`](https://github.com/pvliesdonk/scholar-mcp/commit/97b074879e3b9a731ea92f7ebbbc9ecf1421ac58))

- Add VLM vars to plugin README, test assertions, tighter validation
  ([`3dce50c`](https://github.com/pvliesdonk/scholar-mcp/commit/3dce50c0235de6619ff50b83d96605dd8ea5b723))

- Address all PR #97 review issues
  ([`8097296`](https://github.com/pvliesdonk/scholar-mcp/commit/8097296ebba82464bc31b9647eb95a5034d73782))

- Address PR #95 review — typing, regex, and test coverage
  ([`0402770`](https://github.com/pvliesdonk/scholar-mcp/commit/0402770b29af2e73dd80723f62669bed009ed9fe))

- Address PR #96 review — bugs, performance, race conditions
  ([`5aaad33`](https://github.com/pvliesdonk/scholar-mcp/commit/5aaad33488ad091a528359185ce5f64971802f1f))

- Address PR review — always() on save/upload, graceful artifact download
  ([`0bfa2bf`](https://github.com/pvliesdonk/scholar-mcp/commit/0bfa2bfd68dcb1edcb65e17aabf466a1ae2e7845))

- Address PR review — consolidate Papers sections, add fetch_patent_pdf
  ([`88f5944`](https://github.com/pvliesdonk/scholar-mcp/commit/88f5944309c0d8fe012e60cd4146627d4de91615))

- Address PR review — env expansion, test logic, docs, workflow
  ([`13b6ecd`](https://github.com/pvliesdonk/scholar-mcp/commit/13b6ecd988fba32997dda290a6ce8da6b11d4485))

- Address PR review — improve prerelease docs and configurable token
  ([`188b3b2`](https://github.com/pvliesdonk/scholar-mcp/commit/188b3b2cc326398a56d7e0c8c64d992b00722ed8))

- Address PR review — propagate guard, traceback conditional, test fixes
  ([`583f2ef`](https://github.com/pvliesdonk/scholar-mcp/commit/583f2efa7ae98d7d9844dd303ce227523e7fb0d2))

- Address PR review — throttle cache fallback, black pre-flight, lint, type check
  ([`ce7a21e`](https://github.com/pvliesdonk/scholar-mcp/commit/ce7a21e08fad24ec0f1a7b96ccacf0b39882655e))

- Address remaining nits — capitalisation and Patents bullet
  ([`579dfe9`](https://github.com/pvliesdonk/scholar-mcp/commit/579dfe9171ee7cf8becbb8510a8d8b179eea295a))

- Address round-2 review comments
  ([`2582edf`](https://github.com/pvliesdonk/scholar-mcp/commit/2582edf2f786b52bd82d4ca7dfadf41611d03c0d))

- BCP/STD/FYI canonical identifier format, NIST double-checked locking
  ([`ea26432`](https://github.com/pvliesdonk/scholar-mcp/commit/ea26432e5f0767198c2fc2b07bca6451a2f18252))

- Complete queued operations list and note cache-hit fast path
  ([`3a93cde`](https://github.com/pvliesdonk/scholar-mcp/commit/3a93cde2d6a6859e80608e2a9948a525a352fac5))

- Correct get_standard queueing behaviour in SKILL.md
  ([`9d01d0b`](https://github.com/pvliesdonk/scholar-mcp/commit/9d01d0b8574ac7c4d4fac0282d2ebe72a13b572c))

- Correct queued response shape and duration estimates in SKILL.md
  ([`e640083`](https://github.com/pvliesdonk/scholar-mcp/commit/e64008371052e3dbad4749ef415e0c00269f489f))

- EPO search bugs — 404 no-results, idle throttle, within date syntax, optional query, inventor-only
  search
  ([`f0d6a26`](https://github.com/pvliesdonk/scholar-mcp/commit/f0d6a260fc34823d73213e2cb3cca0eeb0001d58))

- Guard NIST catalogue against empty parse result and add in-memory cache test
  ([`0857b4c`](https://github.com/pvliesdonk/scholar-mcp/commit/0857b4c704170edbfdc15f87cfd6b9c4707f733f))

- Remove duplicate BCP/STD resolver tests
  ([`9fa0f57`](https://github.com/pvliesdonk/scholar-mcp/commit/9fa0f5773b3ea9cd9960555697c93d5bc882776d))

- Remove stale type: ignore comments after StandardRecord typing upgrade
  ([`783fd37`](https://github.com/pvliesdonk/scholar-mcp/commit/783fd37095afb388f02755a4aaed811734657383))

- Replace dead NIST JSON endpoint with MODS XML from GitHub releases (#100)
  ([#100](https://github.com/pvliesdonk/scholar-mcp/pull/100),
  [`8f54959`](https://github.com/pvliesdonk/scholar-mcp/commit/8f54959bb6d942a809386a3cd91d627a811638d9))

- Replace ETSI HTML scraper with Joomla JSON API endpoint (#102)
  ([#102](https://github.com/pvliesdonk/scholar-mcp/pull/102),
  [`5193cf1`](https://github.com/pvliesdonk/scholar-mcp/commit/5193cf1d78f96c10d8a0820722552ab867be8626))

- Replace substring URL checks in tests with startswith (CodeQL)
  ([`5487ce9`](https://github.com/pvliesdonk/scholar-mcp/commit/5487ce97f4eaea99423a4bd6fab77ccff9edb273))

- Rewrite W3C fetcher to use _links.specifications and client-side search (#101)
  ([#101](https://github.com/pvliesdonk/scholar-mcp/pull/101),
  [`cb5b2bd`](https://github.com/pvliesdonk/scholar-mcp/commit/cb5b2bd98f117b63a7c74cdada8664528bdfe9a0))

- Sync SCHOLAR_MCP_LOG_LEVEL to FASTMCP_LOG_LEVEL
  ([`3a48480`](https://github.com/pvliesdonk/scholar-mcp/commit/3a48480677f4f5e2449839feffcc694eb30baaba))

- Use steps.download.outcome instead of success() for artifact guard
  ([`937defe`](https://github.com/pvliesdonk/scholar-mcp/commit/937defe364f270c032fd853e6c702a6bb297ed51))

- W3C empty-results falsy bug, dead committee branch, and coverage
  ([`4b85f34`](https://github.com/pvliesdonk/scholar-mcp/commit/4b85f341c41bf650ab403af79a04cc36f79aaa13))

### Chores

- Clarify ruff lint order in CLAUDE.md gates
  ([`80b09cb`](https://github.com/pvliesdonk/scholar-mcp/commit/80b09cb218d65c363c8f39708ceaa89f87e88200))

- Fix ruff format on _protocols.py and _standards_client.py
  ([`733cbc5`](https://github.com/pvliesdonk/scholar-mcp/commit/733cbc5c59a9f9846b1a461e7018b8cb92846708))

- Fix ruff format on _standards_client.py
  ([`a75376a`](https://github.com/pvliesdonk/scholar-mcp/commit/a75376ab3505abb1c2eaa8319a2d2bbe20360aab))

- Fix ruff format on test_tools_standards.py
  ([`75ba486`](https://github.com/pvliesdonk/scholar-mcp/commit/75ba4869762426683124f9365a0fae1cb58a4d51))

- Fix ruff format on tools branch
  ([`790db54`](https://github.com/pvliesdonk/scholar-mcp/commit/790db5484040827639b5576f8f24fc173c2a4c20))

- Trigger CI
  ([`c378a27`](https://github.com/pvliesdonk/scholar-mcp/commit/c378a27ac87285702f7593c1603e68547112113c))

- Update server.json and uv.lock to v1.6.0 [skip ci]
  ([`cb16e35`](https://github.com/pvliesdonk/scholar-mcp/commit/cb16e351ed2b5afcca8d2d250cdba00f51d84ccc))

- **deps**: Bump cryptography from 46.0.6 to 46.0.7
  ([`9ba4bfe`](https://github.com/pvliesdonk/scholar-mcp/commit/9ba4bfef43049b7b186cb5cbc4de5a9ef61c2010))

### Continuous Integration

- Post codecov/patch status for fork PRs via workflow_run
  ([`591c160`](https://github.com/pvliesdonk/scholar-mcp/commit/591c160863304f7b0fcab4fa065650d748b90ac4))

### Documentation

- Add fetch_patent_pdf to README tool table and READ_ONLY note
  ([`bc22262`](https://github.com/pvliesdonk/scholar-mcp/commit/bc22262f0fe84200f7a53a56cf1fa3d3cbae2873))

- Add logging standard to CLAUDE.md
  ([`4b50302`](https://github.com/pvliesdonk/scholar-mcp/commit/4b5030206e8c55b1a21544b070617083ce7142ca))

- Add standards support design spec (v0.8.0)
  ([`8951391`](https://github.com/pvliesdonk/scholar-mcp/commit/89513913e90270b0ee09f58b710299ec7aaedd3b))

- Add standards support implementation plan (v0.8.0)
  ([`a222653`](https://github.com/pvliesdonk/scholar-mcp/commit/a222653bb7137f811b9e8b557ac25e64df3c80cc))

- Add transparent rate-limiting note to patent tool descriptions
  ([`c377544`](https://github.com/pvliesdonk/scholar-mcp/commit/c3775449093db261e8a28188bfd35fc25c1bc69a))

- Document SCHOLAR_MCP_LOG_FORMAT env var
  ([`86a6239`](https://github.com/pvliesdonk/scholar-mcp/commit/86a6239d95b43046efa41ede473c48a96c097649))

- Document standards tools (search_standards, get_standard, resolve_standard_identifier)
  ([`75f4fc7`](https://github.com/pvliesdonk/scholar-mcp/commit/75f4fc744da418cea993959e4402b8ebad49b89f))

- Implementation plan for EPO per-service throttle and LLM retry guidance
  ([`54b19f1`](https://github.com/pvliesdonk/scholar-mcp/commit/54b19f1d0008bf309ef5ee8fcb19ff18b97270fd))

- Reposition scholar-mcp as a scholarly-sources MCP server
  ([`8dbf918`](https://github.com/pvliesdonk/scholar-mcp/commit/8dbf918d78a1d3f29166fcc5b64b3f4918e3267a))

- Spec for EPO per-service throttle and LLM retry guidance
  ([`59a5ef9`](https://github.com/pvliesdonk/scholar-mcp/commit/59a5ef9ceaeea5590533531c18a80a69f5487b43))

- Update EPO throttle spec with concrete retry times and consistent messaging
  ([`729b58b`](https://github.com/pvliesdonk/scholar-mcp/commit/729b58bb98aaa24c40c19d543dfc0a20c56c62bb))

### Features

- Add _parse_throttle_header for per-service throttle parsing
  ([`dca5fa2`](https://github.com/pvliesdonk/scholar-mcp/commit/dca5fa278ca3563e23bffd445b6e3a562dbec339))

- Add Claude Code plugin and mcpb bundle distribution
  ([`a1c55ee`](https://github.com/pvliesdonk/scholar-mcp/commit/a1c55ee8818e60fd7f178ddcc2ae49954d0bec83))

- Add debug logging to rate-limit queueing in all tools
  ([`68b5150`](https://github.com/pvliesdonk/scholar-mcp/commit/68b51504b2cd24d05314c33ee4256e1c19b596bb))

- Add EpoRateLimitedError.service, throttle cache, and pre-flight check on search()
  ([`e88f56e`](https://github.com/pvliesdonk/scholar-mcp/commit/e88f56e36d9733974bc5d95edb27643cec6c5db4))

- Add ETSI source fetcher with in-memory catalogue index
  ([`7d28aa9`](https://github.com/pvliesdonk/scholar-mcp/commit/7d28aa9eea4be9be68e3affbd0d27521caa3efb0))

- Add fetch_patent_pdf tool with authenticated EPO download + URL interception (#103)
  ([#103](https://github.com/pvliesdonk/scholar-mcp/pull/103),
  [`c3fd2fe`](https://github.com/pvliesdonk/scholar-mcp/commit/c3fd2feac6f17a44284cfb405593284950152043))

- Add IETF RFC source fetcher
  ([`cb8944c`](https://github.com/pvliesdonk/scholar-mcp/commit/cb8944c8221bb4422d28d3b0cb821a588bfb4f3d))

- Add NIST CSRC source fetcher
  ([`ee18b8e`](https://github.com/pvliesdonk/scholar-mcp/commit/ee18b8e1d21b254da0a63eda74f48d6e4f873f8a))

- Add per-service color check to _check_throttle
  ([`77bd254`](https://github.com/pvliesdonk/scholar-mcp/commit/77bd2541b1ce13acef521d95d20b92871866bbb6))

- Add pre-flight throttle check and per-service _check_throttle to all EpoClient methods
  ([`3a52c11`](https://github.com/pvliesdonk/scholar-mcp/commit/3a52c1129288121d4360104dd98298d297548604))

- Add resolve_standard_identifier tool
  ([`d135c5c`](https://github.com/pvliesdonk/scholar-mcp/commit/d135c5c742cf7d2ce652c995a5a2295165d2b785))

- Add scholar-workflow SKILL.md with tool guidance
  ([`d52c313`](https://github.com/pvliesdonk/scholar-mcp/commit/d52c313d996dae6ec2ba6ade0bdaeef9b4ed5455))

- Add SCHOLAR_MCP_LOG_FORMAT config field
  ([`f97ce30`](https://github.com/pvliesdonk/scholar-mcp/commit/f97ce30e25351e37803b90ac6c78caa7bb34d78b))

- Add StandardRecord TypedDict and standards cache tables
  ([`8307d73`](https://github.com/pvliesdonk/scholar-mcp/commit/8307d73b06965a92f57e5b912a4c42439673df75))

- Add standards identifier resolver with Tier 1 regex patterns
  ([`6137180`](https://github.com/pvliesdonk/scholar-mcp/commit/6137180081a860e956302cce7bfeb6ee668c12ee))

- Add StandardsClient and wire into ServiceBundle
  ([`bd2621a`](https://github.com/pvliesdonk/scholar-mcp/commit/bd2621a58f8a01c09e7a352ff1ba58a5d914eb06))

- Add W3C specification source fetcher
  ([`c41d465`](https://github.com/pvliesdonk/scholar-mcp/commit/c41d46507c0c0c8821e989a77973fe54b6ff7172))

- Implement full-text docling conversion in get_standard
  ([`18ce246`](https://github.com/pvliesdonk/scholar-mcp/commit/18ce2468a485dbb626d6c0d52d47ccb94b15fbcc))

- Sanitise rate-limit errors in get_task_result and add patent duration hints
  ([`642ef1d`](https://github.com/pvliesdonk/scholar-mcp/commit/642ef1dcf463f3c427a429932c8b6705198e0fbf))

- Wire FastMCP logging, timing, and error middleware
  ([`1207640`](https://github.com/pvliesdonk/scholar-mcp/commit/12076400a8c7e67d6dda9ce4f518b466d51e9989))

- **ci**: Add prerelease mode to release workflow
  ([`6d66a3e`](https://github.com/pvliesdonk/scholar-mcp/commit/6d66a3ecac7609b084ebbfc8ab9a7d9665b96b83))

### Refactoring

- Replace SCHOLAR_MCP_LOG_LEVEL/LOG_FORMAT with FastMCP vars
  ([`d45c850`](https://github.com/pvliesdonk/scholar-mcp/commit/d45c85035f0df6c61d58f2f2212dd038cae1563a))

- Use FastMCP configure_logging for uniform log output
  ([`2165955`](https://github.com/pvliesdonk/scholar-mcp/commit/2165955140f0d98f77135b22da76ded6f2b84b7a))

### Testing

- Add BCP and STD resolver coverage for IETF patterns
  ([`8abe778`](https://github.com/pvliesdonk/scholar-mcp/commit/8abe778ddc6207d23d7315f46790524ec3524af0))

- Add search_standards and get_standard tool tests
  ([`acf110d`](https://github.com/pvliesdonk/scholar-mcp/commit/acf110d91f8e7eb68c6cd0b84bf5a6fa3fef11f8))

- Cover all _tools_standards branches; add PR gates to CLAUDE.md
  ([`3952989`](https://github.com/pvliesdonk/scholar-mcp/commit/3952989d8f0370b1197879a4785d110972079f19))

- Cover BCP, STD, NIST bare number, and WebAuthn resolver branches
  ([`afff8f5`](https://github.com/pvliesdonk/scholar-mcp/commit/afff8f559c91d2512f2c571bc95d1eadb4a94ccb))

- Cover black pre-flight, _overall fallback, and ValueError in search_patents
  ([`bc0b228`](https://github.com/pvliesdonk/scholar-mcp/commit/bc0b228d7aea787fb796c67fd4216accc7bdbf11))

- Cover docling and NIST branches to reach 80% patch coverage
  ([`b6eb5ca`](https://github.com/pvliesdonk/scholar-mcp/commit/b6eb5ca7ef3a7602e6e71c355ac9bb12d2a7f33b))

- Cover remaining pre-flight branches for all retrieval and inpadoc methods
  ([`e8d2ef7`](https://github.com/pvliesdonk/scholar-mcp/commit/e8d2ef7522260dc62db601b2404e2a70dd5c9c35))

- Raise patch coverage above 80% for PR review fixes
  ([`347d8c2`](https://github.com/pvliesdonk/scholar-mcp/commit/347d8c22764b641560c782aa4692f660f503bcf8))


## v1.6.0 (2026-04-07)

### Bug Fixes

- Address PR #76 review feedback — imports, annotations, coverage
  ([`5796ce4`](https://github.com/pvliesdonk/scholar-mcp/commit/5796ce4b2707f979681c11c552e65de4efd4a16d))

- Address PR #78 review feedback
  ([`5a75767`](https://github.com/pvliesdonk/scholar-mcp/commit/5a7576785b2bd23e421c82cd2eeb674881bbbf56))

- Ruff format _book_enrichment.py
  ([`1151aa7`](https://github.com/pvliesdonk/scholar-mcp/commit/1151aa773d4a13f2ff480db059842949455b040b))

- Ruff format _tools_books.py line length
  ([`a8921d3`](https://github.com/pvliesdonk/scholar-mcp/commit/a8921d36c9556b1ea9ca373eb9e88f7882d5feac))

- Sort recommend_books by edition_count, include limit in cache key
  ([`90f5069`](https://github.com/pvliesdonk/scholar-mcp/commit/90f5069134e4b891ae2d5fa3487b15ff3f0862cb))

- Suppress venue tags for @book entries in CSL-JSON and RIS (#65)
  ([#65](https://github.com/pvliesdonk/scholar-mcp/pull/65),
  [`1e5e8c9`](https://github.com/pvliesdonk/scholar-mcp/commit/1e5e8c968bd8f5bf273ee96c0c2a0708eb9679ba))

- Use _format_bibtex_author for book author fallback
  ([`122569d`](https://github.com/pvliesdonk/scholar-mcp/commit/122569de98b79fc86d3a0c0956e7e7cbb2b67634))

### Chores

- Update server.json and uv.lock to v1.5.0 [skip ci]
  ([`0ff41ca`](https://github.com/pvliesdonk/scholar-mcp/commit/0ff41cacae6d79e3c77f2386128aa9ab30e43538))

### Documentation

- Add authors field to book_metadata enrichment table (#74)
  ([#74](https://github.com/pvliesdonk/scholar-mcp/pull/74),
  [`3fced7f`](https://github.com/pvliesdonk/scholar-mcp/commit/3fced7f3b73fc3c29690ae690d4cf6ccd2b96f5c))

- Add recommend_books tool documentation (#69)
  ([#69](https://github.com/pvliesdonk/scholar-mcp/pull/69),
  [`85bf04a`](https://github.com/pvliesdonk/scholar-mcp/commit/85bf04ae03dc433ae4e645e0645bcea24f957c42))

- Document @book citation output in generate_citations (#65)
  ([#65](https://github.com/pvliesdonk/scholar-mcp/pull/65),
  [`c8dd33d`](https://github.com/pvliesdonk/scholar-mcp/commit/c8dd33d998f021ab1b394e08e80d0fd9574f6928))

- Fix stale cache-key description for recommend_books
  ([`5e5d982`](https://github.com/pvliesdonk/scholar-mcp/commit/5e5d982b981da2ec581be7d348ef51ecd50cdc08))

### Features

- Add book subject cache methods (#69) ([#69](https://github.com/pvliesdonk/scholar-mcp/pull/69),
  [`39f4710`](https://github.com/pvliesdonk/scholar-mcp/commit/39f4710dedaf96780a9c0a519c9d5b2932fb2a1a))

- Add OpenLibraryClient.get_author() (#74)
  ([#74](https://github.com/pvliesdonk/scholar-mcp/pull/74),
  [`0581929`](https://github.com/pvliesdonk/scholar-mcp/commit/058192914d9a88519bf5ea6d4e49b51b16475988))

- Add OpenLibraryClient.get_subject() (#69)
  ([#69](https://github.com/pvliesdonk/scholar-mcp/pull/69),
  [`239c27f`](https://github.com/pvliesdonk/scholar-mcp/commit/239c27ff6ddb4d9eb4884d38c753f39fb70eac10))

- Add recommend_books tool via Open Library subject API (#69)
  ([#69](https://github.com/pvliesdonk/scholar-mcp/pull/69),
  [`0e49719`](https://github.com/pvliesdonk/scholar-mcp/commit/0e49719d9fd1949d5f9f3cde7a03b805d0ec3ee8))

- Add subject normalization and subject work → BookRecord (#69)
  ([#69](https://github.com/pvliesdonk/scholar-mcp/pull/69),
  [`e6a6b1e`](https://github.com/pvliesdonk/scholar-mcp/commit/e6a6b1e2f6efffadbce5561e25c35d20d7164ad8))

- Detect @book entry type from book_metadata (#65)
  ([#65](https://github.com/pvliesdonk/scholar-mcp/pull/65),
  [`c0846c6`](https://github.com/pvliesdonk/scholar-mcp/commit/c0846c6a60a784aeb5e4c52c9e7c58cb3c8fa423))

- Emit @book BibTeX entries with publisher/edition/isbn (#65)
  ([#65](https://github.com/pvliesdonk/scholar-mcp/pull/65),
  [`e60b6ea`](https://github.com/pvliesdonk/scholar-mcp/commit/e60b6eaba1ae38bf79b12117e50d3dc9ddc327d7))

- Emit book type in CSL-JSON with publisher/ISBN (#65)
  ([#65](https://github.com/pvliesdonk/scholar-mcp/pull/65),
  [`ee6b4c6`](https://github.com/pvliesdonk/scholar-mcp/commit/ee6b4c682b857a93236fd5795c4a8c06d8e396ce))

- Emit BOOK type in RIS with publisher/ISBN (#65)
  ([#65](https://github.com/pvliesdonk/scholar-mcp/pull/65),
  [`ecdd0c1`](https://github.com/pvliesdonk/scholar-mcp/commit/ecdd0c1c210ff1af5c41ae7846c7b90f9c4a7a71))

- Enrich edition and work lookups with author names (#74)
  ([#74](https://github.com/pvliesdonk/scholar-mcp/pull/74),
  [`8742a71`](https://github.com/pvliesdonk/scholar-mcp/commit/8742a7107b1047ee5b85b20e83fa79bbba30e596))

- Enrich ISBN book results with authors from work (#74)
  ([#74](https://github.com/pvliesdonk/scholar-mcp/pull/74),
  [`e49cba1`](https://github.com/pvliesdonk/scholar-mcp/commit/e49cba1db854f0e3914138211c4fe839f0facf32))

- Include authors in book enrichment metadata (#74)
  ([#74](https://github.com/pvliesdonk/scholar-mcp/pull/74),
  [`f7156c5`](https://github.com/pvliesdonk/scholar-mcp/commit/f7156c5402204528b7cc92505c01bacbe7b50bb4))

### Refactoring

- Move author enrichment helpers to _book_enrichment.py
  ([`f57c7d0`](https://github.com/pvliesdonk/scholar-mcp/commit/f57c7d0ca6568bc355f12355923504bfb62396ff))

### Testing

- Cover CSL/RIS author prefix+suffix branches, fix mypy errors
  ([`13ff13f`](https://github.com/pvliesdonk/scholar-mcp/commit/13ff13f1c8aa9b78a0ea72ee39a9b8d0e31ef0fc))

- Improve _book_enrichment branch coverage to 100% patch
  ([`9c4736b`](https://github.com/pvliesdonk/scholar-mcp/commit/9c4736b2fbd7cffa382311e8d187b1b1fb3d3142))


## v1.5.0 (2026-04-06)

### Bug Fixes

- Address CI failures and second-round review feedback
  ([`b69d5db`](https://github.com/pvliesdonk/scholar-mcp/commit/b69d5db48f665782939025ade2686747cc22e6c5))

- Address PR #54 review feedback
  ([`58a0d4b`](https://github.com/pvliesdonk/scholar-mcp/commit/58a0d4bf8b1e0aab44c2c7e6f949156448502972))

- Address PR #57 review feedback (caching, imports, rate limits, formatting)
  ([`38122ec`](https://github.com/pvliesdonk/scholar-mcp/commit/38122ec81b568ece73eaf1989befaa44dee3ffb0))

- Address PR #58 review feedback
  ([`cbd17ce`](https://github.com/pvliesdonk/scholar-mcp/commit/cbd17ce5d5ed0a9b471a079cf1bfc3842fb802a7))

- Address PR #71 review feedback
  ([`2fd70fd`](https://github.com/pvliesdonk/scholar-mcp/commit/2fd70fded70cf0a88939ae72c1126857db9688bd))

- Address PR #73 review feedback
  ([`c82df24`](https://github.com/pvliesdonk/scholar-mcp/commit/c82df244ad247391b4fb4f4a3bac386919be29fa))

- Address PR review feedback (CQL escaping, cache key, number validation, throttle parsing)
  ([`ba27156`](https://github.com/pvliesdonk/scholar-mcp/commit/ba27156e40877e18b34b8776971b807c8d546742))

- Address PR review feedback (test fixture, section notices, empty biblio, result mutation)
  ([`838d660`](https://github.com/pvliesdonk/scholar-mcp/commit/838d660a47d569ddb086b63ee1eaff7ea85d2421))

- Improve book search quality, ISBN redirect, batch_resolve ISBN routing
  ([`06068d6`](https://github.com/pvliesdonk/scholar-mcp/commit/06068d6b112d4c49c945c50d86e9fb7121610b48))

- Re-raise RateLimitedError in NPL resolution, preserve DOI on failure, add rate-limit queue test
  ([`5b5250f`](https://github.com/pvliesdonk/scholar-mcp/commit/5b5250fdcc7d98bc52099ee6885e069f21ffced6))

- Replace URL substring check with exact match to resolve CodeQL alert
  ([`e0f0093`](https://github.com/pvliesdonk/scholar-mcp/commit/e0f00932468cc5df19294bdba1a5ab385f3f87c6))

- Resolve CodeQL taint-flow alert and remaining ruff formatting
  ([`88e5576`](https://github.com/pvliesdonk/scholar-mcp/commit/88e5576359a8049705fa6eccc11ce314ca9307e7))

- Resolve mypy error in _download dl_url type annotation
  ([`44d98be`](https://github.com/pvliesdonk/scholar-mcp/commit/44d98be68b55f611eb08d57b31431999854c4510))

- Resolve mypy errors in enrichment hooks, add coverage tests for book tools
  ([`1142009`](https://github.com/pvliesdonk/scholar-mcp/commit/114200995d0b67ae612a768842a577ad64c1aedb))

- Ruff format _cache.py, restore test function name prefixes
  ([`1720be4`](https://github.com/pvliesdonk/scholar-mcp/commit/1720be4ab0900715aedcb5f39d7e8ce2d3ffaaf0))

- Tighten DOI regex rstrip and document S2 re-resolution trade-off
  ([`27ab207`](https://github.com/pvliesdonk/scholar-mcp/commit/27ab207e0d3e76cfa31a67599f59cb2009d8d7ef))

- Update epo_xml docstring and add description multilingual tests
  ([`433c051`](https://github.com/pvliesdonk/scholar-mcp/commit/433c051648e9a1cf8531d0a8a7e70447b7c171aa))

### Chores

- Add python-epo-ops-client and lxml dependencies
  ([`e5e1de6`](https://github.com/pvliesdonk/scholar-mcp/commit/e5e1de69e795f8117fb855afe0ed5bc997a26ddb))

- Ignore worktrees directory in .gitignore
  ([`3219a93`](https://github.com/pvliesdonk/scholar-mcp/commit/3219a9336367608059d078b866a297386127604d))

- Remove accidentally staged worktree reference
  ([`0fd7f4c`](https://github.com/pvliesdonk/scholar-mcp/commit/0fd7f4cfc04a8b85ba7ff59e44ba7f3bd5c40891))

- Update server.json and uv.lock to v1.4.0 [skip ci]
  ([`054c9ca`](https://github.com/pvliesdonk/scholar-mcp/commit/054c9ca6f433e9619f7952865a20a51aa2799f24))

### Documentation

- Add book support design spec
  ([`2176c85`](https://github.com/pvliesdonk/scholar-mcp/commit/2176c8512beaca65dcb24e3af5886a81a96a43a2))

- Add book support implementation plan
  ([`5e6cca7`](https://github.com/pvliesdonk/scholar-mcp/commit/5e6cca7748876a435256c4172a3c74341b018751))

- Add patent extension design spec
  ([`c4e01ec`](https://github.com/pvliesdonk/scholar-mcp/commit/c4e01ec68154651b067bab8f38d4cb2012bbddf5))

- Add patent extension implementation plan
  ([`9fd4e2d`](https://github.com/pvliesdonk/scholar-mcp/commit/9fd4e2d4b73f2d3ab76d64253be58b8accd34e15))

- Add patent tools and EPO configuration documentation
  ([`d991d83`](https://github.com/pvliesdonk/scholar-mcp/commit/d991d836faafd6f14f7ac9ff42c58a25d54c6b5c))

- Add Phase 3 cross-referencing documentation
  ([`85acccc`](https://github.com/pvliesdonk/scholar-mcp/commit/85acccc2e734405fb09161fd904ba5137be8ca04))

- Add search_books, get_book, and auto-enrichment documentation
  ([`0b772d0`](https://github.com/pvliesdonk/scholar-mcp/commit/0b772d05f9e4b320e49609818aca0570a7acda96))

- Fix spec inconsistency and add issue references
  ([`7944630`](https://github.com/pvliesdonk/scholar-mcp/commit/79446301df76e751d217b2be02ae1d6461f802d1))

- Update get_patent documentation with all available sections
  ([`b3ec169`](https://github.com/pvliesdonk/scholar-mcp/commit/b3ec1696394ca37823317cd7ce410b444d06ee47))

- Update README, docs index, and configuration for alternative PDF sources
  ([`771060f`](https://github.com/pvliesdonk/scholar-mcp/commit/771060fc77354d024468cbc66aa4734ac3c45d68))

- Update search_books and batch_resolve documentation
  ([`b0c3bee`](https://github.com/pvliesdonk/scholar-mcp/commit/b0c3bee5560f310decac8804c5644c6cfdc295f9))

- Update spec to reflect deferred NPL medium-confidence and OpenAlex citing patents
  ([`56f149b`](https://github.com/pvliesdonk/scholar-mcp/commit/56f149b433b7d46383348e975eac6eb7c3297d98))

### Features

- Add alternative PDF source resolution and fetch_pdf_by_url tool
  ([`7a5d549`](https://github.com/pvliesdonk/scholar-mcp/commit/7a5d549019fdccdb3a7517ab20301a8a7d22e6b6))

- Add centralized book enrichment for paper records
  ([`fb94837`](https://github.com/pvliesdonk/scholar-mcp/commit/fb9483737e9c2bb2a09f350564527b57696a7966))

- Add citations section to get_patent with NPL resolution
  ([`8fed911`](https://github.com/pvliesdonk/scholar-mcp/commit/8fed911ae7aea61068161a680075e6010cfcd217))

- Add cited references parser with DOI extraction
  ([`8f24b19`](https://github.com/pvliesdonk/scholar-mcp/commit/8f24b196f4970474ebc7b14bc05ae774fddc8422))

- Add claims, description, family, and legal XML parsers
  ([`7b48dbe`](https://github.com/pvliesdonk/scholar-mcp/commit/7b48dbecc3352f81e26ce9c7005ec3078b5e65d2))

- Add claims, description, family, legal to EPO client
  ([`14080d4`](https://github.com/pvliesdonk/scholar-mcp/commit/14080d4c0700b22b680c31ebe2636ab9f1b3610b))

- Add EPO OPS client wrapper
  ([`c53a9a4`](https://github.com/pvliesdonk/scholar-mcp/commit/c53a9a4724240a21c573d4bd58f1692b9c420001))

- Add EPO OPS credential configuration
  ([`9803496`](https://github.com/pvliesdonk/scholar-mcp/commit/9803496efa7a5636cfbcc78beb1aaeb7e3b97ed8))

- Add EPO XML biblio and search parsers
  ([`6dba5f0`](https://github.com/pvliesdonk/scholar-mcp/commit/6dba5f034e8d71b5b79024a05cad7763e7345215))

- Add full section fetching to get_patent with concurrency
  ([`1e0a7ef`](https://github.com/pvliesdonk/scholar-mcp/commit/1e0a7ef146633edc130496f3836728060124482a))

- Add get_citing_patents tool with EPO citation search
  ([`88552e4`](https://github.com/pvliesdonk/scholar-mcp/commit/88552e48db9eefacbdbdbfba8a2fa3d2419634ea))

- Add ISBN utilities and book cache tables
  ([`4fad498`](https://github.com/pvliesdonk/scholar-mcp/commit/4fad4983d4ac95c5c34f352e011c98389f673d28))

- Add Open Library API client with normalization
  ([`092e514`](https://github.com/pvliesdonk/scholar-mcp/commit/092e514effede0030e38d0ab5f3347d253008b60))

- Add optional EpoClient to ServiceBundle
  ([`f3e81a7`](https://github.com/pvliesdonk/scholar-mcp/commit/f3e81a706e7868b03f3c916a60282640ca5603ae))

- Add patent cache tables with per-type TTLs
  ([`6e51381`](https://github.com/pvliesdonk/scholar-mcp/commit/6e5138115650b98ead960449951fd31108f06278))

- Add patent number normalization module
  ([`4fc235e`](https://github.com/pvliesdonk/scholar-mcp/commit/4fc235ea4d218c99769d89ac3f6e9d19f9687933))

- Add search_books and get_book MCP tools
  ([`4f75fee`](https://github.com/pvliesdonk/scholar-mcp/commit/4f75fee1d0cffb9c2eb68eafe7db1e34b49b4d1d))

- Add search_patents and get_patent tools
  ([`d157efe`](https://github.com/pvliesdonk/scholar-mcp/commit/d157efebfbaaab95c8e0acd3e332e49fe8fa6234))

- Disable patent tools when EPO credentials not configured
  ([`1998805`](https://github.com/pvliesdonk/scholar-mcp/commit/199880528b293afeeb39f5899124bed5fb79a910))

- Extend batch_resolve with patent number support
  ([`cf97239`](https://github.com/pvliesdonk/scholar-mcp/commit/cf972399b58d0c8a4446047aa0c35f6052ec4c96))

- Hook book enrichment into get_paper, get_citations, get_references, get_citation_graph
  ([`6c1e5ec`](https://github.com/pvliesdonk/scholar-mcp/commit/6c1e5ec50ccf720a3438046d4189068d7a4dffba))

- Wire OpenLibraryClient into ServiceBundle
  ([`61b159b`](https://github.com/pvliesdonk/scholar-mcp/commit/61b159baa5fbf0661929d9a6d975c2c6473d9b0a))


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
