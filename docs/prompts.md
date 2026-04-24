# Prompts

MCP prompts are reusable prompt templates exposed to clients. The scaffold
ships a minimal set defined in `src/scholar_mcp/_server_prompts.py`; add
domain-specific prompts there and document them in this page.

## Built-in prompts

_None in the scaffold._ Define prompts with `@mcp.prompt(...)` decorators in
`src/scholar_mcp/_server_prompts.py` and list them here with their arguments,
usage, and example output.

## Example

```python
@mcp.prompt()
def summarize(topic: str) -> str:
    """Summarize the given topic in three sentences."""
    return f"Write a three-sentence summary of: {topic}"
```

See the [FastMCP prompts documentation](https://gofastmcp.com/servers/prompts)
for the full prompt API.
