"""Tests for _sync_relaton: YAML mapper, joint detection, record-changed."""

from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

import httpx
import pytest
import respx
import yaml

FIXTURES = Path(__file__).parent / "fixtures" / "standards"


def _load_fixture(relative: str) -> dict:
    with (FIXTURES / relative).open() as f:
        return yaml.safe_load(f)


def test_yaml_to_record_plain_iso() -> None:
    """A real v2 ISO record maps identifier, title, date, links and aliases."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_iso_sample/iso-9001-2015.yaml")
    record, aliases = _yaml_to_record(doc)

    assert record is not None
    assert record["identifier"] == "ISO 9001:2015"
    assert record["body"] == "ISO"
    assert record["title"] == "Quality management systems - Requirements"
    assert record["published_date"] == "2015-09-22"
    assert record["url"] == "https://www.iso.org/standard/62085.html"
    assert record["full_text_url"] == "https://www.iso.org/obp/ui/en/#!iso:std:62085:en"
    assert record["committee"] == "ISO/TC 176/SC 2"
    assert record["supersedes"] == ["ISO 9001:2008", "ISO 9001:2008/Cor 1:2009"]
    assert record["full_text_available"] is False
    assert aliases == ["ISO 9001:2015(E)", "urn:iso:std:iso:9001:stage-95.99"]


def test_yaml_to_record_joint_iso_iec_identifier() -> None:
    """A joint record keeps the slash form of its identifier."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_iso_sample/iso-iec-27001-2022.yaml")
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["identifier"] == "ISO/IEC 27001:2022"
    assert record["status"] == "published"
    assert record["superseded_by"] == []


def test_yaml_to_record_iec_only() -> None:
    """A real v2 IEC record → body='IEC', committee from the subdivision name."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_iec_sample/iec-62443-3-3-2013.yaml")
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["body"] == "IEC"
    assert record["identifier"] == "IEC 62443-3-3:2013"
    assert record["status"] == "published"
    assert record["committee"] == "TC 65"


def test_yaml_to_record_withdrawn_iso_edition_is_superseded() -> None:
    """ISO/IEC 27001:2005, withdrawn at 95.99, names 2013 under obsoletedBy (#641)."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_iso_sample/iso-iec-27001-2005.yaml")
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["status"] == "superseded"
    assert record["superseded_by"] == ["ISO/IEC 27001:2013"]


@pytest.mark.parametrize(
    ("fixture", "status", "superseded_by"),
    [
        ("cd-iwa-37.yaml", "withdrawn", []),
        ("iec-dis-80000-15.yaml", "draft", []),
        ("iec-60335-2-91-1997-cor1-2000.yaml", "superseded", []),
        ("iec-60191-2r-1995.yaml", "withdrawn", []),
        ("ieee-std-1588-2008.yaml", "superseded", ["IEC 61588-2009"]),
        ("ieee-p1547-3-d7-feb-2007.yaml", "draft", []),
        ("ieee-std-254-1963.yaml", "withdrawn", []),
        ("ieee-std-1301-4-1996.yaml", "withdrawn", []),
        ("ieee-std-524-2016-redline.yaml", "published", []),
    ],
    ids=[
        "iso-abandoned-project-30.98",
        "iso-draft-40.60",
        "iec-95.99-revised",
        "iec-95.99-withdrawn",
        "ieee-standard-status-superseded",
        "ieee-stage-draft",
        "ieee-stage-withdrawn",
        "ieee-standard-status-inactive",
        "ieee-standard-status-active",
    ],
)
def test_yaml_to_record_status_from_v2_stage(
    fixture: str, status: str, superseded_by: list[str]
) -> None:
    """Each body's v2 stage maps to a status (#641)."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    record, _ = _yaml_to_record(_load_fixture(f"relaton_v2_status/{fixture}"))

    assert record is not None
    assert record["status"] == status
    assert record["superseded_by"] == superseded_by


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("60.60", "published"),
        ("90.20", "published"),
        ("90.93", "published"),
        ("95.20", "published"),
        ("95.60", "withdrawn"),
        ("95.99", "withdrawn"),
        ("60.00", "draft"),
        ("20.20", "draft"),
        ("40.98", "withdrawn"),
    ],
)
def test_harmonized_status(code: str, status: str) -> None:
    from scholar_mcp._sync_relaton import _harmonized_status

    assert _harmonized_status(code) == status


def test_current_edition_keeps_empty_superseded_by_despite_draft_revision() -> None:
    """ISO links a confirmed edition to its revision's draft; that is no replacement."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [{"content": "ISO 1:2016", "type": "ISO", "primary": True}],
        "title": [{"content": "Length", "type": "main"}],
        "status": {"stage": {"content": "90"}, "substage": {"content": "92"}},
        "relation": [
            {
                "type": "obsoletedBy",
                "bibitem": {"docidentifier": [{"content": "ISO/DIS 1"}]},
            }
        ],
    }
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["status"] == "published"
    assert record["superseded_by"] == []


def test_yaml_to_record_missing_identifier_returns_none() -> None:
    """Document without any docidentifier returns (None, [])."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    record, aliases = _yaml_to_record({"title": [{"content": "orphan"}]})

    assert record is None
    assert aliases == []


def test_yaml_to_record_missing_title_returns_none() -> None:
    """Document with no title is unusable — returns (None, [])."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [{"content": "ISO 123:2020", "type": "ISO", "primary": True}]
    }
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
        {"type": "ISO", "content": "ISO 27001:2022", "primary": True},
        {"type": "IEC", "content": "IEC 27001:2022"},
    ]
    result = _canonical_identifier_and_body(docidentifiers)
    assert result == ("ISO/IEC 27001:2022", "ISO/IEC")


def test_canonical_joint_rewrites_iec_text() -> None:
    """Both ISO and IEC entries present, IEC entry is selected as joint.

    The branch ``elif ident.startswith("IEC ")`` must rewrite
    ``"IEC 27001:2022"`` → ``"ISO/IEC 27001:2022"``.
    """
    from scholar_mcp._sync_relaton import _canonical_identifier_and_body

    docidentifiers = [
        {"type": "IEC", "content": "IEC 27001:2022", "primary": True},
        {"type": "ISO", "content": "ISO 27001:2022"},
    ]
    result = _canonical_identifier_and_body(docidentifiers)
    assert result == ("ISO/IEC 27001:2022", "ISO/IEC")


