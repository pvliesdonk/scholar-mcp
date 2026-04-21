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


def test_canonical_joint_rewrites_iec_text() -> None:
    """Both ISO and IEC entries present, IEC entry is selected as joint.

    The branch ``elif ident.startswith("IEC ")`` must rewrite
    ``"IEC 27001:2022"`` → ``"ISO/IEC 27001:2022"``.
    """
    from scholar_mcp._sync_relaton import _canonical_identifier_and_body

    docidentifiers = [
        {"type": "IEC", "id": "IEC 27001:2022", "primary": True},
        {"type": "ISO", "id": "ISO 27001:2022"},
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


def test_superseded_by_reads_docid_key_in_relation() -> None:
    """bibitem.docid is accepted (mirrors the top-level docid fix)."""
    from scholar_mcp._sync_relaton import _superseded_by

    relations = [
        {
            "type": "obsoleted-by",
            "bibitem": {"docid": [{"id": "ISO 9001:2015"}]},
        }
    ]
    assert _superseded_by(relations) == "ISO 9001:2015"


def test_supersedes_reads_docid_key_in_relation() -> None:
    """bibitem.docid is accepted for obsoletes relations too."""
    from scholar_mcp._sync_relaton import _supersedes

    relations = [
        {
            "type": "obsoletes",
            "bibitem": {"docid": [{"id": "ISO 9001:2008"}]},
        }
    ]
    assert _supersedes(relations) == ["ISO 9001:2008"]


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
                "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
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

        # Joint record carries body='ISO/IEC'
        joint = await cache.get_standard("ISO/IEC 27001:2022")
        assert joint is not None
        assert joint["body"] == "ISO/IEC"
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
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
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
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
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
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
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
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
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
            if request.url.path.endswith("/commits/main"):
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
# Task 7: Withdrawal detection + >50% mass-disappearance guard
# ---------------------------------------------------------------------------


def _tarball_without(fixture_dir: Path, skip_names: set[str], prefix: str) -> bytes:
    """Tarball that OMITS specific filenames — used to simulate withdrawals."""
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


@pytest.mark.asyncio
async def test_loader_marks_missing_records_withdrawn(tmp_path, iso_tarball) -> None:
    """A record present on first sync, absent on second → status='withdrawn'."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        async with httpx.AsyncClient() as http:
            with respx.mock(assert_all_called=False) as router:
                # First sync — full fixture set
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
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

            # Second sync — tarball omits one file
            shrunk = _tarball_without(
                FIXTURES / "relaton_iso_sample",
                skip_names={"iso-14001-2015.yaml"},
                prefix="relaton-data-iso-main",
            )
            with respx.mock(assert_all_called=False) as router:
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
                ).mock(return_value=httpx.Response(200, json={"sha": "v2"}))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/tarball/v2"
                ).mock(return_value=httpx.Response(200, content=shrunk))

                second = await loader.sync(cache)

        assert second.withdrawn == 1

        withdrawn_record = await cache.get_standard("ISO 14001:2015")
        assert withdrawn_record is not None
        assert withdrawn_record["status"] == "withdrawn"
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_loader_aborts_withdrawal_on_mass_disappearance(
    tmp_path, iso_tarball
) -> None:
    """Tarball missing >50% of prior ids → withdrawal pass skipped, error logged."""
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        async with httpx.AsyncClient() as http:
            with respx.mock(assert_all_called=False) as router:
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
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
                prior_ids = await cache.list_synced_standard_ids(source="ISO")
                # Capture statuses before second sync for change-detection
                prior_statuses = {
                    ident: (await cache.get_standard(ident) or {}).get("status")
                    for ident in prior_ids
                }

            # Build a "disaster" tarball with only the first fixture file,
            # guaranteeing >50% of prior ids are missing.
            all_files = sorted(
                p.name for p in (FIXTURES / "relaton_iso_sample").glob("*.yaml")
            )
            keep_one = set(all_files) - {all_files[0]}
            disaster = _tarball_without(
                FIXTURES / "relaton_iso_sample",
                skip_names=keep_one,
                prefix="relaton-data-iso-main",
            )
            with respx.mock(assert_all_called=False) as router:
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
                ).mock(return_value=httpx.Response(200, json={"sha": "v2"}))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/tarball/v2"
                ).mock(return_value=httpx.Response(200, content=disaster))

                second = await loader.sync(cache)

        assert second.withdrawn == 0
        assert any("withdrawal pass aborted" in e for e in second.errors)
        # Prior rows must remain untouched — none flipped to 'withdrawn' by the pass
        for ident in prior_ids:
            record = await cache.get_standard(ident)
            before = prior_statuses.get(ident)
            after = record.get("status") if record else None
            # A record that was NOT already withdrawn before must not be withdrawn now
            if before != "withdrawn":
                assert after != "withdrawn", (
                    f"{ident!r} was flipped to 'withdrawn' despite mass-disappearance guard"
                )
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
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
                ).mock(return_value=httpx.Response(200, json={"sha": "iso-sha"}))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/tarball/iso-sha"
                ).mock(return_value=httpx.Response(200, content=iso_tarball))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iec/commits/main"
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
        assert joint["body"] == "ISO/IEC"
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
                    "https://api.github.com/repos/relaton/relaton-data-iec/commits/main"
                ).mock(return_value=httpx.Response(200, json={"sha": "iec-sha"}))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iec/tarball/iec-sha"
                ).mock(return_value=httpx.Response(200, content=iec_tarball))
                router.get(
                    "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
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
        assert joint["body"] == "ISO/IEC"
        assert joint["status"] == "published"
        # And no duplicate row accidentally written under an ISO-only identifier
        iso_only = await cache.get_standard("ISO 27001:2022")
        assert iso_only is None
    finally:
        await cache.close()


def test_yaml_to_record_reads_docid_key() -> None:
    """Real relaton repos use top-level 'docid:', not 'docidentifier:'.

    Regression guard — the parser must accept both shapes so live-fetched
    records from raw.githubusercontent.com parse into full records (not
    fallback stubs).
    """
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_test_cases/iso-9001-2015-docid-shape.yaml")
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["identifier"] == "ISO 9001:2015"
    assert record["body"] == "ISO"
    assert "Quality management" in record["title"]


def test_yaml_to_record_falls_back_to_docidentifier_key() -> None:
    """Old-shape fixtures with 'docidentifier:' still work."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_iso_sample/iso-9001-2015.yaml")
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["identifier"] == "ISO 9001:2015"


