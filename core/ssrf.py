"""SSRF protection and URL validation utilities.

Public contract (tests/contract/test_url_injection_fuzz.py):
- ``is_private_ip(ip_str)``   — True when an address (or every/any resolved
  address of a hostname) is private/loopback/reserved/link-local.
- ``resolve_and_check(url)``  — True only when *every* address the URL's host
  resolves to is public; encoded IP literals (hex/octal/decimal/shortened)
  are normalized before checking; DNS is resolved twice to narrow
  rebinding windows.
- ``assert_safe_url(url)``    — raises ValueError on unsafe URLs, True otherwise.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import List, Optional, Union
from urllib.parse import urlparse

_IP = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]

# Documentation-only IPv6 range (RFC 3849) — never routable.
_DOC_V6 = ipaddress.ip_network("2001:db8::/32")


def _parse_int(part: str) -> int:
    """Parse an integer honoring 0x/0o/0b prefixes and octal leading zeros."""
    try:
        return int(part, 0)
    except ValueError:
        pass
    if len(part) > 1 and part[0] == "0":
        return int(part, 8)  # inet_aton treats leading 0 as octal
    return int(part, 10)


def _normalize_ip_literal(value: str) -> Optional[_IP]:
    """Parse an IP literal that may use decimal/hex/octal/shortened encodings.

    Returns the parsed address, or None when *value* is not an IP literal.
    """
    s = str(value).strip().strip("[]").split("%", 1)[0]
    if not s:
        return None
    try:
        return ipaddress.ip_address(s)
    except ValueError:
        pass

    # inet_aton-style forms: a, a.b, a.b.c, a.b.c.d with 0x/0o/decimal parts.
    parts = s.split(".")
    if 1 <= len(parts) <= 4:
        try:
            ints = [_parse_int(p) for p in parts]
        except ValueError:
            ints = None
        if ints is not None:
            try:
                if len(ints) == 4:
                    if any(i > 0xFF for i in ints):
                        return None
                    return ipaddress.IPv4Address(
                        ".".join(str(i) for i in ints))
                # Short forms: everything except the last byte-group is a
                # full octet; the last value fills the remaining bytes.
                if any(i > 0xFF for i in ints[:-1]):
                    # Single large integer (e.g. 2130706433) is handled below.
                    if len(ints) == 1 and 0 <= ints[0] <= 0xFFFFFFFF:
                        return ipaddress.IPv4Address(ints[0])
                    return None
                last = ints[-1]
                max_last = 0xFF if len(ints) == 4 else (1 << (8 * (4 - len(ints) + 1))) - 1
                if not (0 <= last <= max_last):
                    return None
                octets = list(ints[:-1])
                remaining = 4 - len(octets)
                width = 8 * remaining
                for shift in range(width - 8, -1, -8):
                    octets.append((last >> shift) & 0xFF)
                return ipaddress.IPv4Address(".".join(str(o) for o in octets))
            except ValueError:
                return None

    # Whole-address integer forms: 0x7f000001, 017700000001, 2130706433.
    try:
        n = int(s, 0)
    except ValueError:
        if len(s) > 1 and s[0] == "0":
            try:
                n = int(s, 8)
            except ValueError:
                return None
        else:
            return None
    if 0 <= n <= 0xFFFFFFFF:
        try:
            return ipaddress.IPv4Address(n)
        except ValueError:
            return None
    return None


def _is_bad_ip(ip: _IP) -> bool:
    """True when the address must never be fetched from the pipeline."""
    try:
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        if (ip.is_private or ip.is_loopback or ip.is_reserved
                or ip.is_link_local or ip.is_multicast or ip.is_unspecified):
            return True
        if ip.version == 6 and ip in _DOC_V6:
            return True
        return False
    except Exception:
        return True


def _check_ip_literal(ip_str: str) -> bool:
    """True when *ip_str* is an IP literal that embeds an IPv4 address."""
    ip = _normalize_ip_literal(ip_str)
    if ip is None:
        return False
    return ip.version == 4 or getattr(ip, "ipv4_mapped", None) is not None


def _resolve_all(hostname: str) -> List[str]:
    addrinfo = socket.getaddrinfo(hostname, None)
    return [item[4][0] for item in addrinfo]


def is_private_ip(ip_str: str) -> bool:
    """True when the address is private — resolves hostnames, too."""
    ip = _normalize_ip_literal(ip_str)
    if ip is not None:
        return _is_bad_ip(ip)
    # Not a literal: resolve as a hostname; private if any address is private.
    try:
        resolved = _resolve_all(str(ip_str))
    except Exception:
        return False
    for ip_str_resolved in resolved:
        try:
            if _is_bad_ip(ipaddress.ip_address(ip_str_resolved)):
                return True
        except ValueError:
            return True
    return False


def _all_public(resolved: List[str]) -> bool:
    for ip_str in resolved:
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if _is_bad_ip(addr):
            return False
    return True


def resolve_and_check(url: str) -> bool:
    """True when every address *url*'s host resolves to is public.

    Encoded IP literals are normalized; hostnames are DNS-resolved twice
    to narrow DNS-rebinding (TOCTOU) windows.
    """
    try:
        parsed = urlparse(str(url))
        hostname = parsed.hostname
    except Exception:
        return False
    if not hostname:
        return False
    hostname = hostname.strip("[]").rstrip(".")

    ip = _normalize_ip_literal(hostname)
    if ip is not None:
        return not _is_bad_ip(ip)

    try:
        first = _resolve_all(hostname)
    except Exception:
        # Unresolvable host: nothing to connect to either way.
        return True
    if not _all_public(first):
        return False
    # Double-resolve: a host that flips to a private address between checks
    # (DNS rebinding) is rejected.
    try:
        second = _resolve_all(hostname)
    except Exception:
        return False
    return _all_public(second)


def assert_safe_url(url: str) -> bool:
    parsed = urlparse(str(url))
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Disallowed scheme: {parsed.scheme}")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Missing hostname")
    hostname = hostname.strip("[]").rstrip(".")

    ip = _normalize_ip_literal(hostname)
    if ip is not None:
        if _is_bad_ip(ip):
            raise ValueError(f"Private IP disallowed: {hostname}")
        return True

    try:
        resolved = _resolve_all(hostname)
    except Exception:
        # Unresolvable host: the connection attempt will fail on its own.
        return True
    for ip_str in resolved:
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            raise ValueError(f"Unparseable resolved address: {ip_str}")
        if _is_bad_ip(addr):
            raise ValueError(f"Private IP disallowed: {hostname}")
    return True


def sanitize_redirect_url(url: str) -> str:
    assert_safe_url(url)
    return url
