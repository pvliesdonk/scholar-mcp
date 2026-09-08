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
first thing a contributor reaches for. The builder set is collected across
the whole suite, not per module, so a helper parked in `conftest.py` and
called from a test file is caught too; that is the likeliest shape of all.

The indirection is one level by design. A helper calling a helper is not
followed, and the set is keyed on the callee's bare name, so a same-named
callable that does not build a server is flagged. Both are deliberate: the
gate errs toward a message a contributor can act on rather than toward
silence.
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


def _suite_builders(trees: dict[Path, ast.Module]) -> set[str]:
    """Return every synchronous builder name in the suite, across modules.

    Collecting per module would miss the likeliest shape of all: a helper in
    `conftest.py` that an async test in another file calls.

    Args:
        trees: Parsed modules, keyed by path.

    Returns:
        The union of each module's synchronous builder names.
    """
    return set().union(*(_sync_builders(tree) for tree in trees.values()))


def _violations(path: Path, tree: ast.Module, builders: set[str]) -> list[str]:
    """Return one message per async function in *path* that builds a server.

    Args:
        path: The module's path, used for the message.
        tree: The parsed module.
        builders: Synchronous builder names collected across the whole suite.

    Returns:
        A list of ``"file:line function -- reason"`` strings; empty when the
        module is clean.
    """
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
    trees = {
        path: ast.parse(path.read_text(encoding="utf-8"))
        for path in sorted(_TESTS_DIR.rglob("*.py"))
    }
    builders = _suite_builders(trees)
    assert "server" in builders, (
        "the `server` fixture in tests/conftest.py no longer builds the "
        "server; this gate is measuring the wrong thing"
    )
    offenders = [
        message
        for path, tree in trees.items()
        for message in _violations(path, tree, builders)
    ]
    assert not offenders, (
        "these async functions construct the server inside a running event "
        "loop:\n  " + "\n  ".join(offenders) + f"\n\n{_REMEDY}"
    )


def test_the_check_detects_all_three_shapes() -> None:
    """The gate catches the direct call and both helper indirections.

    Without this, a refactor that broke `_violations` -- a renamed target, a
    walk that stops at function boundaries, a builder set collected per file
    again -- would report a clean suite and the gate would pass by being
    blind. The cross-module case is the one a per-module scan misses, so it
    is asserted rather than described.
    """
    shared = ast.parse("def build_in_conftest():\n    return make_server()\n")
    module = ast.parse(
        """
def _build():
    return make_server()

def sync_is_fine():
    return make_server()

async def direct():
    return make_server()

async def same_module_indirect():
    return _build()

async def cross_module_indirect():
    return build_in_conftest()

async def clean(server):
    return server
"""
    )
    fake_conftest = _TESTS_DIR / "conftest.py"
    fake_module = _TESTS_DIR / "test_x.py"
    trees = {fake_conftest: shared, fake_module: module}
    builders = _suite_builders(trees)
    assert builders == {"build_in_conftest", "_build", "sync_is_fine"}

    flagged = {
        message.split(" -- ")[0].split(" ")[-1]
        for path, tree in trees.items()
        for message in _violations(path, tree, builders)
    }
    assert flagged == {"direct", "same_module_indirect", "cross_module_indirect"}

    # A per-module builder set would miss the cross-module case; prove it, so
    # a regression to that shape fails here rather than passing silently.
    per_module_only = {
        message.split(" -- ")[0].split(" ")[-1]
        for message in _violations(fake_module, module, _sync_builders(module))
    }
    assert "cross_module_indirect" not in per_module_only