def test_canonical_iec_ieee_joint() -> None:
    from scholar_mcp._sync_relaton import _canonical_identifier_and_body

    docidentifiers = [
        {"type": "IEEE", "content": "IEC/IEEE 61588-2021", "primary": True},
        {"type": "IEC", "content": "IEC 61588:2021"},
    ]
    assert _canonical_identifier_and_body(docidentifiers) == (
        "IEC/IEEE 61588-2021",
        "IEC/IEEE",
    )


def test_canonical_iso_iec_ieee_joint() -> None:
    from scholar_mcp._sync_relaton import _canonical_identifier_and_body

    docidentifiers = [
        {"type": "IEEE", "content": "ISO/IEC/IEEE 42010-2011", "primary": True},
        {"type": "ISO", "content": "ISO/IEC/IEEE 42010:2011"},
        {"type": "IEC", "content": "ISO/IEC/IEEE 42010:2011"},
    ]
    assert _canonical_identifier_and_body(docidentifiers) == (
        "ISO/IEC/IEEE 42010-2011",
        "ISO/IEC/IEEE",
    )


def test_canonical_primary_entry_fallback() -> None:
    """When neither ISO nor IEC entries exist, primary=True entry is used."""
    from scholar_mcp._sync_relaton import _canonical_identifier_and_body

    docidentifiers = [
        {"type": "URN", "content": "urn:iso:std:iso:9999:ed-1", "primary": True},
    ]
    result = _canonical_identifier_and_body(docidentifiers)
    assert result == ("urn:iso:std:iso:9999:ed-1", "URN")


def test_canonical_no_matching_entry_returns_none() -> None:
    """No ISO/IEC entry and no primary entry → None."""
    from scholar_mcp._sync_relaton import _canonical_identifier_and_body

    result = _canonical_identifier_and_body([{"type": "OTHER", "content": "X 1"}])
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
# _full_title coverage
# ---------------------------------------------------------------------------


def test_full_title_plain_string() -> None:
    """When titles[0] is a plain string, it is returned as-is."""
    from scholar_mcp._sync_relaton import _full_title

    assert _full_title(["Some Title"]) == "Some Title"


def test_full_title_empty_list() -> None:
    from scholar_mcp._sync_relaton import _full_title

    assert _full_title([]) == ""


# ---------------------------------------------------------------------------
# _published_date coverage
# ---------------------------------------------------------------------------


def test_published_date_no_published_type_returns_none() -> None:
    """Date entries with no 'published' type → None."""
    from scholar_mcp._sync_relaton import _published_date

    dates = [{"type": "updated", "at": "2023-01-01"}]
    assert _published_date(dates) is None


def test_published_date_no_date_key_returns_none() -> None:
    """Published entry without an 'at' key → None (falls through)."""
    from scholar_mcp._sync_relaton import _published_date

    dates = [{"type": "published"}]  # missing 'at'
    assert _published_date(dates) is None


# ---------------------------------------------------------------------------
# _related_identifiers coverage
# ---------------------------------------------------------------------------


def test_related_identifiers_relation_absent() -> None:
    from scholar_mcp._sync_relaton import _related_identifiers

    assert _related_identifiers(None, "obsoletedBy") == []


def test_related_identifiers_ignores_other_types() -> None:
    """updatedBy names an amendment, not a replacement; the main spelling is gone."""
    from scholar_mcp._sync_relaton import _related_identifiers

    relations = [
        {
            "type": "updatedBy",
            "bibitem": {"docidentifier": [{"content": "ISO 9001:2008/Cor 1:2009"}]},
        },
        {
            "type": "obsoleted-by",
            "bibitem": {"docidentifier": [{"content": "ISO 9001:2015"}]},
        },
    ]
    assert _related_identifiers(relations, "obsoletedBy") == []


def test_related_identifiers_reads_a_real_record() -> None:
    from scholar_mcp._sync_relaton import _related_identifiers

    doc = _load_fixture("relaton_iso_sample/iso-9001-2008.yaml")
    assert _related_identifiers(doc["relation"], "obsoletedBy") == ["ISO 9001:2015"]
    assert _related_identifiers(doc["relation"], "obsoletes") == ["ISO 9001:2000"]


def test_related_identifiers_lists_every_match_in_order() -> None:
    """Each matching relation contributes one identifier, in order (#637)."""
    from scholar_mcp._sync_relaton import _related_identifiers

    relations = [
        {
            "type": "obsoletedBy",
            "bibitem": {"docidentifier": [{"content": "ISO 1:2020"}]},
        },
        {
            "type": "updates",
            "bibitem": {"docidentifier": [{"content": "ISO 1:2019/Amd 1"}]},
        },
        {
            "type": "obsoletedBy",
            "bibitem": {"docidentifier": [{"content": "ISO 2:2021"}]},
        },
    ]
    assert _related_identifiers(relations, "obsoletedBy") == [
        "ISO 1:2020",
        "ISO 2:2021",
    ]


def test_related_identifiers_lists_a_repeated_relation_once() -> None:
    from scholar_mcp._sync_relaton import _related_identifiers

    relation = {
        "type": "obsoletedBy",
        "bibitem": {"docidentifier": [{"content": "IEEE Std 776-2018"}]},
    }
    assert _related_identifiers([relation, relation], "obsoletedBy") == [
        "IEEE Std 776-2018"
    ]


# ---------------------------------------------------------------------------
# _committee coverage
# ---------------------------------------------------------------------------


def test_committee_none_contributors() -> None:
    from scholar_mcp._sync_relaton import _committee

    assert _committee(None) is None


@pytest.mark.parametrize(
    ("fixture", "committee"),
    [
        ("relaton_iso_sample/iso-iec-27001-2022.yaml", "ISO/IEC JTC 1/SC 27"),
        ("relaton_iec_sample/iec-62443-3-3-2013.yaml", "TC 65"),
        (
            "relaton_ieee_sample/ieee-std-1003-1-2024.yaml",
            "Microprocessor Standards Committee of the IEEE Computer Society",
        ),
    ],
    ids=["iso-identifier", "iec-number-only-uses-name", "ieee-name-only"],
)
def test_committee_from_author_subdivision(fixture: str, committee: str) -> None:
    from scholar_mcp._sync_relaton import _committee

    assert _committee(_load_fixture(fixture)["contributor"]) == committee


def test_committee_skips_publisher_and_malformed_entries() -> None:
    from scholar_mcp._sync_relaton import _committee

    contributors = [
        "not a mapping",
        {
            "role": [{"type": "publisher"}],
            "organization": {"subdivision": [{"name": [{"content": "Not it"}]}]},
        },
        {
            "role": [{"type": "author"}],
            "organization": {"subdivision": ["bad", {"identifier": [], "name": []}]},
        },
    ]
    assert _committee(contributors) is None


