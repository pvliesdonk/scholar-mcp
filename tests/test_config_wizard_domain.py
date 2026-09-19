"""Domain-specific config-wizard tests for Scholar MCP.

This file is owned by the generated project (kept across ``copier update`` via
``_skip_if_exists``). The template seeds it once with a single skipped
placeholder test; add browser assertions here that depend on *this project's*
``wizard-spec.json`` — e.g. that a specific field renders, that a chosen option
emits the expected env var, or that a guard message appears. The generic
framework tests live in ``test_config_wizard_smoke.py`` (template-owned) and
must not be edited here.

Import the page/browser fixtures from ``test_config_wizard_smoke.py`` (e.g.
``from tests.test_config_wizard_smoke import page, site_url, browser``). This
module is marked ``browser`` so the tests you add run in the docs CI lane, which
invokes ``pytest ... -m browser``.
"""

from __future__ import annotations

import typing

import pytest

from tests.test_config_wizard_smoke import (  # noqa: F401 — pytest fixtures
    browser,
    page,
    site_url,
)

if typing.TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = pytest.mark.browser


# --- bearer_token visibility gating -----------------------------------------
#
# `wizard.js` skips a question entirely when `isVisible()` is false
# (`if (!isVisible(q, answers)) continue;`), so a gated-out field is absent
# from the DOM rather than hidden. These assert on `count()` for that reason:
# `is_visible()` would also read false for a missing element and so would not
# notice a future change to render-then-hide.


def test_bearer_token_absent_for_local_deployment(page: Page) -> None:
    """A local deployment exposes no bearer-token field."""
    page.select_option('[data-qid="deployment"] select', "local")
    assert page.locator('[data-qid="bearer_token"]').count() == 0


def test_bearer_token_needs_both_gate_conditions(page: Page) -> None:
    """Server deployment alone does not reveal the bearer token.

    ``bearer_token`` carries ``showIf: {deployment: [server], auth: [bearer,
    both]}`` — two conditions, and ``isVisible`` requires *every* one. Choosing
    a server deployment satisfies only the first, so the field stays absent
    until an auth mode that uses a bearer token is chosen as well.
    """
    page.select_option('[data-qid="deployment"] select', "server")
    assert page.locator('[data-qid="bearer_token"]').count() == 0

    page.select_option('[data-qid="auth"] select', "bearer")
    assert page.locator('[data-qid="bearer_token"]').count() == 1


def test_bearer_token_shown_for_combined_auth(page: Page) -> None:
    """``both`` is the other auth mode that uses a bearer token."""
    page.select_option('[data-qid="deployment"] select', "server")
    page.select_option('[data-qid="auth"] select', "both")
    assert page.locator('[data-qid="bearer_token"]').count() == 1


def test_bearer_token_disappears_when_auth_turned_off(page: Page) -> None:
    """Revoking either condition hides the field again.

    Pins the gate as live rather than one-way: a field that appeared once must
    not linger once its condition stops holding, or a token entered under
    `bearer` would keep being emitted after switching to `none`.
    """
    page.select_option('[data-qid="deployment"] select', "server")
    page.select_option('[data-qid="auth"] select', "bearer")
    assert page.locator('[data-qid="bearer_token"]').count() == 1

    page.select_option('[data-qid="auth"] select', "none")
    assert page.locator('[data-qid="bearer_token"]').count() == 0


# --- bool env emission, with the non-prefixed var pinned ---------------------
#
# A `bool` question renders as a three-option <select> ("", "true", "false"),
# and `buildEnvMap` emits a var only when the answer is neither undefined nor
# "". So "(default)" contributes nothing and an explicit choice emits
# `VAR=true` / `VAR=false`. The assertions below match on `KEY=value`, not on
# the bare key, because a bare key also appears in field labels and help text.


def test_read_only_emits_the_prefixed_var(page: Page) -> None:
    """``read_only`` emits ``SCHOLAR_MCP_READ_ONLY``, which gates write tools."""
    page.select_option('[data-qid="read_only"] select', "false")
    assert "SCHOLAR_MCP_READ_ONLY=false" in page.inner_text(".cfg-output")


def test_bool_left_at_default_emits_nothing(page: Page) -> None:
    """The "(default)" option is the empty answer, so no var is emitted.

    Without this, a test that only ever selects an explicit value cannot tell
    "emitted because chosen" from "emitted always".
    """
    assert "SCHOLAR_MCP_READ_ONLY=" not in page.inner_text(".cfg-output")


def test_rich_logging_emits_the_unprefixed_fastmcp_var(page: Page) -> None:
    """``fastmcp_enable_rich_logging`` deliberately carries no project prefix.

    It is read by FastMCP itself, so the emitted key must stay
    ``FASTMCP_ENABLE_RICH_LOGGING``. A refactor that applied the
    ``SCHOLAR_MCP_`` prefix uniformly would break it silently, which is why the
    negative is asserted alongside the positive.
    """
    page.locator("details.cfg-advanced summary").first.click()
    page.select_option('[data-qid="fastmcp_enable_rich_logging"] select', "false")

    text = page.inner_text(".cfg-output")
    assert "FASTMCP_ENABLE_RICH_LOGGING=false" in text
    assert "SCHOLAR_MCP_ENABLE_RICH_LOGGING" not in text
