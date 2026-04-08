"""Standards lookup client: identifier resolver, source fetchers, StandardsClient."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns for local identifier resolution
# ---------------------------------------------------------------------------

# IETF RFC: "RFC 9000", "rfc9000", "rfc-9000", "RFC9000"
_IETF_RFC_RE = re.compile(r"(?i)\brfc[-\s]?(\d+)\b")
# IETF BCP: "BCP 47", "BCP47"
_IETF_BCP_RE = re.compile(r"(?i)\bbcp[-\s]?(\d+)\b")
# IETF STD: "STD 66", "STD66"
_IETF_STD_RE = re.compile(r"(?i)\bstd[-\s]?(\d+)\b")

# NIST SP with optional revision: "SP 800-53 Rev. 5", "SP800-53r5", "NIST SP 800-53 Rev 5"
_NIST_SP_REV_RE = re.compile(
    r"(?i)\b(?:nist\s+)?sp\s*(\d{3,4}(?:-\d+)?[A-Z]?)\s*r(?:ev\.?\s*)?(\d)\b"
)
# NIST SP without revision: "NIST SP 800-53", "SP800-53", "nist 800-53"
_NIST_SP_RE = re.compile(r"(?i)\b(?:nist\s+)?sp\s*(\d{3,4}(?:-\d+)?[A-Z]?)\b")
# NIST SP shorthand: "nist 800-53 rev 5" (number only after "nist")
_NIST_NUM_REV_RE = re.compile(r"(?i)\bnist\s+(\d{3,4}(?:-\d+)?)\s+r(?:ev\.?\s*)?(\d)\b")
_NIST_NUM_RE = re.compile(r"(?i)\bnist\s+(\d{3,4}(?:-\d+)?)\b")
# NIST FIPS: "FIPS 140-3", "FIPS140-3", "FIPS PUB 140-3"
_NIST_FIPS_RE = re.compile(r"(?i)\bfips(?:\s+pub)?\s*(\d{1,3}(?:-\d+)?)\b")
# NIST IR: "NISTIR 8259A", "NISTIR8259A"
_NIST_IR_RE = re.compile(r"(?i)\bnistir\s*(\d{4}[A-Z]?)\b")

# W3C: "WCAG 2.1", "WCAG2.1", "W3C WCAG 2.1", "WebAuthn Level 2"
_W3C_WCAG_RE = re.compile(r"(?i)\bwcag\s*(\d+\.\d+)\b")
_W3C_WEBAUTHN_RE = re.compile(r"(?i)\bwebauthn\s+level\s+(\d+)\b")

# ETSI: "ETSI EN 303 645", "etsi en 303645", "ETSI TS 102 165"
# Require explicit "etsi" prefix to avoid false positives with other European bodies (CEN, CENELEC)
_ETSI_RE = re.compile(
    r"(?i)\betsi\s+(EN|TS|TR|ES|EG)\s*(\d{3})\s*[\s-]?\s*(\d{3})\b"
)


def _resolve_identifier_local(raw: str) -> tuple[str, str] | None:
    """Attempt to resolve *raw* to (canonical_identifier, body) using only regex.

    Returns ``None`` when no Tier 1 pattern matches.

    Args:
        raw: Raw citation string from a paper reference.

    Returns:
        Tuple of (canonical_identifier, body) or None.
    """
    s = raw.strip()

    # IETF RFC (check before NIST to avoid "RFC" matching NIST patterns)
    m = _IETF_RFC_RE.search(s)
    if m:
        return f"RFC {int(m.group(1))}", "IETF"

    # IETF BCP
    m = _IETF_BCP_RE.search(s)
    if m:
        return f"BCP {int(m.group(1))}", "IETF"

    # IETF STD
    m = _IETF_STD_RE.search(s)
    if m:
        return f"STD {int(m.group(1))}", "IETF"

    # NIST FIPS
    m = _NIST_FIPS_RE.search(s)
    if m:
        return f"FIPS {m.group(1)}", "NIST"

    # NIST IR
    m = _NIST_IR_RE.search(s)
    if m:
        return f"NISTIR {m.group(1).upper()}", "NIST"

    # NIST SP with revision (must check before without-revision to capture rev)
    m = _NIST_SP_REV_RE.search(s)
    if m:
        return f"NIST SP {m.group(1)} Rev. {m.group(2)}", "NIST"

    # NIST SP without revision
    m = _NIST_SP_RE.search(s)
    if m:
        return f"NIST SP {m.group(1)}", "NIST"

    # NIST shorthand with revision: "nist 800-53 rev 5"
    m = _NIST_NUM_REV_RE.search(s)
    if m:
        return f"NIST SP {m.group(1)} Rev. {m.group(2)}", "NIST"

    # NIST shorthand without revision: "nist 800-53"
    m = _NIST_NUM_RE.search(s)
    if m:
        return f"NIST SP {m.group(1)}", "NIST"

    # W3C WCAG
    m = _W3C_WCAG_RE.search(s)
    if m:
        return f"WCAG {m.group(1)}", "W3C"

    # W3C WebAuthn
    m = _W3C_WEBAUTHN_RE.search(s)
    if m:
        return f"WebAuthn Level {m.group(1)}", "W3C"

    # ETSI
    m = _ETSI_RE.search(s)
    if m:
        return f"ETSI {m.group(1).upper()} {m.group(2)} {m.group(3)}", "ETSI"

    return None
