"""Tests for _sync_relaton: YAML mapper, joint detection, record-changed."""

from __future__ import annotations

from pathlib import Path

import yaml

FIXTURES = Path(__file__).parent / "fixtures" / "standards"


def _load_fixture(relative: str) -> dict:
    with (FIXTURES / relative).open() as f:
        return yaml.safe_load(f)


def test_yaml_to_record_plain_iso() -> None:
    """Plain ISO entry maps to body='ISO', identifier='ISO 9001:2015'."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_iso_sample/iso-9001-2015.yaml")
    record, aliases = _yaml_to_record(doc)

    assert record is not None
    assert record["identifier"] == "ISO 9001:2015"
    assert record["body"] == "ISO"
    assert "Quality management" in record["title"]
    assert record["status"] == "published"
    assert record["published_date"] == "2015-09-15"
    assert record["url"] == "https://www.iso.org/standard/62085.html"
    assert record["full_text_available"] is False
    # URN form is an alias
    assert any("urn" in a.lower() or "iso:std" in a for a in aliases)


def test_yaml_to_record_joint_iso_iec() -> None:
    """Joint entry → body='ISO/IEC', identifier preserves slash form."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_iso_sample/iso-iec-27001-2022.yaml")
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["body"] == "ISO/IEC"
    assert record["identifier"] == "ISO/IEC 27001:2022"


def test_yaml_to_record_iec_only() -> None:
    """IEC-only entry → body='IEC'."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_iec_sample/iec-62443-3-3-2020.yaml")
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["body"] == "IEC"
    assert record["identifier"] == "IEC 62443-3-3:2020"


def test_yaml_to_record_withdrawn_status() -> None:
    """docstatus.stage='95.99' maps to status='withdrawn'."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_iso_sample/iso-9001-2008.yaml")
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["status"] == "withdrawn"
    assert record["superseded_by"] == "ISO 9001:2015"


def test_yaml_to_record_missing_identifier_returns_none() -> None:
    """Document without any docidentifier returns (None, [])."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    record, aliases = _yaml_to_record({"title": [{"content": "orphan"}]})

    assert record is None
    assert aliases == []


def test_yaml_to_record_missing_title_returns_none() -> None:
    """Document with no title is unusable — returns (None, [])."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {"docidentifier": [{"id": "ISO 123:2020", "type": "ISO", "primary": True}]}
    record, aliases = _yaml_to_record(doc)

    assert record is None
    assert aliases == []


def test_record_changed_detects_title_edit() -> None:
    from scholar_mcp._sync_relaton import _record_changed

    old = {"identifier": "ISO 9001:2015", "title": "A", "status": "published"}
    new = {"identifier": "ISO 9001:2015", "title": "B", "status": "published"}
    assert _record_changed(old, new) is True


def test_record_changed_ignores_extra_keys() -> None:
    """Synced records may have fields like cached_at added later — ignore them."""
    from scholar_mcp._sync_relaton import _record_changed

    old = {"identifier": "ISO 9001:2015", "title": "A"}
    new = {"identifier": "ISO 9001:2015", "title": "A"}
    assert _record_changed(old, new) is False