# ---------------------------------------------------------------------------
# _yaml_to_record miscellaneous branches
# ---------------------------------------------------------------------------


def test_yaml_to_record_alias_skips_undated_and_non_string() -> None:
    """The iso-undated entry and a non-string content are not aliases."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [
            {"content": "ISO 9001:2015", "type": "ISO", "primary": True},
            {"content": "ISO 9001", "type": "iso-undated"},
            {"content": 12345, "type": "NUMERIC"},  # non-string id
            {"content": "ISO 9001:2015(E)", "type": "iso-reference"},
        ],
        "title": [{"content": "Quality management"}],
    }
    _, aliases = _yaml_to_record(doc)

    assert aliases == ["ISO 9001:2015(E)"]


def test_yaml_to_record_abstract_plain_string() -> None:
    """When abstract[0] is a plain string, scope remains None."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [{"content": "ISO 9001:2015", "type": "ISO", "primary": True}],
        "title": [{"content": "Quality management"}],
        "abstract": ["Plain text scope — not a dict"],
    }
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["scope"] is None


def test_yaml_to_record_unknown_stage_defaults_to_published() -> None:
    """An unrecognised stage word defaults to 'published' and logs a debug message."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [{"content": "ISO 9001:2015", "type": "ISO", "primary": True}],
        "title": [{"content": "Quality management"}],
        "status": {"stage": {"content": "SOMETHING"}},
    }
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["status"] == "published"


# ---------------------------------------------------------------------------
# RelatonLoader tests (Task 6)
# ---------------------------------------------------------------------------


def _build_tarball(fixture_dir: Path, prefix: str = "relaton-data-iso-main") -> bytes:
    """Build an in-memory .tar.gz matching GitHub's tarball layout.

    GitHub tarballs prefix every entry with '<repo>-<sha7>/', and YAML
    files live under '<prefix>/data/'.
    """
    buf = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buf, mode="wb") as gz,
        tarfile.open(fileobj=gz, mode="w") as tar,
    ):
        for yaml_path in sorted(fixture_dir.glob("*.yaml")):
            data = yaml_path.read_bytes()
            info = tarfile.TarInfo(name=f"{prefix}/data/{yaml_path.name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def iso_tarball() -> bytes:
    return _build_tarball(FIXTURES / "relaton_iso_sample")


@pytest.fixture
def iec_tarball() -> bytes:
    return _build_tarball(
        FIXTURES / "relaton_iec_sample", prefix="relaton-data-iec-main"
    )


@pytest.fixture
def ieee_tarball() -> bytes:
    return _build_tarball(
        FIXTURES / "relaton_ieee_sample", prefix="relaton-data-ieee-main"
    )


@pytest.mark.asyncio
async def test_loader_cold_sync_inserts_records(tmp_path, iso_tarball) -> None:
    """Cold sync (empty cache) inserts every fixture row with added=N."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        with respx.mock(assert_all_called=False) as router:
            router.get(
                "https://api.github.com/repos/relaton/relaton-data-iso/commits/v2"
            ).mock(return_value=httpx.Response(200, json={"sha": "deadbeef"}))
            router.get(
                "https://api.github.com/repos/relaton/relaton-data-iso/tarball/deadbeef"
            ).mock(return_value=httpx.Response(200, content=iso_tarball))

            async with httpx.AsyncClient() as http:
                loader = RelatonLoader(body="ISO", http=http)
                report = await loader.sync(cache)

        assert report.body == "ISO"
        assert report.added > 0
        assert report.updated == 0
        assert report.unchanged == 0
        assert report.upstream_ref == "deadbeef"

        # Rows must be findable via their canonical identifiers
        iso_9001 = await cache.get_standard("ISO 9001:2015")
        assert iso_9001 is not None
        assert iso_9001["title"].startswith("Quality management")

        # The #641 symptom, end to end: a withdrawn edition names its successor.
        old_27001 = await cache.get_standard("ISO/IEC 27001:2005")
        assert old_27001 is not None
        assert old_27001["status"] == "superseded"
        assert old_27001["superseded_by"] == ["ISO/IEC 27001:2013"]
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_loader_resync_same_sha_returns_unchanged(tmp_path, iso_tarball) -> None:
    """Second call with the same SHA skips tarball fetch, reports unchanged."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        async with httpx.AsyncClient() as http:
            with respx.mock(assert_all_called=False) as router:
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/v2"
                ).mock(return_value=httpx.Response(200, json={"sha": "same-sha"}))
                tarball_route = router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/tarball/same-sha"
                ).mock(return_value=httpx.Response(200, content=iso_tarball))

                loader = RelatonLoader(body="ISO", http=http)
                first = await loader.sync(cache)
                # Persist the upstream_ref the way run_sync would
                await cache.set_sync_run(
                    body=first.body,
                    upstream_ref=first.upstream_ref,
                    added=first.added,
                    updated=first.updated,
                    unchanged=first.unchanged,
                    withdrawn=first.withdrawn,
                    errors=first.errors,
                    started_at=first.started_at or 0.0,
                    finished_at=first.finished_at or 0.0,
                )

                # Second run — tarball should NOT be fetched
                tarball_route.reset()
                second = await loader.sync(cache)

        assert second.added == 0
        assert second.updated == 0
        assert second.unchanged > 0
        assert not tarball_route.called
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_loader_force_bypasses_sha_check(tmp_path, iso_tarball) -> None:
    """force=True triggers a tarball fetch even when SHA is unchanged."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        async with httpx.AsyncClient() as http:
            with respx.mock(assert_all_called=False) as router:
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/v2"
                ).mock(return_value=httpx.Response(200, json={"sha": "same-sha"}))
                tarball_route = router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/tarball/same-sha"
                ).mock(return_value=httpx.Response(200, content=iso_tarball))

                loader = RelatonLoader(body="ISO", http=http)
                await loader.sync(cache)
                await cache.set_sync_run(
                    body="ISO",
                    upstream_ref="same-sha",
                    added=0,
                    updated=0,
                    unchanged=0,
                    withdrawn=0,
                    errors=[],
                    started_at=0.0,
                    finished_at=0.0,
                )
                tarball_route.reset()

                forced = await loader.sync(cache, force=True)

        assert tarball_route.called
        assert forced.upstream_ref == "same-sha"
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_loader_modified_record_increments_updated(tmp_path, iso_tarball) -> None:
    """A fixture record whose title changed upstream → updated == 1."""
    import copy

    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        async with httpx.AsyncClient() as http:
            with respx.mock(assert_all_called=False) as router:
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/v2"
                ).mock(return_value=httpx.Response(200, json={"sha": "v1"}))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/tarball/v1"
                ).mock(return_value=httpx.Response(200, content=iso_tarball))

                loader = RelatonLoader(body="ISO", http=http)
                first = await loader.sync(cache)
                await cache.set_sync_run(
                    body="ISO",
                    upstream_ref="v1",
                    added=first.added,
                    updated=0,
                    unchanged=0,
                    withdrawn=0,
                    errors=[],
                    started_at=0.0,
                    finished_at=0.0,
                )

            # Mutate ISO 9001:2015's cached row (simulate prior-sync drift)
            existing = await cache.get_standard("ISO 9001:2015")
            assert existing is not None
            mutated = copy.deepcopy(existing)
            mutated["title"] = "STALE TITLE"
            await cache.set_standard(
                "ISO 9001:2015", mutated, source="ISO", synced=True
            )

            with respx.mock(assert_all_called=False) as router:
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/v2"
                ).mock(return_value=httpx.Response(200, json={"sha": "v2"}))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/tarball/v2"
                ).mock(return_value=httpx.Response(200, content=iso_tarball))

                second = await loader.sync(cache)

        assert second.updated == 1
        refreshed = await cache.get_standard("ISO 9001:2015")
        assert refreshed is not None
        assert refreshed["title"].startswith("Quality management")
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_loader_sends_github_token_header(tmp_path, iso_tarball) -> None:
    """When token is set, Authorization header is attached to GitHub calls."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        seen_auth: list[str | None] = []

        def _capture(request: httpx.Request) -> httpx.Response:
            seen_auth.append(request.headers.get("Authorization"))
            if request.url.path.endswith("/commits/v2"):
                return httpx.Response(200, json={"sha": "abc"})
            return httpx.Response(200, content=iso_tarball)

        with respx.mock(assert_all_called=False) as router:
            router.route(host="api.github.com").mock(side_effect=_capture)

            async with httpx.AsyncClient() as http:
                loader = RelatonLoader(body="ISO", http=http, token="ghp_xyz")
                await loader.sync(cache)

        assert seen_auth  # at least one request captured
        assert all(a == "token ghp_xyz" for a in seen_auth)
    finally:
        await cache.close()


# ---------------------------------------------------------------------------
# Removal of identifiers the dump no longer lists (#641)
# ---------------------------------------------------------------------------


def _tarball_without(fixture_dir: Path, skip_names: set[str], prefix: str) -> bytes:
    """Tarball that OMITS specific filenames — used to simulate removals."""
    buf = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buf, mode="wb") as gz,
        tarfile.open(fileobj=gz, mode="w") as tar,
    ):
        for yaml_path in sorted(fixture_dir.glob("*.yaml")):
            if yaml_path.name in skip_names:
                continue
            data = yaml_path.read_bytes()
            info = tarfile.TarInfo(name=f"{prefix}/data/{yaml_path.name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


async def _sync_twice(cache, first: bytes, second: bytes, body: str = "ISO"):
    """Run a sync over *first*, then over *second* under a new commit."""
    from scholar_mcp._sync_relaton import RelatonLoader

    repo = f"https://api.github.com/repos/relaton/relaton-data-{body.lower()}"
    async with httpx.AsyncClient() as http:
        loader = RelatonLoader(body=body, http=http)
        reports = []
        for sha, tarball in (("v1", first), ("v2", second)):
            with respx.mock(assert_all_called=False) as router:
                router.get(f"{repo}/commits/v2").mock(
                    return_value=httpx.Response(200, json={"sha": sha})
                )
                router.get(f"{repo}/tarball/{sha}").mock(
                    return_value=httpx.Response(200, content=tarball)
                )
                reports.append(await loader.sync(cache))
    return reports


@pytest.mark.asyncio
async def test_loader_removes_records_the_dump_no_longer_lists(
    tmp_path, iso_tarball
) -> None:
    """v2 keeps withdrawn editions, so a missing identifier is deleted, not withdrawn."""
    from scholar_mcp._cache import ScholarCache

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        await cache.set_standard_alias("ISO 14001:2015(E)", "ISO 14001:2015")
        shrunk = _tarball_without(
            FIXTURES / "relaton_iso_sample",
            skip_names={"iso-14001-2015.yaml"},
            prefix="relaton-data-iso-v2",
        )
        _, second = await _sync_twice(cache, iso_tarball, shrunk)

        assert second.removed == 1
        assert second.withdrawn == 0
        assert await cache.get_standard("ISO 14001:2015") is None
        assert await cache.get_standard_alias("ISO 14001:2015(E)") is None
        assert await cache.get_standard("ISO 9001:2015") is not None
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_loader_removes_renamed_identifiers_even_past_half(tmp_path) -> None:
    """The move to v2 renamed most IEEE drafts; every old identifier goes in one run."""
    from scholar_mcp._cache import ScholarCache

    def _record(ident: str) -> bytes:
        return f"""
