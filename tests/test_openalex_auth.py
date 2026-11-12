"""The OpenAlex API key reaches OpenAlex alone, as a Bearer header."""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from pathlib import Path

import httpx
import pytest
import respx

from scholar_mcp.config import ProjectConfig
from scholar_mcp.domain import Service

_KEY = "oa-secret-key"
_DOI = "10.1/x"


async def _probe(config: ProjectConfig) -> tuple[httpx.Request, httpx.Request]:
    """Open the clients for *config*; return one OpenAlex and one CrossRef request."""
    service = Service(config)
    async with AsyncExitStack() as stack:
        service._open_clients(stack)
        with respx.mock:
            oa = respx.get(
                f"https://api.openalex.org/works/https://doi.org/{_DOI}"
            ).mock(return_value=httpx.Response(200, json={"id": "W1"}))
            cr = respx.get(f"https://api.crossref.org/works/{_DOI}").mock(
                return_value=httpx.Response(200, json={"message": {}})
            )
            await service.openalex.get_by_doi(_DOI)
            await service.crossref.get_by_doi(_DOI)
        return oa.calls.last.request, cr.calls.last.request


async def test_key_is_sent_to_openalex_only(tmp_path: Path) -> None:
    config = ProjectConfig(
        cache_dir=tmp_path,
        openalex_api_key=_KEY,
        contact_email="ops@example.org",
    )
    oa, cr = await _probe(config)
    assert oa.headers["Authorization"] == f"Bearer {_KEY}"
    assert _KEY not in str(oa.url)
    assert "mailto:ops@example.org" in oa.headers["User-Agent"]
    assert "Authorization" not in cr.headers


async def test_no_key_sends_no_authorization(tmp_path: Path) -> None:
    oa, cr = await _probe(ProjectConfig(cache_dir=tmp_path))
    assert "Authorization" not in oa.headers
    assert "Authorization" not in cr.headers


@pytest.mark.parametrize("status", [403, 429])
async def test_refusal_log_never_carries_the_key(
    tmp_path: Path, status: int, caplog: pytest.LogCaptureFixture
) -> None:
    from scholar_mcp._openalex_client import OpenAlexRefusedError

    service = Service(ProjectConfig(cache_dir=tmp_path, openalex_api_key=_KEY))
    caplog.set_level(logging.DEBUG)
    async with AsyncExitStack() as stack:
        service._open_clients(stack)
        with respx.mock:
            respx.get(f"https://api.openalex.org/works/https://doi.org/{_DOI}").mock(
                return_value=httpx.Response(status, json={"error": "key_not_activated"})
            )
            with pytest.raises(OpenAlexRefusedError):
                await service.openalex.get_by_doi(_DOI)
    assert caplog.records, "a refusal must be logged"
    for record in caplog.records:
        assert _KEY not in record.getMessage()
