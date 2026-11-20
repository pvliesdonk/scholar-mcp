"""The quarterly CEN review's prompt carries the table the loader syncs (#594)."""

from __future__ import annotations

import datetime
import importlib.util
import re
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

from scholar_mcp._sync_cen import _HARMONISED_STANDARDS

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "cen-review.yml"
FETCH_OJ = REPO_ROOT / "scripts" / "fetch_oj.sh"


@pytest.fixture(scope="module")
def prompt_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "cen_review_prompt", REPO_ROOT / "scripts" / "cen_review_prompt.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_prompt_lists_every_table_entry(prompt_script: ModuleType) -> None:
    """The script reads the table with ast; it must see what the loader sees."""
    source = (REPO_ROOT / "src" / "scholar_mcp" / "_sync_cen.py").read_text()
    entries = prompt_script.table_entries(source)
    assert [e["identifier"] for e in entries] == [
        e.identifier for e in _HARMONISED_STANDARDS
    ]


def test_the_prompt_carries_the_procedure_table_and_task(
    prompt_script: ModuleType,
) -> None:
    prompt = prompt_script.build_prompt(datetime.date(2027, 1, 2))
    assert prompt.startswith("# CEN harmonised-standards table review")
    assert "| EMC | EN 55032:2015" in prompt
    assert "Today is 2027-01-02." in prompt
    assert prompt_script.FINDINGS_FILE in prompt


def test_the_workflow_lets_the_agent_write_only_the_findings_file(
    prompt_script: ModuleType,
) -> None:
    """The file the agent may write is the one the filing step reads."""
    workflow = WORKFLOW.read_text()
    findings = prompt_script.FINDINGS_FILE
    assert f"Edit(./{findings})" in workflow
    assert "persist-credentials: false" in workflow
    assert f"-s {findings}" in workflow
    assert re.search(r'--disallowedTools "[^"]*\bRead\b', workflow)
    assert re.search(r'--disallowedTools "[^"]*\bWebSearch\b', workflow)


@pytest.mark.parametrize(
    "argument", ["x;env", "32026D2479 $(id)", "../etc/passwd", "", "32026D2479 x"]
)
def test_fetch_oj_refuses_anything_but_a_celex_number(argument: str) -> None:
    """The agent's one shell command takes a CELEX number and nothing else."""
    result = subprocess.run(
        ["bash", str(FETCH_OJ), argument],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
