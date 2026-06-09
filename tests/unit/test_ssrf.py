import unittest.mock
import pytest
from core.ssrf import is_private_ip, resolve_and_check, assert_safe_url


class TestIsPrivateIp:
    def test_loopback(self):
        assert is_private_ip("127.0.0.1") is True
        assert is_private_ip("127.255.255.255") is True
        assert is_private_ip("0.0.0.0") is True

    def test_private_10(self):
        assert is_private_ip("10.0.0.1") is True
        assert is_private_ip("10.255.255.255") is True

    def test_private_172(self):
        assert is_private_ip("172.16.0.1") is True
        assert is_private_ip("172.31.255.255") is True

    def test_private_192(self):
        assert is_private_ip("192.168.0.1") is True
        assert is_private_ip("192.168.255.255") is True

    def test_link_local(self):
        assert is_private_ip("169.254.1.1") is True

    def test_ipv6_loopback(self):
        assert is_private_ip("::1") is True

    def test_public_ip(self):
        assert is_private_ip("8.8.8.8") is False
        assert is_private_ip("93.184.216.34") is False
        assert is_private_ip("1.1.1.1") is False

    def test_invalid_input(self):
        assert is_private_ip("not-an-ip") is False
        assert is_private_ip("") is False


class TestResolveAndCheck:
    def test_https_public_domain(self):
        assert resolve_and_check("https://example.com") is True

    def test_http_public_domain(self):
        assert resolve_and_check("http://example.com") is True

    def test_blocked_scheme(self):
        assert resolve_and_check("ftp://example.com") is False
        assert resolve_and_check("file:///etc/passwd") is False
        assert resolve_and_check("gopher://localhost") is False

    def test_localhost_hostname(self):
        assert resolve_and_check("http://localhost:11434") is False
        assert resolve_and_check("http://localhost.localdomain:8080") is False
        assert resolve_and_check("http://0.0.0.0:8000") is False
        assert resolve_and_check("http://0:8000") is False

    def test_private_ip_in_url(self):
        assert resolve_and_check("http://127.0.0.1:8000") is False
        assert resolve_and_check("http://10.0.0.1") is False
        assert resolve_and_check("http://192.168.1.1") is False
        assert resolve_and_check("http://0.0.0.0:80") is False

    def test_dns_resolution_failure(self):
        assert resolve_and_check("http://this-domain-definitely-does-not-exist-12345.com") is False


class TestAssertSafeUrl:
    def test_public_url(self):
        import httpx
        with unittest.mock.patch.object(httpx, "Client") as mock_client:
            mock_instance = mock_client.return_value.__enter__.return_value
            mock_response = unittest.mock.MagicMock()
            mock_response.url = "https://example.com"
            mock_instance.get.return_value = mock_response
            assert_safe_url("https://example.com")

    def test_private_url_raises(self):
        with pytest.raises(ValueError, match="SSRF blocked"):
            assert_safe_url("http://127.0.0.1:8000")

    def test_localhost_raises(self):
        with pytest.raises(ValueError, match="SSRF blocked"):
            assert_safe_url("http://localhost:11434")

    def test_bad_scheme_raises(self):
        with pytest.raises(ValueError, match="SSRF blocked"):
            assert_safe_url("file:///etc/passwd")

    def test_empty_url(self):
        with pytest.raises(ValueError, match="SSRF blocked"):
            assert_safe_url("")
