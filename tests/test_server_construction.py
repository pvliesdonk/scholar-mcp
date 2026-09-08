"""Gate that no test builds the server inside a running event loop.

`make_server()` must run synchronously. From `fastmcp-pvl-core` 6 -- which
template v7.0 brings in -- `finalize_instructions` enumerates the effective
tool set through `effective_tool_names`, and that function calls
`asyncio.get_running_loop()` and raises rather than move potentially
loop-affine providers onto a worker loop [verified: `_visibility.py` at
`fastmcp-pvl-core>=6,<7`, "instruction finalization requires synchronous
server construction"].

On the pvl-core this project pins today the call is harmless, so nothing
fails when a test constructs the server in an `async def` body -- which is
how fourteen call sites accumulated (#338). This test is what makes the
constraint enforceable *before* the hop lands, so the v7.0 update is a pure
template change with no test rework inside it. It keeps its value after the
hop too: it names the remedy at collection time instead of leaving a
contributor to decode a `RuntimeError` from library internals.

The check is deliberately not "no `make_server` on a line inside an `async
def`". It also follows one level of indirection -- a synchronous helper that
builds the server is fine on its own, and only becomes a violation when an
async function calls it -- because extracting the call into a helper is the
first thing a contributor reaches for.
"""

from __future__ import annotations

import ast
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_TARGET = "make_server"

_REMEDY = (
    "Take the server from the synchronous `server` fixture in "
    "tests/conftest.py instead (`async def test_x(server: FastMCP)`), or "
    "from `client` when the test needs a connected client. Env the server "
    "reads goes through indirect parametrisation: "
    '@pytest.mark.parametrize("server", [{"SCHOLAR_MCP_...": "..."}], '
    'indirect=True, ids=["..."]). See #338.'
)


def _called_names(node: ast.AST) -> set[str]:
    """Return every simple name called anywhere in *node*'s subtree.

    Args:
        node: The AST node to walk.

    Returns:
        The set of callee names, taking `f()` as ``"f"`` and `o.f()` as
        ``"f"``. Attribute access is flattened deliberately: a module-scoped
        helper reached as `mod.helper()` should read the same as `helper()`.
    """
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name:
                names.add(name)
    return names


def _sync_builders(tree: ast.Module) -> set[str]:
    """Return names of synchronous functions in *tree* that build a server.

    Args:
        tree: A parsed test module.

    Returns:
        The names of every `def` (at any nesting depth) whose body reaches
        `make_server`. These are legitimate on their own -- the `server`
        fixture is one -- and only matter as things an async function must
        not call.
    """
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and _TARGET in _called_names(node)
    }


def _violations(path: Path) -> list[str]:
    """Return one message per async function in *path* that builds a server.

    Args:
        path: A test module to check.

    Returns:
        A list of ``"file:line function -- reason"`` strings; empty when the
        module is clean.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    builders = _sync_builders(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        called = _called_names(node)
        if _TARGET in called:
            reason = f"calls {_TARGET}() directly"
        elif reached := sorted(called & builders):
            reason = f"calls {', '.join(reached)}(), which builds a server"
        else:
            continue
        found.append(
            f"{path.relative_to(_TESTS_DIR.parent)}:{node.lineno} "
            f"{node.name} -- {reason}"
        )
    return found


def test_no_async_function_constructs_the_server() -> None:
    """No `async def` in the suite reaches `make_server`, directly or via a helper."""
    offenders = [
        message
        for path in sorted(_TESTS_DIR.rglob("*.py"))
        for message in _violations(path)
    ]
    assert not offenders, (
        "these async functions construct the server inside a running event "
        "loop:\n  " + "\n  ".join(offenders) + f"\n\n{_REMEDY}"
    )


def test_the_check_detects_both_shapes() -> None:
    """The gate itself catches the direct call and the helper indirection.

    Without this, a refactor that broke `_violations` -- a renamed target, a
    walk that stops at function boundaries -- would report a clean suite and
    the gate would pass by being blind.
    """
    source = """
def _build():
    return make_server()

def sync_is_fine():
    return make_server()

async def direct():
    return make_server()

async def indirect():
    return _build()

async def clean(server):
    return server
"""
    tree = ast.parse(source)
    assert _sync_builders(tree) == {"_build", "sync_is_fine"}
    flagged = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        and (
            _TARGET in _called_names(node) or _called_names(node) & _sync_builders(tree)
        )
    }
    assert flagged == {"direct", "indirect"}
