"""SSRF protection and URL validation utilities."""
from __future__ import annotations
import ipaddress
import socket
from urllib.parse import urlparse


def _check_ip_literal(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return not (ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local)
    except ValueError:
        return False


def is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local
    except ValueError:
        return True


def resolve_and_check(hostname: str) -> bool:
    try:
        addrinfo = socket.getaddrinfo(hostname, None)
        for item in addrinfo:
            ip_str = item[4][0]
            if is_private_ip(ip_str):
                return False
        return True
    except Exception:
        return False


def assert_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Disallowed scheme: {parsed.scheme}")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Missing hostname")
    if is_private_ip(hostname):
        raise ValueError(f"Private IP disallowed: {hostname}")
    return True


def sanitize_redirect_url(url: str) -> str:
    assert_safe_url(url)
    return url
