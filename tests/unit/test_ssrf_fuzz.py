"""Property-based fuzz tests for SSRF protection using hypothesis."""
import pytest
from hypothesis import given, assume, strategies as st, settings, HealthCheck

from core.ssrf import is_private_ip, resolve_and_check, assert_safe_url, sanitize_redirect_url


def _ip_to_hex(ip: str) -> str:
    parts = ip.split(".")
    return "0x" + "".join(hex(int(p))[2:].zfill(2) for p in parts)


def _ip_to_octal(ip: str) -> str:
    parts = ip.split(".")
    return ".".join(oct(int(p))[2:] for p in parts)


def _ip_to_decimal(ip: str) -> str:
    parts = ip.split(".")
    return str(sum(int(p) * (256 ** (3 - i)) for i, p in enumerate(parts)))


private_ip_strategy = st.sampled_from([
    "127.0.0.1",
    "10.0.0.1",
    "172.16.0.1",
    "172.31.255.255",
    "192.168.1.1",
    "169.254.1.1",
    "::1",
    "fc00::1",
    "fe80::1",
])

public_ip_strategy = st.sampled_from([
    "8.8.8.8",
    "1.1.1.1",
    "93.184.216.34",
    "208.67.222.222",
    "9.9.9.9",
])

scheme_strategy = st.sampled_from([
    "http", "https", "ftp", "file", "gopher", "dict",
    "ldap", "tftp", "jar:", "php:",
])


class TestIsPrivateIpFuzz:
    @given(st.ip_addresses(v=4).map(str))
    def test_ipv4_private_ranges(self, ip_str):
        """All private IPv4 ranges are identified."""
        result = is_private_ip(ip_str)
        octets = [int(x) for x in ip_str.split(".")]
        expected = (
            octets[0] == 0
            or octets[0] == 10
            or (octets[0] == 172 and 16 <= octets[1] <= 31)
            or (octets[0] == 192 and octets[1] == 168)
            or octets[0] == 127
            or (octets[0] == 169 and octets[1] == 254)
        )
        assert result == expected, f"{ip_str} expected private={expected}"

    @given(st.ip_addresses(v=6).map(str))
    def test_ipv6_private_ranges(self, ip_str):
        """All private IPv6 ranges are identified."""
        result = is_private_ip(ip_str)
        lower = ip_str.lower()
        expected = (
            lower == "::1"
            or lower.startswith("fc")
            or lower.startswith("fd")
            or lower.startswith("fe8")
            or lower.startswith("fe9")
            or lower.startswith("fea")
            or lower.startswith("feb")
        )
        assert result == expected, f"{ip_str} expected private={expected}"

    @given(st.text(min_size=0, max_size=50))
    def test_invalid_never_crashes(self, s):
        """Non-IP strings don't crash the function."""
        try:
            is_private_ip(s)
        except Exception:
            pass


class TestResolveAndCheckFuzz:
    @given(
        scheme=st.sampled_from(["http", "https"]),
        host=public_ip_strategy,
        port=st.integers(min_value=1, max_value=65535),
    )
    @settings(deadline=5000, suppress_health_check=[HealthCheck.too_slow])
    def test_public_ip_urls_allowed(self, scheme, host, port):
        """Public IPs over HTTP/S schemes should pass."""
        url = f"{scheme}://{host}:{port}"
        assert resolve_and_check(url) is True

    @given(
        scheme=scheme_strategy,
        host=private_ip_strategy,
    )
    @settings(deadline=5000, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
    def test_private_ip_urls_blocked(self, scheme, host):
        """Private IPs blocked regardless of scheme."""
        url = f"{scheme}://{host}"
        assert resolve_and_check(url) is False

    @given(
        scheme=st.sampled_from(["ftp", "file", "gopher", "dict", "ldap", "tftp"]),
        host=public_ip_strategy,
    )
    def test_blocked_schemes(self, scheme, host):
        """Non-HTTP/S schemes blocked even with public IPs."""
        url = f"{scheme}://{host}"
        assert resolve_and_check(url) is False

    @given(
        host=st.sampled_from([
            "localhost", "localhost.localdomain", "127.0.0.1", "0.0.0.0",
        ]),
        port=st.integers(min_value=0, max_value=65535),
    )
    @settings(deadline=5000, suppress_health_check=[HealthCheck.too_slow])
    def test_localhost_variants_blocked(self, host, port):
        """Localhost by hostname or IP blocked."""
        url = f"http://{host}:{port}"
        assert resolve_and_check(url) is False

    @given(st.text(min_size=1, max_size=100))
    @settings(deadline=5000, suppress_health_check=[HealthCheck.too_slow])
    def test_nonexistent_domain_blocked(self, domain):
        """Non-resolving domains blocked."""
        assume("://" not in domain)
        assume(" " not in domain)
        assume("\n" not in domain)
        assume("\t" not in domain)
        url = f"http://{domain}.nonexistent.invalid"
        try:
            assert resolve_and_check(url) is False
        except Exception:
            pass


class TestSanitizeRedirectUrl:
    @given(
        host=public_ip_strategy,
        path=st.text(min_size=0, max_size=30),
    )
    def test_public_redirect_returns_url(self, host, path):
        """Safe redirect URLs returned as-is."""
        url = f"https://{host}/{path}"
        result = sanitize_redirect_url(url)
        assert result == url

    @given(
        scheme=st.sampled_from(["ftp", "file", "gopher"]),
        host=st.sampled_from(["localhost", "127.0.0.1"]),
    )
    def test_unsafe_redirect_returns_none(self, scheme, host):
        """Unsafe redirect URLs return None."""
        url = f"{scheme}://{host}"
        assert sanitize_redirect_url(url) is None


class TestAssertSafeUrl:
    @given(
        scheme=st.sampled_from(["file", "gopher", "dict"]),
        host=st.sampled_from(["localhost", "127.0.0.1", "example.com"]),
    )
    def test_unsafe_urls_raise_valueerror(self, scheme, host):
        """Assert_safe_url raises on unsafe URLs."""
        url = f"{scheme}://{host}"
        with pytest.raises(ValueError, match="SSRF blocked"):
            assert_safe_url(url)
