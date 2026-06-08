from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse
from core.plugins.errors import PluginNetworkError

logger = logging.getLogger(__name__)

BLOCKED_HOSTS: set[str] = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "[::1]",
    "metadata.google.internal",
    "169.254.169.254",
}

PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

ALLOWED_SCHEMES = {"http", "https", "ws", "wss"}

DISALLOWED_PORTS = {22, 23, 25, 53, 135, 137, 139, 389, 445, 636, 1433, 1521, 2049, 2375, 2376, 3306, 3389, 5432, 5900, 6379, 8080, 8443, 27017}


def _resolve_host(hostname: str) -> str | None:
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        return None


def is_private_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in PRIVATE_RANGES)
    except ValueError:
        return False


def is_blocked_hostname(hostname: str) -> bool:
    normalized = hostname.strip().lower()
    if normalized in BLOCKED_HOSTS:
        return True
    for blocked in BLOCKED_HOSTS:
        if normalized.endswith("." + blocked):
            return True
    ip = _resolve_host(normalized)
    if ip and is_private_ip(ip):
        return True
    return False


def is_blocked_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
    except Exception as e:
        return True, f"Invalid URL: {e}"

    if parsed.scheme not in ALLOWED_SCHEMES:
        return True, f"Disallowed scheme: {parsed.scheme}"

    hostname = parsed.hostname or ""
    if is_blocked_hostname(hostname):
        return True, f"Blocked host: {hostname}"

    if parsed.port and parsed.port in DISALLOWED_PORTS:
        return True, f"Disallowed port: {parsed.port}"

    ip = _resolve_host(hostname)
    if ip and is_private_ip(ip):
        return True, f"Private IP: {ip}"

    return False, ""


def assert_safe_url(url: str) -> None:
    blocked, reason = is_blocked_url(url)
    if blocked:
        from core.plugins.errors import PluginNetworkError

        raise PluginNetworkError(url, reason)


def safe_httpx_client(**kwargs: Any) -> Any:
    import httpx

    class SsrfTransport(httpx.BaseTransport):
        def __init__(self, inner=None):
            self._inner = inner or httpx.HTTPTransport()

        def handle_request(self, request):
            blocked, reason = is_blocked_url(str(request.url))
            if blocked:
                raise PluginNetworkError(str(request.url), reason)
            return self._inner.handle_request(request)

        def handle_async_request(self, request):
            blocked, reason = is_blocked_url(str(request.url))
            if blocked:
                raise PluginNetworkError(str(request.url), reason)
            return self._inner.handle_async_request(request)

        def close(self):
            self._inner.close()

    return httpx.Client(transport=SsrfTransport(), **kwargs)


class SsrfProtection:
    def __init__(self, enabled: bool = True, allow_private: bool = False, allow_ports: set[int] | None = None):
        self.enabled = enabled
        self.allow_private = allow_private
        self.allow_ports = allow_ports or set()

    def check(self, url: str) -> tuple[bool, str]:
        if not self.enabled:
            return True, ""
        return is_blocked_url(url)

    def wrap_client(self, **kwargs: Any) -> Any:
        return safe_httpx_client(**kwargs)