docidentifier:
  - content: "{ident}"
    type: "IEEE"
    primary: true
title:
  - content: "Draft {ident}"
    type: "main"
""".encode()

    old = {f"data/old-{n}.yaml": _record(f"IEEE P{n}/D-1-2020-01") for n in range(4)}
    new = {
        f"data/new-{n}.yaml": _record(f"IEEE P{n}/D1, January 2020") for n in range(4)
    }
    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        _, second = await _sync_twice(
            cache,
            _make_tarball(prefix="relaton-data-ieee-v1", files=old),
            _make_tarball(prefix="relaton-data-ieee-v2", files=new),
            body="IEEE",
        )

        assert second.removed == 4
        assert second.errors == []
        assert await cache.list_synced_standard_ids(source="IEEE") == {
            f"IEEE P{n}/D1, January 2020" for n in range(4)
        }
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_loader_refuses_removal_when_the_dump_shrinks_below_half(
    tmp_path, iso_tarball
) -> None:
    """A dump under half the previous count looks truncated: nothing is deleted."""
    from scholar_mcp._cache import ScholarCache

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        all_files = sorted(
            p.name for p in (FIXTURES / "relaton_iso_sample").glob("*.yaml")
        )
        disaster = _tarball_without(
            FIXTURES / "relaton_iso_sample",
            skip_names=set(all_files[1:]),
            prefix="relaton-data-iso-v2",
        )
        first, second = await _sync_twice(cache, iso_tarball, disaster)

        assert second.removed == 0
        assert any("removal pass aborted" in e for e in second.errors)
        assert len(await cache.list_synced_standard_ids(source="ISO")) == first.added
    finally:
        await cache.close()


# ---------------------------------------------------------------------------
# Task 7: Joint-dedup tests (both body orderings)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loader_joint_dedup_iso_then_iec(
    tmp_path, iso_tarball, iec_tarball
) -> None:
    """Syncing ISO then IEC leaves joint records as one row per identifier."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        async with httpx.AsyncClient() as http:
            with respx.mock(assert_all_called=False) as router:
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/v2"
                ).mock(return_value=httpx.Response(200, json={"sha": "iso-sha"}))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/tarball/iso-sha"
                ).mock(return_value=httpx.Response(200, content=iso_tarball))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iec/commits/v2"
                ).mock(return_value=httpx.Response(200, json={"sha": "iec-sha"}))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iec/tarball/iec-sha"
                ).mock(return_value=httpx.Response(200, content=iec_tarball))

                iso_loader = RelatonLoader(body="ISO", http=http)
                iec_loader = RelatonLoader(body="IEC", http=http)
                await iso_loader.sync(cache)
                await cache.set_sync_run(
                    body="ISO",
                    upstream_ref="iso-sha",
                    added=0,
                    updated=0,
                    unchanged=0,
                    withdrawn=0,
                    errors=[],
                    started_at=0.0,
                    finished_at=0.0,
                )
                await iec_loader.sync(cache)

        joint = await cache.get_standard("ISO/IEC 27001:2022")
        assert joint is not None
        assert joint["status"] == "published"
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_loader_joint_dedup_iec_then_iso(
    tmp_path, iso_tarball, iec_tarball
) -> None:
    """Reverse order leaves the same final joint row — one per identifier."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        async with httpx.AsyncClient() as http:
            with respx.mock(assert_all_called=False) as router:
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iec/commits/v2"
                ).mock(return_value=httpx.Response(200, json={"sha": "iec-sha"}))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iec/tarball/iec-sha"
                ).mock(return_value=httpx.Response(200, content=iec_tarball))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/v2"
                ).mock(return_value=httpx.Response(200, json={"sha": "iso-sha"}))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/tarball/iso-sha"
                ).mock(return_value=httpx.Response(200, content=iso_tarball))

                iec_loader = RelatonLoader(body="IEC", http=http)
                iso_loader = RelatonLoader(body="ISO", http=http)
                await iec_loader.sync(cache)
                await cache.set_sync_run(
                    body="IEC",
                    upstream_ref="iec-sha",
                    added=0,
                    updated=0,
                    unchanged=0,
                    withdrawn=0,
                    errors=[],
                    started_at=0.0,
                    finished_at=0.0,
                )
                await iso_loader.sync(cache)

        joint = await cache.get_standard("ISO/IEC 27001:2022")
        assert joint is not None
        assert joint["status"] == "published"
        # And no duplicate row accidentally written under an ISO-only identifier
        iso_only = await cache.get_standard("ISO 27001:2022")
        assert iso_only is None
    finally:
        await cache.close()


def test_yaml_to_record_plain_ieee() -> None:
    """A real v2 IEEE record: identifier keeps 'Std', the ™ entry is no canonical."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_ieee_sample/ieee-std-1003-1-2024.yaml")
    record, aliases = _yaml_to_record(doc)

    assert record is not None
    assert record["identifier"] == "IEEE Std 1003.1-2024"
    assert record["body"] == "IEEE"
    assert record["status"] == "published"
    assert "Portable Operating System Interface" in record["title"]
    assert "IEEE Std 1003.1™-2024" in aliases


