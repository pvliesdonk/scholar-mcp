"""Compose the copier-update PR body from three claude-code agent JSON outputs.

Reads /tmp/agent-job-{a,b,c}.json (or paths passed via CLI), validates each
against an inline schema, and composes a markdown PR body that extends the
existing #49-shaped body (delta/notes/diff/conflicts) with three new sections
(conflict resolutions, changelog triage, excluded-file evolution).

Failure-tolerant: missing/skipped/rate-limited/errored agent outputs render
as state-specific placeholders without affecting other sections. The existing
#49 sections always render regardless of agent state.

Exit codes:
- 0: composed body written successfully (even if some sections are placeholders)
- 1: catastrophic failure (e.g. existing body file missing, output path unwritable)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class AggregatorInputs:
    existing_body: str
    agent_enabled: bool
    job_a_path: Path | None
    job_b_path: Path | None
    job_c_path: Path | None
    conflict_count: int
    template_advanced: bool = True
    """Whether the template ref actually changed.

    Jobs B and C only fire when `template_advanced=True`. When False (e.g. a
    `workflow_dispatch` re-run with the same vcs-ref), Jobs B/C section
    rendering is suppressed entirely rather than rendered as 'Agent failed'.
    Defaults to True for backward compatibility with callers that don't pass
    the flag (Job A's `conflict_count` already gates its own section).
    """


def _read_job_json(path: Path | None) -> dict | None:
    """Read and JSON-parse an agent output file. Returns None if missing or unreadable."""
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _validate_job_a(data: dict | None) -> dict | None:
    """Return data if it has the expected schema, else None (treated as errored).

    Validates ONLY the top-level shape (`status` is a str; `auto_resolved` /
    `needs_review` are lists). Item-level shape (each entry's `file`,
    `commit_sha`, `articulation` keys) is intentionally NOT validated here —
    a malformed item raises KeyError at render time and `_safe_render` catches
    it, degrading to that section's error placeholder. This matches the spec's
    section-level isolation contract; do not extend item-level validation here
    expecting it to change failure granularity (it won't).
    """
    if data is None:
        return None
    if not isinstance(data.get("status"), str):
        return None
    if data["status"] == "ok" and not isinstance(data.get("auto_resolved", []), list):
        return None
    if data["status"] == "ok" and not isinstance(data.get("needs_review", []), list):
        return None
    return data


def _validate_job_b(data: dict | None) -> dict | None:
    """Return data if it has the expected schema, else None (treated as errored)."""
    if data is None:
        return None
    if not isinstance(data.get("status"), str):
        return None
    if data["status"] == "ok" and not isinstance(data.get("entries", []), list):
        return None
    return data


def _validate_job_c(data: dict | None) -> dict | None:
    """Return data if it has the expected schema, else None (treated as errored)."""
    if data is None:
        return None
    if not isinstance(data.get("status"), str):
        return None
    if data["status"] == "ok" and not isinstance(data.get("files", []), list):
        return None
    return data


def _placeholder(section_title: str, status: str) -> str:
    """Render a state-specific placeholder for a section."""
    if status == "rate_limited":
        msg = "⏳ Agent rate-limited — full analysis will retry on next cron."
    else:  # generic error or missing-but-expected
        msg = "⚠️ Agent failed — see workflow log."
    return f"### {section_title}\n\n{msg}\n"


def _render_job_a(data: dict | None, conflict_count: int) -> str:
    """Render the 🔧 Conflict resolutions section."""
    if conflict_count == 0:
        return ""  # Job A is gated; no section if no conflicts
    data = _validate_job_a(data)
    if data is None:
        return _placeholder("🔧 Conflict resolutions", "error")
    status = data.get("status", "error")
    if status == "rate_limited":
        return _placeholder("🔧 Conflict resolutions", "rate_limited")
    if status != "ok":
        return _placeholder("🔧 Conflict resolutions", "error")

    lines = ["### 🔧 Conflict resolutions", ""]
    auto = data.get("auto_resolved", [])
    if auto:
        lines.append("**Auto-committed by claude-code** — VERIFY before merging:")
        lines.append("")
        for item in auto:
            lines.append(
                f"- `{item['file']}` (commit {item['commit_sha']}): "
                f"_{item['articulation']}_"
            )
        lines.append("")
    review = data.get("needs_review", [])
    if review:
        lines.append(
            "**Needs review** — conflict markers remain, operator must resolve:"
        )
        lines.append("")
        for item in review:
            lines.append(f"- `{item['file']}`: {item['reasoning']}")
            lines.append(f"  Recommended approach: {item['recommended_resolution']}")
        lines.append("")
    return "\n".join(lines)


def _render_job_b(data: dict | None, template_advanced: bool = True) -> str:
    """Render the ✨ New features in this update section."""
    if not template_advanced:
        return ""  # Job B is gated; no section if refs didn't differ
    data = _validate_job_b(data)
    if data is None:
        return _placeholder("✨ New features in this update", "error")
    status = data.get("status", "error")
    if status == "rate_limited":
        return _placeholder("✨ New features in this update", "rate_limited")
    if status != "ok":
        return _placeholder("✨ New features in this update", "error")

    entries = data.get("entries", [])
    if not entries:
        return ""  # No features = no section (rare — refs differed but changelog empty)

    # Sort by PR# ascending for deterministic body across re-runs
    # (LLM-emitted entry order may vary; canonical sort collapses that variance).
    # `lstrip("#")` tolerates LLM-emitted prefixes like `"#89"`. `or 0` covers
    # null values. Without coercion a single bad entry would degrade the whole
    # section to an error placeholder via _safe_render's TypeError catch.
    entries = sorted(
        entries,
        key=lambda e: int(str(e.get("pr_number") or "0").lstrip("#") or "0"),
    )

    by_class: dict[str, list[dict]] = {
        "needs-opt-in": [],
        "ships-automatically": [],
        "informational": [],
    }
    # Map any unknown classification to "informational" so the render loop
    # (which only iterates the three keys above) doesn't silently drop entries
    # with off-spec classification strings (e.g., LLM emits "NEEDS-OPT-IN" or
    # a typo). The `setdefault`-style pattern would have created a new dict
    # key but the render loop wouldn't have visited it.
    for e in entries:
        cls = e.get("classification")
        by_class[cls if cls in by_class else "informational"].append(e)

    lines = ["### ✨ New features in this update", ""]
    if by_class["needs-opt-in"]:
        lines.append("**Needs your attention** (action-required):")
        lines.append("")
        for e in by_class["needs-opt-in"]:
            lines.append(f"- #{e['pr_number']} {e['title']} — needs opt-in.")
            lines.append(f"  {e['summary']}")
        lines.append("")
    if by_class["ships-automatically"]:
        lines.append("**Ships through automatically** (informational):")
        lines.append("")
        for e in by_class["ships-automatically"]:
            lines.append(f"- #{e['pr_number']} {e['title']} — applied this run")
        lines.append("")
    if by_class["informational"]:
        ids = ", ".join(f"#{e['pr_number']}" for e in by_class["informational"])
        n = len(by_class["informational"])
        lines.append(
            f"**Internal / no downstream effect** ({n} {'entry' if n == 1 else 'entries'}): {ids}"
        )
        lines.append("")
    return "\n".join(lines)


def _render_job_c(data: dict | None, template_advanced: bool = True) -> str:
    """Render the 📦 Excluded-file upstream changes section."""
    if not template_advanced:
        return ""  # Job C is gated; no section if refs didn't differ
    data = _validate_job_c(data)
    if data is None:
        return _placeholder("📦 Excluded-file upstream changes", "error")
    status = data.get("status", "error")
    if status == "rate_limited":
        return _placeholder("📦 Excluded-file upstream changes", "rate_limited")
    if status != "ok":
        return _placeholder("📦 Excluded-file upstream changes", "error")

    files = data.get("files", [])
    if not files:
        return ""

    # Sort by file path for deterministic body across re-runs.
    # `str(... or "")` coerces null/missing file fields without raising
    # TypeError on mixed-type lists (the LLM may emit `"file": null` for a
    # malformed entry). Same robustness rationale as Job B's pr_number sort.
    files = sorted(files, key=lambda f: str(f.get("file") or ""))

    by_class: dict[str, list[dict]] = {
        "recommend-port": [],
        "informational": [],
        "skip": [],
    }
    # Map unknown classifications to "informational" — same rationale as
    # Job B (avoid silent data loss from off-spec classification strings).
    for f in files:
        cls = f.get("classification")
        by_class[cls if cls in by_class else "informational"].append(f)

    lines = ["### 📦 Excluded-file upstream changes", ""]
    if by_class["recommend-port"]:
        lines.append("**Recommended to port** (action-required):")
        lines.append("")
        for f in by_class["recommend-port"]:
            lines.append(f"- `{f['file']}`: {f['summary']}")
            lines.append(f"  Diff: {f['diff_summary']}")
        lines.append("")
    if by_class["informational"]:
        lines.append("**Informational**:")
        lines.append("")
        for f in by_class["informational"]:
            lines.append(f"- `{f['file']}`: {f['summary']}")
        lines.append("")
    if by_class["skip"]:
        names = ", ".join(f"`{f['file']}`" for f in by_class["skip"])
        n = len(by_class["skip"])
        lines.append(
            f"**Skipped (template-internal)** ({n} {'file' if n == 1 else 'files'}): {names}"
        )
        lines.append("")
    return "\n".join(lines)


_DISABLED_NOTICE = (
    "🔒 Agent disabled — `CLAUDE_CODE_OAUTH_TOKEN` not configured. "
    "Set the secret in repo settings to enable."
)


def _disabled_section(section_title: str) -> str:
    """Per-section placeholder when agent_enabled=False."""
    return f"### {section_title}\n\n{_DISABLED_NOTICE}\n"


def compose_body(inputs: AggregatorInputs) -> str:
    """Compose the full PR body from existing #49 content + agent JSON outputs."""
    parts = [inputs.existing_body.rstrip(), "", "---", "", "## Agent analysis", ""]

    if not inputs.agent_enabled:
        # Per-section disabled placeholders so structure is consistent across
        # configured / not-configured runs. Each section that WOULD have run
        # gets a skip notice; sections gated out (e.g. Job A with no conflicts)
        # are omitted entirely.
        if inputs.conflict_count > 0:
            parts.append(_disabled_section("🔧 Conflict resolutions"))
        if inputs.template_advanced:
            parts.append(_disabled_section("✨ New features in this update"))
            parts.append(_disabled_section("📦 Excluded-file upstream changes"))
        return "\n".join(parts) + "\n"

    # Each render is wrapped in try/except so a malformed item in one job's
    # JSON (e.g. LLM emitted entry missing a required field) degrades to that
    # section's error placeholder without nuking the other two sections.
    # See spec § Aggregator's four-state contract — sections must be
    # independently failing.
    section_a = _safe_render(
        "🔧 Conflict resolutions",
        lambda: _render_job_a(_read_job_json(inputs.job_a_path), inputs.conflict_count),
    )
    if section_a:
        parts.append(section_a)

    section_b = _safe_render(
        "✨ New features in this update",
        lambda: _render_job_b(
            _read_job_json(inputs.job_b_path), inputs.template_advanced
        ),
    )
    if section_b:
        parts.append(section_b)

    section_c = _safe_render(
        "📦 Excluded-file upstream changes",
        lambda: _render_job_c(
            _read_job_json(inputs.job_c_path), inputs.template_advanced
        ),
    )
    if section_c:
        parts.append(section_c)

    return "\n".join(parts) + "\n"


def _safe_render(section_title: str, render_fn: Callable[[], str]) -> str:
    """Run render_fn; on any exception, return that section's error placeholder.

    Per-section isolation: a render-time crash on one job (e.g. KeyError from a
    malformed item) must not affect the other two job sections. The render
    callable is invoked and its result returned; only on exception do we
    substitute an error placeholder.
    """
    try:
        return render_fn()
    except (KeyError, TypeError, ValueError, AttributeError):
        return _placeholder(section_title, "error")


BODY_LIMIT = 60_000
SECTION_MARKERS = ["### 🔧 ", "### ✨ ", "### 📦 "]


def compose_body_with_overflow(
    inputs: AggregatorInputs, overflow_dir: Path
) -> tuple[str, list[Path]]:
    """Compose body; if > BODY_LIMIT chars, spill longest section(s) to overflow files.

    Returns (body, overflow_paths). overflow_paths is empty if no spill occurred.
    Each overflow path holds the displaced section content (caller posts as comments).
    """
    body = compose_body(inputs)
    if len(body) <= BODY_LIMIT:
        return body, []

    overflow_dir.mkdir(parents=True, exist_ok=True)
    overflow_paths: list[Path] = []
    spill_index = 0
    # Track which markers have already been spilled so a later iteration
    # doesn't re-pick the (now-tiny) replacement section as longest. Without
    # this guard, the replacement (still beginning with "### …") would match
    # the section finder forever, producing useless overflow files of stub
    # content while the loop spins.
    spilled_markers: set[str] = set()

    while len(body) > BODY_LIMIT:
        # Find each not-yet-spilled section's start + length.
        sections: list[tuple[str, int, int]] = []  # (header, start, end)
        for marker in SECTION_MARKERS:
            if marker in spilled_markers:
                continue
            start = body.find(marker)
            if start == -1:
                continue
            # Section ends at the start of the NEXT known SECTION_MARKER, or
            # EOF. Don't bare-find `\n### ` — agent-supplied text inside a
            # section (Job A articulation, Job B/C summaries) may legitimately
            # contain `### Sub-header` lines that would otherwise be mistaken
            # for a section boundary, splitting the section prematurely.
            other_starts = [
                body.find(m, start + len(marker))
                for m in SECTION_MARKERS
                if m != marker
            ]
            other_starts = [s for s in other_starts if s != -1]
            end = min(other_starts) if other_starts else len(body)
            sections.append((marker, start, end))

        if not sections:
            # All agent sections already spilled; can't reduce further
            # (existing #49 body alone exceeds the limit). Bail.
            break

        sections.sort(key=lambda s: s[2] - s[1], reverse=True)
        marker, start, end = sections[0]
        spilled_markers.add(marker)
        spill_index += 1
        overflow_path = overflow_dir / f"overflow-{spill_index}.md"
        overflow_path.write_text(body[start:end], encoding="utf-8")
        overflow_paths.append(overflow_path)

        # Capture the FULL heading line (`### 🔧 Conflict resolutions`) so the
        # replacement preserves the section-name signal, then strip the `### `
        # prefix for the bold replacement (which intentionally uses non-`###`
        # so the section finder skips it on subsequent iterations).
        heading_end = body.find("\n", start)
        if heading_end == -1:
            heading_end = end
        full_heading = body[start:heading_end].lstrip("# ").rstrip()
        replacement = (
            f"**{full_heading} — full analysis posted as a "
            f"follow-up comment (overflow #{spill_index}).**\n\n"
        )
        body = body[:start] + replacement + body[end:]

    return body, overflow_paths


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compose copier-update PR body from agent JSON outputs."
    )
    p.add_argument(
        "--existing-body",
        type=Path,
        required=True,
        help="Path to the existing #49-shaped body markdown.",
    )
    p.add_argument("--agent-enabled", choices=["true", "false"], required=True)
    p.add_argument(
        "--job-a",
        type=Path,
        default=None,
        help="Path to /tmp/agent-job-a.json (or absent).",
    )
    p.add_argument("--job-b", type=Path, default=None)
    p.add_argument("--job-c", type=Path, default=None)
    p.add_argument("--conflict-count", type=int, required=True)
    p.add_argument(
        "--template-advanced",
        choices=["true", "false"],
        default="true",
        help="Whether the template ref changed; gates Jobs B/C section rendering.",
    )
    p.add_argument(
        "--output-body", type=Path, required=True, help="Where to write composed body."
    )
    p.add_argument(
        "--overflow-dir",
        type=Path,
        required=True,
        help="Directory for overflow comment files.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    inputs = AggregatorInputs(
        existing_body=args.existing_body.read_text(encoding="utf-8"),
        agent_enabled=(args.agent_enabled == "true"),
        job_a_path=args.job_a,
        job_b_path=args.job_b,
        job_c_path=args.job_c,
        conflict_count=args.conflict_count,
        template_advanced=(args.template_advanced == "true"),
    )
    body, overflow_paths = compose_body_with_overflow(
        inputs, overflow_dir=args.overflow_dir
    )
    args.output_body.write_text(body, encoding="utf-8")
    if overflow_paths:
        for p in overflow_paths:
            print(f"OVERFLOW: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
