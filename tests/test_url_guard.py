"""Tests for the public-destination guard on caller-chosen URLs (#514)."""

from __future__ import annotations

import ipaddress
import socket

import httpx
import pytest
import respx

from scholar_mcp import _url_guard
from scholar_mcp._url_guard import (
    MAX_REDIRECTS,
    BlockedDestinationError,
    check_public_url,
    get_public,
    is_public_address,
)

PUBLIC = "93.184.216.34"


def _resolver(table: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    """Return a fake ``_resolve`` answering from ``table``, else refusing."""

    async def fake(host: str, port: int) -> list[str]:  # noqa: ARG001
        if host not in table:
            raise socket.gaierror(socket.EAI_NONAME, "unknown host")
        return table[host]

    return fake


@pytest.mark.parametrize(
    ("text", "public"),
    [
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("172.16.0.1", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("224.0.0.1", False),
        ("::1", False),
        ("fe80::1", False),
        ("fd00::1", False),
        ("::ffff:127.0.0.1", False),
        ("::ffff:8.8.8.8", True),
        ("8.8.8.8", True),
        ("2001:4860:4860::8888", True),
    ],
)
def test_is_public_address(text: str, public: bool) -> None:
    assert is_public_address(ipaddress.ip_address(text)) is public


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com/a.pdf", "file:///etc/passwd", "https:///nohost.pdf"],
)
async def test_check_refuses_non_http_or_hostless(url: str) -> None:
    with pytest.raises(BlockedDestinationError):
        await check_public_url(url)


async def test_check_refuses_a_host_with_any_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One public and one private answer is refused: either may be used."""
    monkeypatch.setattr(
        _url_guard, "_resolve", _resolver({"mixed.test": [PUBLIC, "10.0.0.5"]})
    )
    with pytest.raises(BlockedDestinationError) as info:
        await check_public_url("https://mixed.test/a.pdf")
    assert info.value.address == "10.0.0.5"


async def test_check_strips_ipv6_zone_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _url_guard, "_resolve", _resolver({"ll.test": ["fe80::1%eth0"]})
    )
    with pytest.raises(BlockedDestinationError):
        await check_public_url("http://ll.test/a.pdf")


async def test_check_accepts_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_url_guard, "_resolve", _resolver({"pub.test": [PUBLIC]}))
    await check_public_url("https://pub.test:8443/a.pdf")


async def test_check_lets_resolution_failure_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_url_guard, "_resolve", _resolver({}))
    with pytest.raises(socket.gaierror):
        await check_public_url("https://nowhere.test/a.pdf")


async def test_resolve_returns_address_literal() -> None:
    """The real resolver passes a loopback literal straight through."""
    assert "127.0.0.1" in await _url_guard._resolve("127.0.0.1", 80)


async def test_refuses_an_address_literal_without_dns() -> None:
    with pytest.raises(BlockedDestinationError) as info:
        await check_public_url("http://127.0.0.1:8080/x.pdf")
    assert info.value.address == "127.0.0.1"


async def test_get_public_refuses_a_redirect_to_a_private_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The private hop is never requested."""
    monkeypatch.setattr(
        _url_guard,
        "_resolve",
        _resolver({"pub.test": [PUBLIC], "internal.test": ["192.168.0.10"]}),
    )
    with respx.mock(assert_all_called=False) as router:
        router.get("https://pub.test/a.pdf").mock(
            return_value=httpx.Response(
                302, headers={"Location": "http://internal.test/secret.pdf"}
            )
        )
        internal = router.get("http://internal.test/secret.pdf").mock(
            return_value=httpx.Response(200, content=b"%PDF-1.7")
        )
        async with httpx.AsyncClient() as client:
            with pytest.raises(BlockedDestinationError) as info:
                await get_public(client, "https://pub.test/a.pdf")
    assert info.value.url == "http://internal.test/secret.pdf"
    assert not internal.called


async def test_get_public_follows_public_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _url_guard, "_resolve", _resolver({"a.test": [PUBLIC], "b.test": [PUBLIC]})
    )
    with respx.mock() as router:
        router.get("https://a.test/x").mock(
            return_value=httpx.Response(301, headers={"Location": "https://b.test/y"})
        )
        router.get("https://b.test/y").mock(
            return_value=httpx.Response(200, content=b"%PDF-1.7 ok")
        )
        async with httpx.AsyncClient() as client:
            response = await get_public(client, "https://a.test/x")
    assert response.content == b"%PDF-1.7 ok"


async def test_get_public_stops_after_max_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_url_guard, "_resolve", _resolver({"loop.test": [PUBLIC]}))
    with respx.mock() as router:
        router.get("https://loop.test/x").mock(
            return_value=httpx.Response(
                302, headers={"Location": "https://loop.test/x"}
            )
        )
        async with httpx.AsyncClient() as client:
            with pytest.raises(httpx.TooManyRedirects):
                await get_public(client, "https://loop.test/x")
        assert router.calls.call_count == MAX_REDIRECTS + 1
