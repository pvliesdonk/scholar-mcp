"""Tests for StandardsClient, source fetchers, and identifier resolver."""

from __future__ import annotations

from scholar_mcp._standards_client import _resolve_identifier_local

# --- Resolver: IETF ---


def test_resolve_rfc_with_space() -> None:
    result = _resolve_identifier_local("RFC 9000")
    assert result == ("RFC 9000", "IETF")


def test_resolve_rfc_no_space() -> None:
    result = _resolve_identifier_local("rfc9000")
    assert result == ("RFC 9000", "IETF")


def test_resolve_rfc_hyphen() -> None:
    result = _resolve_identifier_local("rfc-9000")
    assert result == ("RFC 9000", "IETF")


def test_resolve_rfc_tls() -> None:
    result = _resolve_identifier_local("RFC 8446")
    assert result == ("RFC 8446", "IETF")


# --- Resolver: NIST SP ---


def test_resolve_nist_sp_full() -> None:
    result = _resolve_identifier_local("NIST SP 800-53 Rev. 5")
    assert result == ("NIST SP 800-53 Rev. 5", "NIST")


def test_resolve_nist_sp_abbreviated_rev() -> None:
    result = _resolve_identifier_local("SP800-53r5")
    assert result == ("NIST SP 800-53 Rev. 5", "NIST")


def test_resolve_nist_sp_space_rev() -> None:
    result = _resolve_identifier_local("nist 800-53 rev 5")
    assert result == ("NIST SP 800-53 Rev. 5", "NIST")


def test_resolve_nist_sp_no_rev() -> None:
    result = _resolve_identifier_local("NIST SP 800-53")
    assert result == ("NIST SP 800-53", "NIST")


def test_resolve_nist_fips() -> None:
    result = _resolve_identifier_local("FIPS 140-3")
    assert result == ("FIPS 140-3", "NIST")


def test_resolve_nist_fips_no_space() -> None:
    result = _resolve_identifier_local("FIPS140-3")
    assert result == ("FIPS 140-3", "NIST")


def test_resolve_nistir() -> None:
    result = _resolve_identifier_local("NISTIR 8259A")
    assert result == ("NISTIR 8259A", "NIST")


def test_resolve_nist_fips_pub_form() -> None:
    result = _resolve_identifier_local("FIPS PUB 140-3")
    assert result == ("FIPS 140-3", "NIST")


def test_resolve_nistir_no_space() -> None:
    result = _resolve_identifier_local("NISTIR8259A")
    assert result == ("NISTIR 8259A", "NIST")


# --- Resolver: W3C ---


def test_resolve_wcag_with_prefix() -> None:
    result = _resolve_identifier_local("W3C WCAG 2.1")
    assert result == ("WCAG 2.1", "W3C")


def test_resolve_wcag_no_prefix() -> None:
    result = _resolve_identifier_local("WCAG 2.1")
    assert result == ("WCAG 2.1", "W3C")


def test_resolve_wcag_no_space() -> None:
    result = _resolve_identifier_local("WCAG2.1")
    assert result == ("WCAG 2.1", "W3C")


# --- Resolver: ETSI ---


def test_resolve_etsi_en_with_spaces() -> None:
    result = _resolve_identifier_local("ETSI EN 303 645")
    assert result == ("ETSI EN 303 645", "ETSI")


def test_resolve_etsi_en_no_spaces() -> None:
    result = _resolve_identifier_local("etsi en 303645")
    assert result == ("ETSI EN 303 645", "ETSI")


# --- Resolver: unrecognised ---


def test_resolve_unknown_returns_none() -> None:
    result = _resolve_identifier_local("some random text")
    assert result is None


def test_resolve_iec_series_returns_none() -> None:
    # IEC 62443 is Tier 2 — not handled by local Tier 1 resolver
    result = _resolve_identifier_local("62443")
    assert result is None