def test_yaml_to_record_plain_ieee() -> None:
    """Pure IEEE entry → body='IEEE', identifier preserved verbatim."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_ieee_sample/ieee-1003-1-2024.yaml")
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["identifier"] == "IEEE 1003.1-2024"
    assert record["body"] == "IEEE"
    assert "POSIX" in record["title"]


def test_yaml_to_record_iec_ieee_joint() -> None:
    """docid list with IEC + IEEE entries → body='IEC/IEEE'."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_ieee_sample/iec-ieee-61588-2021.yaml")
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["identifier"] == "IEC/IEEE 61588-2021"
    assert record["body"] == "IEC/IEEE"


def test_yaml_to_record_iso_iec_ieee_joint() -> None:
    """docid list with ISO + IEC + IEEE entries → body='ISO/IEC/IEEE'."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_ieee_sample/iso-iec-ieee-42010-2011.yaml")
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["body"] == "ISO/IEC/IEEE"
    assert "ISO/IEC/IEEE 42010" in record["identifier"]
    # trademark variant (with ™) is filtered — canonical must NOT include the ™ suffix
    assert "™" not in record["identifier"]


def test_yaml_to_record_ieee_skips_trademark_scope() -> None:
    """scope: trademark entries are filtered out when picking canonical."""
    from scholar_mcp._sync_relaton import _yaml_to_record

    doc = _load_fixture("relaton_ieee_sample/ieee-1003-1-2024-with-trademark.yaml")
    record, _ = _yaml_to_record(doc)

    assert record is not None
    assert record["identifier"] == "IEEE 1003.1-2024"
    assert "™" not in record["identifier"]


@pytest.mark.asyncio
async def test_loader_cold_sync_inserts_ieee_records(
    tmp_path: Path, ieee_tarball: bytes
) -> None:
    """Cold sync of IEEE fixtures exercises the full RelatonLoader path.

    The four fixture YAML files map to three unique canonical identifiers
    (the trademark fixture and the plain fixture both resolve to
    ``IEEE 1003.1-2024``; alphabetical iteration means the trademark
    version inserts first and the plain version updates it). Guards
    against wiring regressions between RelatonLoader, _yaml_to_record,
    and _canonical_identifier_and_body for IEEE inputs including the
    IEC/IEEE and ISO/IEC/IEEE joint detection.
    """
    from scholar_mcp._cache import ScholarCache
    from scholar_mcp._sync_relaton import RelatonLoader

    cache = ScholarCache(tmp_path / "cache.db")
    await cache.open()
    try:
        sha = "deadbeef" * 5
        with respx.mock(assert_all_called=False) as router:
            router.get(
                "https://api.github.com/repos/relaton/relaton-data-ieee/commits/main"
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
        assert report.updated == 1
        assert report.body == "IEEE"
        assert report.upstream_ref == sha

        plain = await cache.get_standard("IEEE 1003.1-2024")
        assert plain is not None
        assert plain["body"] == "IEEE"
        assert "POSIX" in plain["title"]

        iec_ieee = await cache.get_standard("IEC/IEEE 61588-2021")
        assert iec_ieee is not None
        assert iec_ieee["body"] == "IEC/IEEE"

        iso_iec_ieee = await cache.get_standard("ISO/IEC/IEEE 42010-2011")
        assert iso_iec_ieee is not None
        assert iso_iec_ieee["body"] == "ISO/IEC/IEEE"
        assert "™" not in iso_iec_ieee["identifier"]
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
docid:
  - id: "ISO/IEC 15408-1:2022"
    type: "ISO"
    primary: true
title:
  - content: "Information technology - Security techniques - Evaluation criteria"
    format: "text/plain"
    type: "main"
docstatus:
  stage: "60.60"
"""
    loaded_yaml = b"""
docid:
  - id: "ISO 9999:2022"
    type: "ISO"
    primary: true
title:
  - content: "Some other ISO standard"
    format: "text/plain"
    type: "main"
docstatus:
  stage: "60.60"
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
                "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
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
docid:
  - id: "IEC 99999:2022"
    type: "IEC"
    primary: true
title:
  - content: "Defensive test for per-body skip-list"
    format: "text/plain"
    type: "main"
docstatus:
  stage: "60.60"
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
                "https://api.github.com/repos/relaton/relaton-data-iec/commits/main"
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
        entries=[("other/iso-9001-2015.yaml", b"docid:\n  - id: ISO 9001:2015\n")],
    )
    records, errors = _parse_tarball_sync(_open_tarball(tb), "ISO", frozenset())
    assert records == []
    assert errors == []


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
docid:
  - id: "ISO 9001:2015"
    type: "ISO"
    primary: true
title:
  - content: "Quality management systems"
    format: "text/plain"
    type: "main"
docstatus:
  stage: "60.60"
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
docid:
  - id: "ISO 9001:2015"
    type: "ISO"
    primary: true
title:
  - content: "Quality management"
    format: "text/plain"
    type: "main"
docstatus:
  stage: "60.60"
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
                "https://api.github.com/repos/relaton/relaton-data-iso/commits/main"
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