@pytest.mark.parametrize(
    ("fixture", "identifier"),
    [
        ("iec-ieee-61588-2021.yaml", "IEC/IEEE 61588-2021"),
        ("iso-iec-ieee-42010-2011.yaml", "ISO/IEC/IEEE 42010-2011"),
    ],
)
def test_yaml_to_record_ieee_joint_identifier(fixture: str, identifier: str) -> None:
    """A joint record from the IEEE dump keeps its slash identifier, without ™."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    record, _ = _yaml_to_record(_load_fixture(f"relaton_ieee_sample/{fixture}"))

    assert record is not None
    assert record["identifier"] == identifier


@pytest.mark.asyncio
async def test_loader_cold_sync_inserts_ieee_records(
    tmp_path: Path, ieee_tarball: bytes
) -> None:
    """Cold sync of IEEE fixtures exercises the full RelatonLoader path.

    The three fixture records map to three identifiers, two of them joint.
    Guards against wiring regressions between RelatonLoader, _yaml_to_record
    and _canonical_identifier_and_body for IEEE inputs.
    """
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        sha = "deadbeef" * 5
        with respx.mock(assert_all_called=False) as router:
            router.get(
                "https://api.github.com/repos/relaton/relaton-data-ieee/commits/v2"
            ).mock(return_value=httpx.Response(200, json={"sha": sha}))
            router.get(
                f"https://api.github.com/repos/relaton/relaton-data-ieee/tarball/{sha}"
            ).mock(
                return_value=httpx.Response(
                    200,
                    content=ieee_tarball,
                    headers={"Content-Type": "application/x-gzip"},
                )
            )

            async with httpx.AsyncClient() as http:
                loader = RelatonLoader("IEEE", http=http)
                report = await loader.sync(cache)

        assert report.added == 3
        assert report.updated == 0
        assert report.body == "IEEE"
        assert report.upstream_ref == sha

        plain = await cache.get_standard("IEEE Std 1003.1-2024")
        assert plain is not None
        assert plain["body"] == "IEEE"

        assert await cache.get_standard("IEC/IEEE 61588-2021") is not None
        assert await cache.get_standard("ISO/IEC/IEEE 42010-2011") is not None
    finally:
        await cache.close()


# ---------------------------------------------------------------------------
# Task 1: ISO loader denylist for shared-ownership slugs
# ---------------------------------------------------------------------------


def _make_tarball(*, prefix: str, files: dict[str, bytes]) -> bytes:
    """Build an in-memory .tar.gz from file contents."""
    buf = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buf, mode="wb") as gz,
        tarfile.open(fileobj=gz, mode="w") as tar,
    ):
        for name, data in files.items():
            info = tarfile.TarInfo(name=f"{prefix}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.mark.asyncio
async def test_iso_loader_skips_15408_slugs(tmp_path: Path) -> None:
    """ISO loader filters out ISO/IEC 15408 family — owned by CC loader."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    skipped_yaml = b"""
