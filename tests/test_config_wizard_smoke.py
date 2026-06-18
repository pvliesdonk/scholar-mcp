"""Browser smoke test for the built config-wizard page.

Marked ``browser``; requires the ``browser`` dependency group and
``playwright install chromium``. Runs against the built ``site/`` directory, so
``mkdocs build`` must have run first.
"""

from __future__ import annotations

import functools
import http.server
import socketserver
import threading
import typing
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

if typing.TYPE_CHECKING:
    from playwright.sync_api import Browser, Page

SITE = Path(__file__).resolve().parent.parent / "site"

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def site_url() -> typing.Iterator[str]:
    if not (SITE / "configuration-generator" / "index.html").exists():
        pytest.skip("site/ not built -- run `uv run mkdocs build` first")
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(SITE)
    )
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            httpd.shutdown()


@pytest.fixture(scope="module")
def browser(site_url: str) -> typing.Iterator[Browser]:
    # Depend on site_url so its "site not built" skip runs BEFORE we try to
    # launch Chromium. In the main CI test lane (no built site, no installed
    # browser) this makes the smoke tests skip cleanly instead of erroring.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser: Browser, site_url: str) -> typing.Iterator[Page]:
    # Fresh page per test: the wizard keeps answer state in a module-level JS
    # object, so each test must start from a clean load to stay order-independent.
    pg = browser.new_page()
    pg.goto(f"{site_url}/configuration-generator/")
    pg.wait_for_selector("#cfg-wizard select")
    yield pg
    pg.close()


def test_local_path_emits_claude_json(page: Page) -> None:
    page.select_option('[data-qid="deployment"] select', "local")
    text = page.inner_text(".cfg-output")
    assert "scholar-mcp" in text


def test_server_docker_path_emits_image(page: Page) -> None:
    page.select_option('[data-qid="deployment"] select', "server")
    page.fill('[data-qid="bearer_token"] input', "secret-token")
    text = page.inner_text("#cfg-wizard")
    assert "ghcr.io/pvliesdonk/scholar-mcp:latest" in text
    assert "SCHOLAR_MCP_BEARER_TOKEN" in text
