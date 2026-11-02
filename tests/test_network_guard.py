"""Tests for the suite's network guard (`tests/conftest.py::_no_network`)."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any

import httpx
import pytest

from tests.conftest import NetworkGuard, _is_local_host


@pytest.mark.parametrize(
    "host",
    [
        None,
        "localhost",
        b"localhost",
        "LOCALHOST",
        "app.localhost",
        "127.0.0.1",
        "127.1.2.3",
        "::1",
        "[::1]",
        # The IPv4 wildcard, built rather than written: the literal trips the
        # structural gate's S104 ("binding to all interfaces"), and this is no bind.
        str(ipaddress.IPv4Address(0)),
        "::",
    ],
)
def test_local_hosts_are_allowed(host: object) -> None:
    """Loopback names and addresses, and the wildcard bind, count as local."""
    assert _is_local_host(host)


@pytest.mark.parametrize(
    "host",
    [
        "api.semanticscholar.org",
        b"api.openalex.org",
        "8.8.8.8",
        "2001:4860:4860::8888",
        "localhost.example.com",
        "",
    ],
)
def test_remote_hosts_are_refused(host: object) -> None:
    """Any other name or address is remote, including look-alikes."""
    assert not _is_local_host(host)


def test_guard_passes_local_lookups_through() -> None:
    """A local lookup reaches the real resolver with its arguments intact."""
    calls: list[tuple[Any, ...]] = []

    def fake_getaddrinfo(*args: Any, **kwargs: Any) -> str:
        calls.append((args, kwargs))
        return "resolved"

    guard = NetworkGuard(fake_getaddrinfo)
    assert guard.getaddrinfo("localhost", 80, type=socket.SOCK_STREAM) == "resolved"
    assert calls == [(("localhost", 80), {"type": socket.SOCK_STREAM})]
    assert guard.refused == []


def test_guard_records_and_refuses_remote_lookups() -> None:
    """A remote lookup never reaches the resolver; it is recorded and refused."""

    def fake_getaddrinfo(*args: Any, **kwargs: Any) -> str:  # noqa: ARG001
        raise AssertionError("the real resolver must not be called")

    guard = NetworkGuard(fake_getaddrinfo)
    with pytest.raises(socket.gaierror, match="network access blocked"):
        guard.getaddrinfo("api.semanticscholar.org", 443)
    with pytest.raises(socket.gaierror):
        guard.getaddrinfo(b"api.openalex.org", 443)
    assert guard.refused == ["api.semanticscholar.org", "api.openalex.org"]


async def test_guard_is_installed_for_httpx(_no_network: NetworkGuard | None) -> None:
    """An unmocked httpx request fails fast instead of reaching the internet."""
    assert _no_network is not None
    async with httpx.AsyncClient() as http:
        with pytest.raises(httpx.ConnectError):
            await http.get("https://api.semanticscholar.org/graph/v1/paper/x")
    assert _no_network.refused == ["api.semanticscholar.org"]
    # Clear the record, or the fixture's teardown would fail this test.
    _no_network.refused.clear()


@pytest.mark.live
def test_live_tests_are_exempt(_no_network: NetworkGuard | None) -> None:
    """A `live` test gets no guard, so it may reach real services."""
    assert _no_network is None