docidentifier:
  - content: "ISO/IEC 15408-1:2022"
    type: "ISO"
    primary: true
title:
  - content: "Information technology - Security techniques - Evaluation criteria"
    format: "text/plain"
    type: "main"
status:
  stage:
    content: "60"
  substage:
    content: "60"
"""
    loaded_yaml = b"""
docidentifier:
  - content: "ISO 9999:2022"
    type: "ISO"
    primary: true
title:
  - content: "Some other ISO standard"
    format: "text/plain"
    type: "main"
status:
  stage:
    content: "60"
  substage:
    content: "60"
"""

    tarball = _make_tarball(
        prefix="relaton-data-iso-main",
        files={
            "data/iso-iec-15408-1-2022.yaml": skipped_yaml,
            "data/iso-9999-2022.yaml": loaded_yaml,
        },
    )

    sha = "deadbeef" * 5
    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        with respx.mock(assert_all_called=False) as router:
            router.get(
                "https://api.github.com/repos/relaton/relaton-data-iso/commits/v2"
            ).mock(return_value=httpx.Response(200, json={"sha": sha}))
            router.get(
                f"https://api.github.com/repos/relaton/relaton-data-iso/tarball/{sha}"
            ).mock(
                return_value=httpx.Response(
                    200, content=tarball, headers={"Content-Type": "application/x-gzip"}
                )
            )

            async with httpx.AsyncClient() as http:
                loader = RelatonLoader("ISO", http=http)
                report = await loader.sync(cache)

        assert report.added == 1
        assert await cache.get_standard("ISO 9999:2022") is not None
        assert await cache.get_standard("ISO/IEC 15408-1:2022") is None
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_iso_loader_skip_slugs_only_apply_to_their_body(
    tmp_path: Path,
) -> None:
    """Skip-list is per-body; an IEC sync sees the slug only if listed under IEC."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    yaml_bytes = b"""
docidentifier:
  - content: "IEC 99999:2022"
    type: "IEC"
    primary: true
title:
  - content: "Defensive test for per-body skip-list"
    format: "text/plain"
    type: "main"
status:
  stage:
    content: "60"
  substage:
    content: "60"
"""
    tarball = _make_tarball(
        prefix="relaton-data-iec-main",
        files={"data/iso-iec-15408-1-2022.yaml": yaml_bytes},
    )

    sha = "cafef00d" * 5
    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        with respx.mock(assert_all_called=False) as router:
            router.get(
                "https://api.github.com/repos/relaton/relaton-data-iec/commits/v2"
            ).mock(return_value=httpx.Response(200, json={"sha": sha}))
            router.get(
                f"https://api.github.com/repos/relaton/relaton-data-iec/tarball/{sha}"
            ).mock(
                return_value=httpx.Response(
                    200, content=tarball, headers={"Content-Type": "application/x-gzip"}
                )
            )

            async with httpx.AsyncClient() as http:
                loader = RelatonLoader("IEC", http=http)
                report = await loader.sync(cache)

        assert report.added == 1
        assert await cache.get_standard("IEC 99999:2022") is not None
    finally:
        await cache.close()


# ---------------------------------------------------------------------------
# _parse_tarball_sync unit tests — covers error paths in the extracted function
# ---------------------------------------------------------------------------


def _make_tarball_raw(*, prefix: str, entries: list[tuple[str, bytes | None]]) -> bytes:
    """Build an in-memory .tar.gz with explicit control over entry types.

    Each entry is (name, content). Pass content=None to add a directory entry.
    """
    buf = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buf, mode="wb") as gz,
        tarfile.open(fileobj=gz, mode="w") as tar,
    ):
        for name, content in entries:
            if content is None:
                info = tarfile.TarInfo(name=f"{prefix}/{name}")
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            else:
                info = tarfile.TarInfo(name=f"{prefix}/{name}")
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _open_tarball(data: bytes) -> io.BytesIO:
    buf = io.BytesIO(data)
    buf.seek(0)
    return buf


def test_parse_tarball_sync_skips_directory_entries() -> None:
    """Non-file (directory) entries are skipped without error."""
    from scholar_mcp._sync_relaton import _parse_tarball_sync

    tb = _make_tarball_raw(
        prefix="repo-main",
        entries=[("data/", None)],  # directory entry
    )
    records, errors = _parse_tarball_sync(_open_tarball(tb), "ISO", frozenset())
    assert records == []
    assert errors == []


def test_parse_tarball_sync_skips_non_yaml_files() -> None:
    """Files not ending in .yaml are skipped."""
    from scholar_mcp._sync_relaton import _parse_tarball_sync

    tb = _make_tarball_raw(
        prefix="repo-main",
        entries=[("data/readme.txt", b"not yaml")],
    )
    records, errors = _parse_tarball_sync(_open_tarball(tb), "ISO", frozenset())
    assert records == []
    assert errors == []


def test_parse_tarball_sync_skips_yaml_outside_data_dir() -> None:
    """YAML files not under a /data/ path are silently ignored."""
    from scholar_mcp._sync_relaton import _parse_tarball_sync

    tb = _make_tarball_raw(
        prefix="repo-main",
        entries=[
            (
                "other/iso-9001-2015.yaml",
                b"docidentifier:\n  - content: ISO 9001:2015\n",
            )
        ],
    )
    records, errors = _parse_tarball_sync(_open_tarball(tb), "ISO", frozenset())
    assert records == []
    assert errors == []


def test_parse_tarball_sync_skips_iec_projects() -> None:
    """IEC's data/projects/ holds work items, not publications (#641)."""
    from scholar_mcp._sync_relaton import _parse_tarball_sync

    project = (FIXTURES / "relaton_iec_sample" / "iec-62443-3-3-2013.yaml").read_bytes()
    tb = _make_tarball_raw(
        prefix="repo-v2",
        entries=[
            ("data/projects/iec-62443-3-3-2013-ed1.yaml", project),
            ("data/iec-62443-3-3-2013.yaml", project),
        ],
    )
    records, errors = _parse_tarball_sync(_open_tarball(tb), "IEC", frozenset())
    assert errors == []
    assert [identifier for identifier, _, _ in records] == ["IEC 62443-3-3:2013"]


def test_parse_tarball_sync_reports_invalid_yaml() -> None:
    """A file with unparseable YAML bytes produces an error entry."""
    from scholar_mcp._sync_relaton import _parse_tarball_sync

    tb = _make_tarball_raw(
        prefix="repo-main",
        entries=[("data/bad.yaml", b"key: [unclosed")],
    )
    records, errors = _parse_tarball_sync(_open_tarball(tb), "ISO", frozenset())
    assert records == []
    assert len(errors) == 1
    assert "unparseable" in errors[0]
    assert "bad.yaml" in errors[0]


