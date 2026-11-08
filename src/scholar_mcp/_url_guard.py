"""Refuse downloads whose destination is not a public internet address.

`fetch_pdf_by_url` fetches a URL the caller chooses. Without a check, a
caller could make the server request hosts on its own network: loopback,
RFC 1918 ranges, link-local addresses such as cloud metadata endpoints
(#514). This module resolves a URL's host and refuses it unless every
address it resolves to is a public unicast address. Redirects are followed
here, one hop at a time, so each hop is checked before it is requested. The
paper download path applies the same check to the candidate URLs it takes
from upstream metadata (#573).

The check runs before the request, not at connect time, so a host whose DNS
answer changes between the check and the connection (DNS rebinding) is not
caught. Connect-time pinning would have to bypass a configured HTTP proxy,
which egress-restricted deployments rely on; see
``docs/design/pdf-downloads.md``.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

MAX_REDIRECTS = 10
"""Redirect hops followed before giving up, as `httpx.TooManyRedirects`."""

_IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

_NAT64_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")
"""RFC 6052 well-known prefix; its last 32 bits are an IPv4 address."""


class BlockedDestinationError(Exception):
    """A URL resolves to an address the server must not request.

    Attributes:
        url: The URL that was refused.
        address: The offending address, or the host when the URL has no
            usable host or scheme.
    """

    def __init__(self, url: str, address: str) -> None:
        """Record the refused URL and the address that caused the refusal.

        Args:
            url: The URL that was refused.
            address: The non-public address it resolved to, or the reason
                text when no address was involved.
        """
        super().__init__(f"{url} -> {address}")
        self.url = url
        self.address = address


def is_public_address(address: _IPAddress) -> bool:
    """Return whether an address is a public unicast internet address.

    IPv6 addresses that carry an IPv4 address are judged by that address:
    IPv4-mapped (``::ffff:127.0.0.1``), because the kernel connects to it,
    and the NAT64 well-known prefix (``64:ff9b::/96``), because a NAT64
    gateway forwards to it. Python already treats 6to4 (``2002::/16``) as
    not global.

    Args:
        address: The address to judge.

    Returns:
        ``True`` only for a global, non-multicast address.
    """
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            address = address.ipv4_mapped
        elif address in _NAT64_PREFIX:
            address = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    return address.is_global and not address.is_multicast


async def _resolve(host: str, port: int) -> list[str]:
    """Return every address the system resolver gives for ``host``.

    Args:
        host: A host name or address literal.
        port: The port the request would use.

    Returns:
        The resolved addresses as strings.

    Raises:
        socket.gaierror: The host does not resolve.
    """
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


async def check_public_url(url: str) -> None:
    """Refuse ``url`` unless its host resolves only to public addresses.

    Every resolved address must be public: a host with one public and one
    private address is refused, because the connection may use either.

    Args:
        url: An absolute ``http`` or ``https`` URL.

    Raises:
        BlockedDestinationError: The scheme is not HTTP(S), the URL has no
            host, or an address is not public.
        socket.gaierror: The host does not resolve.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BlockedDestinationError(url, parts.hostname or "no host")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    for text in await _resolve(parts.hostname, port):
        # Strip an IPv6 zone index ("fe80::1%eth0") before parsing.
        if not is_public_address(ipaddress.ip_address(text.split("%", 1)[0])):
            raise BlockedDestinationError(url, text)


async def get_public(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET ``url``, following redirects, refusing any non-public hop.

    Args:
        client: The client to send requests with. Its own
            ``follow_redirects`` setting is ignored.
        url: The first URL to request.

    Returns:
        The final, non-redirect response.

    Raises:
        BlockedDestinationError: The URL or a redirect target is not public.
        httpx.TooManyRedirects: More than `MAX_REDIRECTS` hops.
        httpx.HTTPError: The request itself failed.
        socket.gaierror: A host does not resolve.
    """
    await check_public_url(url)
    response = await client.get(url, follow_redirects=False)
    hops = 0
    while (next_request := response.next_request) is not None:
        if hops == MAX_REDIRECTS:
            raise httpx.TooManyRedirects(
                f"Exceeded {MAX_REDIRECTS} redirects", request=response.request
            )
        hops += 1
        await response.aclose()
        await check_public_url(str(next_request.url))
        response = await client.send(next_request, follow_redirects=False)
    return response
