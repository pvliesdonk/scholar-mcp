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
    """cached_at is not in _RECORD_IDENTITY_FIELDS — must be ignored."""
    from scholar_mcp._sync_relaton import _record_changed

    old = {"title": "A", "status": "published", "body": "ISO"}
    new = {
        "title": "A",
        "status": "published",
        "body": "ISO",
        "cached_at": "2026-04-14T00:00:00Z",  # extra key absent in old
    }
    assert _record_changed(old, new) is False


def test_record_changed_detects_status_edit() -> None:
    """A change in an identity field (status) must be detected."""
    from scholar_mcp._sync_relaton import _record_changed

    old = {"title": "A", "status": "published", "body": "ISO"}
    new = {"title": "A", "status": "withdrawn", "body": "ISO"}
    assert _record_changed(old, new) is True


# ---------------------------------------------------------------------------
# _canonical_identifier_and_body branch coverage
# ---------------------------------------------------------------------------


def test_canonical_joint_rewrites_iso_text() -> None:
    """Both ISO and IEC entries present but neither id contains 'ISO/IEC'.

    The branch ``if not ident.startswith("ISO/IEC")`` must rewrite
    ``"ISO 27001:2022"`` → ``"ISO/IEC 27001:2022"``.
    """
    from scholar_mcp._sync_relaton import _canonical_identifier_and_body

    docidentifiers = [
        {"type": "ISO", "id": "ISO 27001:2022", "primary": True},
        {"type": "IEC", "id": "IEC 27001:2022"},
    ]
    result = _canonical_identifier_and_body(docidentifiers)
    assert result == ("ISO/IEC 27001:2022", "ISO/IEC")


def test_canonical_primary_entry_fallback() -> None:
    """When neither ISO nor IEC entries exist, primary=True entry is used."""
    from scholar_mcp._sync_relaton import _canonical_identifier_and_body

    docidentifiers = [
        {"type": "URN", "id": "urn:iso:std:iso:9999:ed-1", "primary": True},
    ]
    result = _canonical_identifier_and_body(docidentifiers)
    assert result == ("urn:iso:std:iso:9999:ed-1", "URN")


def test_canonical_no_matching_entry_returns_none() -> None:
    """No ISO/IEC entry and no primary entry → None."""
    from scholar_mcp._sync_relaton import _canonical_identifier_and_body

    result = _canonical_identifier_and_body([{"type": "OTHER", "id": "X 1"}])
    assert result is None


# ---------------------------------------------------------------------------
# _first_link_of_type coverage
# ---------------------------------------------------------------------------


def test_first_link_of_type_not_found_returns_none() -> None:
    """Empty links list returns None."""
    from scholar_mcp._sync_relaton import _first_link_of_type

    assert _first_link_of_type([], "src") is None


def test_first_link_of_type_finds_later_entry() -> None:
    """When the first entry doesn't match, a later one is returned."""
    from scholar_mcp._sync_relaton import _first_link_of_type

    links = [
        {"type": "obp", "content": "https://obp.example.com"},
        {"type": "src", "content": "https://src.example.com"},
    ]
    assert _first_link_of_type(links, "src") == "https://src.example.com"


# ---------------------------------------------------------------------------
# _first_title coverage
# ---------------------------------------------------------------------------


def test_first_title_plain_string() -> None:
    """When titles[0] is a plain string, it is returned as-is."""
    from scholar_mcp._sync_relaton import _first_title

    assert _first_title(["Some Title"]) == "Some Title"


def test_first_title_empty_list() -> None:
    from scholar_mcp._sync_relaton import _first_title

    assert _first_title([]) == ""


# ---------------------------------------------------------------------------
# _published_date coverage
# ---------------------------------------------------------------------------


def test_published_date_no_published_type_returns_none() -> None:
    """Date entries with no 'published' type → None."""
    from scholar_mcp._sync_relaton import _published_date

    dates = [{"type": "updated", "value": "2023-01-01"}]
    assert _published_date(dates) is None


def test_published_date_no_date_key_returns_none() -> None:
    """Published entry without a 'value' key → None (falls through)."""
    from scholar_mcp._sync_relaton import _published_date

    dates = [{"type": "published"}]  # missing 'value'
    assert _published_date(dates) is None


# ---------------------------------------------------------------------------
# _superseded_by coverage
# ---------------------------------------------------------------------------


def test_superseded_by_relation_absent() -> None:
    from scholar_mcp._sync_relaton import _superseded_by

    assert _superseded_by(None) is None


def test_superseded_by_non_obsoleted_relation_returns_none() -> None:
    """A 'replaces' relation should NOT match."""
    from scholar_mcp._sync_relaton import _superseded_by

    relations = [
        {
            "type": "replaces",
            "bibitem": {"docidentifier": [{"id": "ISO 9001:2008"}]},
        }
    ]
    assert _superseded_by(relations) is None


def test_superseded_by_happy_path() -> None:
    """obsoleted-by relation returns the successor identifier."""
    from scholar_mcp._sync_relaton import _superseded_by

    doc = _load_fixture("relaton_iso_sample/iso-9001-2008.yaml")
    assert _superseded_by(doc.get("relation")) == "ISO 9001:2015"


# ---------------------------------------------------------------------------
# _supersedes coverage
# ---------------------------------------------------------------------------


def test_supersedes_obsoletes_relation() -> None:
    """'obsoletes' relation populates the supersedes list."""
    from scholar_mcp._sync_relaton import _supersedes

    relations = [
        {
            "type": "obsoletes",
            "bibitem": {"docidentifier": [{"id": "ISO 9001:2008"}]},
        }
    ]
    assert _supersedes(relations) == ["ISO 9001:2008"]


def test_supersedes_empty_when_no_relations() -> None:
    from scholar_mcp._sync_relaton import _supersedes

    assert _supersedes(None) == []


# ---------------------------------------------------------------------------
# _committee coverage
# ---------------------------------------------------------------------------


def test_committee_none_editorialgroup() -> None:
    from scholar_mcp._sync_relaton import _committee

    assert _committee(None) is None


def test_committee_dash_variant() -> None:
    """editorialgroup uses 'technical-committee' (dash) key."""
    from scholar_mcp._sync_relaton import _committee

    eg = {"technical-committee": [{"name": "TC 176"}]}
    assert _committee(eg) == "TC 176"


# ---------------------------------------------------------------------------
# _yaml_to_record miscellaneous branches
# ---------------------------------------------------------------------------


def test_yaml_to_record_alias_non_string_skipped() -> None:
    """A docidentifier entry whose id is not a string must be skipped."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [
            {"id": "ISO 9001:2015", "type": "ISO", "primary": True},
            {"id": 12345, "type": "NUMERIC"},  # non-string id
        ],
        "title": [{"content": "Quality management"}],
    }
    record, aliases = _yaml_to_record(doc)

    assert record is not None
    assert 12345 not in aliases
    assert all(isinstance(a, str) for a in aliases)


def test_yaml_to_record_abstract_plain_string() -> None:
    """When abstract[0] is a plain string, scope remains None."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [{"id": "ISO 9001:2015", "type": "ISO", "primary": True}],
        "title": [{"content": "Quality management"}],
        "abstract": ["Plain text scope — not a dict"],
    }
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["scope"] is None


def test_yaml_to_record_unknown_stage_defaults_to_published() -> None:
    """An unrecognised stage code defaults to 'published' and logs a debug message."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [{"id": "ISO 9001:2015", "type": "ISO", "primary": True}],
        "title": [{"content": "Quality management"}],
        "docstatus": {"stage": "99.99"},  # not in _STAGE_TO_STATUS
    }
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["status"] == "published"