def test_parse_tarball_sync_reports_non_mapping_yaml() -> None:
    """A YAML file that parses to a list (not a dict) produces an error entry."""
    from scholar_mcp._sync_relaton import _parse_tarball_sync

    tb = _make_tarball_raw(
        prefix="repo-main",
        entries=[("data/list.yaml", b"- item1\n- item2\n")],
    )
    records, errors = _parse_tarball_sync(_open_tarball(tb), "ISO", frozenset())
    assert records == []
    assert len(errors) == 1
    assert "not a mapping" in errors[0]


def test_parse_tarball_sync_reports_unparseable_record() -> None:
    """A valid YAML dict that _yaml_to_record cannot map produces an error entry."""
    from scholar_mcp._sync_relaton import _parse_tarball_sync

    # No docidentifier and no title — _yaml_to_record returns None
    tb = _make_tarball_raw(
        prefix="repo-main",
        entries=[("data/no-id.yaml", b"scope: some text\n")],
    )
    records, errors = _parse_tarball_sync(_open_tarball(tb), "ISO", frozenset())
    assert records == []
    assert len(errors) == 1
    assert "unparseable" in errors[0]


def test_parse_tarball_sync_returns_valid_records() -> None:
    """Happy-path: valid YAML files in /data/ are parsed and returned."""
    from scholar_mcp._sync_relaton import _parse_tarball_sync

    valid_yaml = b"""
docidentifier:
  - content: "ISO 9001:2015"
    type: "ISO"
    primary: true
title:
  - content: "Quality management systems"
    format: "text/plain"
    type: "main"
status:
  stage:
    content: "60"
  substage:
    content: "60"
"""
    tb = _make_tarball_raw(
        prefix="repo-main",
        entries=[("data/iso-9001-2015.yaml", valid_yaml)],
    )
    records, errors = _parse_tarball_sync(_open_tarball(tb), "ISO", frozenset())
    assert errors == []
    assert len(records) == 1
    identifier, record, _aliases = records[0]
    assert identifier == "ISO 9001:2015"
    assert record.get("body") == "ISO"


def test_parse_tarball_sync_skips_symlink_entries() -> None:
    """Symlink members (extractfile returns None) are skipped without error."""
    from scholar_mcp._sync_relaton import _parse_tarball_sync

    buf = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buf, mode="wb") as gz,
        tarfile.open(fileobj=gz, mode="w") as tar,
    ):
        info = tarfile.TarInfo(name="repo-main/data/link.yaml")
        info.type = tarfile.SYMTYPE
        info.linkname = "target.yaml"
        tar.addfile(info)
    buf.seek(0)
    records, errors = _parse_tarball_sync(buf, "ISO", frozenset())
    assert records == []
    assert errors == []


@pytest.mark.asyncio
async def test_loader_within_batch_unchanged_duplicate(tmp_path: Path) -> None:
    """Two identical entries for the same identifier count as added=1, unchanged=1."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    same_yaml = b"""
docidentifier:
  - content: "ISO 9001:2015"
    type: "ISO"
    primary: true
title:
  - content: "Quality management"
    format: "text/plain"
    type: "main"
status:
  stage:
    content: "60"
  substage:
    content: "60"
"""
    # Two files with identical content → same canonical identifier resolved twice
    tarball = _make_tarball(
        prefix="relaton-data-iso-main",
        files={
            "data/iso-9001-2015-copy1.yaml": same_yaml,
            "data/iso-9001-2015-copy2.yaml": same_yaml,
        },
    )

    sha = "aabbccdd"
    cache = ScholarCache(tmp_path / "c.db")
    await cache.open()
    try:
        with respx.mock(assert_all_called=False) as router:
            router.get(
                "https://api.github.com/repos/relaton/relaton-data-iso/commits/v2"
            ).mock(return_value=httpx.Response(200, json={"sha": sha}))
            router.get(
                f"https://api.github.com/repos/relaton/relaton-data-iso/tarball/{sha}"
            ).mock(return_value=httpx.Response(200, content=tarball))

            async with httpx.AsyncClient() as http:
                loader = RelatonLoader("ISO", http=http)
                report = await loader.sync(cache)

        assert report.added == 1
        assert report.updated == 0
        assert report.unchanged == 1
        assert await cache.get_standard("ISO 9001:2015") is not None
    finally:
        await cache.close()


# ---------------------------------------------------------------------------
# isinstance guard tests — ISO edge cases with non-dict list entries
# ---------------------------------------------------------------------------


def test_yaml_to_record_string_docidentifier_entries_skipped() -> None:
    """docidentifier list containing plain strings should not raise."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [
            "ISO 9001:2015",  # plain string — must be skipped, not crash
            {"content": "ISO 9001:2015", "type": "ISO", "primary": True},
        ],
        "title": [{"content": "Quality management"}],
    }
    record, aliases = _yaml_to_record(doc)

    assert record is not None
    assert record["identifier"] == "ISO 9001:2015"
    # The plain string entry should not appear in aliases
    assert "ISO 9001:2015" not in aliases


def test_yaml_to_record_string_relation_entries_skipped() -> None:
    """relation list containing plain strings should not raise."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [{"content": "ISO 9001:2008", "type": "ISO", "primary": True}],
        "title": [{"content": "Quality management (old)"}],
        "status": {"stage": {"content": "95"}, "substage": {"content": "99"}},
        "relation": [
            "obsoleted-by ISO 9001:2015",  # plain string — must be skipped
            {
                "type": "obsoletedBy",
                "bibitem": {
                    "docidentifier": [{"content": "ISO 9001:2015", "type": "ISO"}],
                },
            },
        ],
    }
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["superseded_by"] == ["ISO 9001:2015"]


def test_yaml_to_record_string_bibitem_skipped() -> None:
    """relation entry with bibitem as a string should not raise."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [{"content": "ISO 9001:2008", "type": "ISO", "primary": True}],
        "title": [{"content": "Quality management (old)"}],
        "status": {"stage": {"content": "95"}, "substage": {"content": "99"}},
        "relation": [
            {
                "type": "obsoletedBy",
                "bibitem": "ISO 9001:2015",  # string instead of dict
            },
        ],
    }
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["superseded_by"] == []


