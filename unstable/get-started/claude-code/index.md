# Claude Code

Claude Code can start the server for you, as Claude Desktop does. It can also connect to a server that already runs somewhere else. Started locally, the server runs with your user account's access and trusts the Claude Code session that started it; the [security model](https://pvliesdonk.github.io/scholar-mcp/unstable/security-model/index.md) says what that reaches.

## The plugin

The shortest route. In a Claude Code session, run:

```
/plugin marketplace add pvliesdonk/claude-plugins
/plugin install scholar-mcp@pvliesdonk
```

The first command registers the `pvliesdonk` marketplace, once. The second opens the plugin's details and asks for a scope:

- **user**: you, in every project on this machine;
- **project**: everyone who works in this repository;
- **local**: you, in this repository only.

The plugin follows stable releases and runs the released package with `uvx` at the version it was published with. Install `uv` first; the machine also needs network access the first time the server starts.

Run `/mcp` to see the server connected. To update or remove the plugin later, open `/plugin`, select it under **Installed**, and choose **Update now** or **Uninstall**; from a shell, `claude plugin update scholar-mcp@pvliesdonk` does the update.

From a shell, without a session (a setup script, say):

```
claude plugin marketplace add pvliesdonk/claude-plugins
claude plugin install scholar-mcp@pvliesdonk
```

The shell form installs at user scope unless `--scope project` or `--scope local` says otherwise, and the plugin loads when Claude Code next starts.

## The command

Without the plugin, install the server as a command, then register it with Claude Code:

```
uv tool install "pvliesdonk-scholar-mcp"
claude mcp add --transport stdio scholar-mcp -- scholar-mcp serve
```

Claude Code runs whatever follows the `--`, so settings for the server go on the command line as environment variables: `--env NAME=value` before the server's name, one per variable, from the [configuration reference](https://pvliesdonk.github.io/scholar-mcp/unstable/reference/configuration/index.md). The entry is stored for the current project; `--scope user` makes it available in every project. `/mcp` shows it connected.

## A server that already runs

When someone runs the server for you over HTTP, register its URL instead:

```
claude mcp add --transport http scholar-mcp https://mcp.example.com/mcp
```

With a bearer token, add `--header "Authorization: Bearer <token>"`. Which credential the server wants is up to whoever runs it; [A remote server](https://pvliesdonk.github.io/scholar-mcp/unstable/get-started/http-client/index.md) covers both kinds.

## Ask Claude one question

> Which version of Scholar MCP is running?

Claude calls the server's `get_server_info` tool, which reads the server's version and the protocol revision in use and changes nothing. Then the first task below.

### Your first task

When you install the plugin, Claude Code asks for its settings. Only the cache directory is required: give it a writable local path such as `~/Documents/scholar-mcp`. Read-only mode is on by default. Enter a Semantic Scholar API key there too if you have one, and an EPO OPS key and secret to turn on the patent tools.

With the command instead of the plugin, pass the same settings with `--env`:

```
claude mcp add --transport stdio \
  --env SCHOLAR_MCP_CACHE_DIR="$HOME/.local/share/scholar-mcp" \
  --env SCHOLAR_MCP_S2_API_KEY=your-key \
  scholar-mcp -- scholar-mcp serve
```

The key is optional: without one, requests share Semantic Scholar's public capacity and are throttled more often. Then give Claude a read-only task:

> Find the three most cited papers on retrieval-augmented generation and show how they cite each other.

That uses search and the citation graph. PDF download and conversion need write mode and a docling-serve; [PDF conversion](https://pvliesdonk.github.io/scholar-mcp/unstable/use/pdf-conversion/index.md) covers both.

## Next

- [Claude Desktop](https://pvliesdonk.github.io/scholar-mcp/unstable/get-started/claude-desktop/index.md): the same server in the desktop app.
- [Installation](https://pvliesdonk.github.io/scholar-mcp/unstable/get-started/installation/index.md): the other ways to install it.
- [Use](https://pvliesdonk.github.io/scholar-mcp/unstable/use/index.md): what the server does for real tasks.
