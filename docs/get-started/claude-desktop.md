---
description: "Connect Claude Desktop to Scholar MCP on your machine and make a first, read-only call."
kind: tutorial
---

# Claude Desktop

Claude Desktop starts the server on your machine when it opens and talks to it directly; nothing listens on the network. The server runs with your user account's access and trusts the app that started it; the [security model](../security-model.md) says what that reaches. Claude Desktop is available for macOS and Windows.

The steps below end with one question to Claude.

## 1. Install the command

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then install the server as a command:

```bash
uv tool install "pvliesdonk-scholar-mcp"
```

uv keeps the server in its own environment and fetches a Python when your machine has none. Check the result:

```bash
scholar-mcp --help
```

Claude Desktop needs the command's full path, because it does not read your shell's `PATH`. Print it now and keep it for step 2:

```bash
which scholar-mcp        # macOS
where.exe scholar-mcp    # Windows
```

The path is inside uv's executable directory, `~/.local/bin` unless you configured another (`uv tool dir --bin` prints it).

**Without a terminal.** Each release ships a `.mcpb` bundle on the [releases page](https://github.com/pvliesdonk/scholar-mcp/releases). Download it and open it with Claude Desktop, or choose **Settings** › **Extensions** › **Advanced settings** › **Install Extension…** and pick the file. Claude Desktop asks for the settings this server declares and writes its own configuration. The bundle carries no code: on first launch it fetches the released package from PyPI, so the machine needs network access then. Skip to [step 4](#4-ask-claude-one-question).

## 2. Tell Claude Desktop about it

In Claude Desktop, open the Claude menu, choose **Settings…**, then **Developer**, then **Edit Config**. That opens the configuration file, creating it when it does not exist:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add the server, with the path from step 1 as `command`. With this entry the server appears in Claude under the name `scholar-mcp`:

```json { .config data-expect="server_name='scholar-mcp'" }
{
  "mcpServers": {
    "scholar-mcp": {
      "command": "/Users/me/.local/bin/scholar-mcp",
      "args": ["serve"],
      "env": {}
    }
  }
}
```

On Windows the path ends in `.exe` and each backslash is doubled: `"C:\\Users\\me\\.local\\bin\\scholar-mcp.exe"`.

Claude Desktop passes every value as written, so paths are absolute (`~` is not expanded). Keep the JSON valid: no trailing commas. Settings for the server go in `env`, one environment variable per key; the [configuration reference](../reference/configuration.md) lists them all.

### What this server needs

<!-- DOMAIN-CLAUDE-DESKTOP-START -->
<!-- Add domain-specific Claude Desktop configuration examples here.
     Kept across copier update. -->
<!-- DOMAIN-CLAUDE-DESKTOP-END -->

## 3. Restart Claude Desktop

Quit it completely and open it again; the configuration is read at start. Then click the **+** button at the bottom left of the message box, open **Connectors**, then **Manage connectors**: `scholar-mcp` is listed with its tools. If it is not, see [step 5](#5-if-it-does-not-appear).

## 4. Ask Claude one question

Ask Claude:

> Which version of Scholar MCP is running?

Claude calls the server's `get_server_info` tool and answers with the server's version, the version of the shared library it is built on and the protocol revision in use. The call reads those fields and changes nothing, so it is a safe first check of the connection; the [tools reference](../reference/tools/index.md) says what else the server offers. Then try the first task named under [What this server needs](#what-this-server-needs).

## 5. If it does not appear

- The JSON is valid (a trailing comma is the usual culprit) and `command` is an absolute path.
- Run the command yourself in a terminal: `scholar-mcp serve` starts the server and waits for a client; press Ctrl+C to stop it. An error here is the server's, not Claude Desktop's.
- Read the logs: `~/Library/Logs/Claude/mcp*.log` on macOS, `%APPDATA%\Claude\logs` on Windows. `mcp-server-scholar-mcp.log` holds what the server wrote to its standard error.

## Next

- [Claude Code](claude-code.md): the same server inside Claude Code.
- [Installation](installation.md): the other ways to install it.
- [Use](../use/index.md): what the server does for real tasks.