def test_yaml_to_record_string_ident_in_bibitem_skipped() -> None:
    """docid list inside relation.bibitem containing plain strings should not raise."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [{"content": "ISO 9001:2008", "type": "ISO", "primary": True}],
        "title": [{"content": "Quality management (old)"}],
        "status": {"stage": {"content": "95"}, "substage": {"content": "99"}},
        "relation": [
            {
                "type": "obsoletedBy",
                "bibitem": {
                    "docidentifier": ["ISO 9001:2015"],  # plain string in list
                },
            },
        ],
    }
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["superseded_by"] == []


def test_yaml_to_record_string_link_entries_skipped() -> None:
    """link list containing plain strings should not raise."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [{"content": "ISO 9001:2015", "type": "ISO", "primary": True}],
        "title": [{"content": "Quality management"}],
        "source": [
            "https://www.iso.org/standard/62085.html",  # plain string — must be skipped
            {"type": "src", "content": "https://www.iso.org/standard/62085.html"},
        ],
    }
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["url"] == "https://www.iso.org/standard/62085.html"


def test_yaml_to_record_string_date_entries_skipped() -> None:
    """date list containing plain strings should not raise."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [{"content": "ISO 9001:2015", "type": "ISO", "primary": True}],
        "title": [{"content": "Quality management"}],
        "date": [
            "2015-09-15",  # plain string — must be skipped
            {"type": "published", "at": "2015-09-15"},
        ],
    }
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["published_date"] == "2015-09-15"


def test_yaml_to_record_supersedes_string_entries_skipped() -> None:
    """relation 'obsoletes' entries containing string idents should not raise."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = {
        "docidentifier": [{"content": "ISO 9001:2015", "type": "ISO", "primary": True}],
        "title": [{"content": "Quality management"}],
        "relation": [
            {
                "type": "obsoletes",
                "bibitem": {
                    "docidentifier": ["ISO 9001:2008"],  # plain string in list
                },
            },
            {
                "type": "obsoletes",
                "bibitem": {
                    "docidentifier": [{"content": "ISO 9001:2008", "type": "ISO"}],
                },
            },
        ],
    }
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["supersedes"] == ["ISO 9001:2008"]


# ---------------------------------------------------------------------------
# #480: the composed ``main`` title, not whichever part comes first
# ---------------------------------------------------------------------------

# Title lists copied from relaton-data-iso, -iec and -ieee (fetched 2026-09-28).
_ISO_27002_TITLES = [
    {
        "content": "Information security, cybersecurity and privacy protection",
        "language": ["en"],
        "type": "title-intro",
    },
    {
        "content": "Information security controls",
        "language": ["en"],
        "type": "title-main",
    },
    {
        "content": "Information security, cybersecurity and privacy protection - "
        "Information security controls",
        "language": ["en"],
        "type": "main",
    },
    {
        "content": "Sécurité de l'information, cybersécurité et protection de la "
        "vie privée",
        "language": ["fr"],
        "type": "title-intro",
    },
    {
        "content": "Mesures de sécurité de l'information",
        "language": ["fr"],
        "type": "title-main",
    },
    {
        "content": "Sécurité de l'information, cybersécurité et protection de la "
        "vie privée - Mesures de sécurité de l'information",
        "language": ["fr"],
        "type": "main",
    },
]
_IEC_AMENDMENT_TITLES = [
    {"content": "Amendment 1", "language": "en", "type": "title-intro"},
    {
        "content": "Specification for CISPR radio interference measuring "
        "apparatus for the frequency range 0,15 MHz to 30 MHz",
        "language": "en",
        "type": "title-main",
    },
    {
        "content": "Amendment 1 - Specification for CISPR radio interference "
        "measuring apparatus for the frequency range 0,15 MHz to 30 MHz",
        "language": "en",
        "type": "main",
    },
    {"content": "Amendement 1", "language": "fr", "type": "title-intro"},
]
_IEEE_TITLES = [
    {
        "content": "IRE Standards on Antennas and Waveguides: Definitions for "
        "Waveguide Components, 1955",
        "language": None,
        "type": "main",
    },
]


@pytest.mark.parametrize(
    ("titles", "expected"),
    [
        (
            _ISO_27002_TITLES,
            "Information security, cybersecurity and privacy protection - "
            "Information security controls",
        ),
        (
            _IEC_AMENDMENT_TITLES,
            "Amendment 1 - Specification for CISPR radio interference "
            "measuring apparatus for the frequency range 0,15 MHz to 30 MHz",
        ),
        (
            _IEEE_TITLES,
            "IRE Standards on Antennas and Waveguides: Definitions for "
            "Waveguide Components, 1955",
        ),
        # French-only main: still better than a bare part.
        (
            [
                {"content": "Exigences", "language": ["fr"], "type": "title-main"},
                {"content": "Qualité - Exigences", "language": ["fr"], "type": "main"},
            ],
            "Qualité - Exigences",
        ),
        # No composed title at all: fall back to the first entry, as before.
        ([{"content": "orphan", "type": "title-main"}], "orphan"),
        # A main with no usable text is skipped, and so is a bad first entry.
        ([{"type": "main", "content": None}, {"type": "main", "content": "X"}], "X"),
        ([5], ""),
    ],
    ids=[
        "iso-list-language",
        "iec-string-language",
        "ieee-null-language",
        "non-english-main",
        "no-main",
        "empty-main-skipped",
        "unusable-entry",
    ],
)
def test_full_title_prefers_the_english_main_title(titles: list, expected: str) -> None:
    from scholar_mcp._sync_relaton import _full_title

    assert _full_title(titles) == expected


def test_iso_27001_and_27002_no_longer_share_a_title() -> None:
    """The observed symptom: two standards, one title-intro, one title."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    iso_27001_titles = [
        {
            "content": "Information security, cybersecurity and privacy protection",
            "language": ["en"],
            "type": "title-intro",
        },
        {
            "content": "Information security management systems",
            "language": ["en"],
            "type": "title-main",
        },
        {"content": "Requirements", "language": ["en"], "type": "title-part"},
        {
            "content": "Information security, cybersecurity and privacy protection - "
            "Information security management systems - Requirements",
            "language": ["en"],
            "type": "main",
        },
    ]
    first, _ = _yaml_to_record(
        {
            "docidentifier": [
                {"content": "ISO/IEC 27001:2022", "type": "ISO", "primary": True}
            ],
            "title": iso_27001_titles,
        }
    )
    second, _ = _yaml_to_record(
        {
            "docidentifier": [
                {"content": "ISO/IEC 27002:2022", "type": "ISO", "primary": True}
            ],
            "title": _ISO_27002_TITLES,
        }
    )
    assert first is not None and second is not None
    assert first["title"] != second["title"]
