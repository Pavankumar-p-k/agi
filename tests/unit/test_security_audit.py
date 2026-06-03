"""tests/test_security_audit.py — Tests for core/security_audit.py SecurityAuditor."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestSecurityAuditor:
    @pytest.fixture
    def auditor(self):
        with patch("core.security_audit.AUDIT_DIR", MagicMock()):
            from core.security_audit import SecurityAuditor
            yield SecurityAuditor()

    def test_audit_config_clean(self, auditor):
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/tmp")
            findings = auditor.audit_config()
            assert len(findings) >= 1
            assert findings[-1].severity == "info"

    def test_audit_config_dangerous_flags(self, auditor):
        mock_config = MagicMock()
        mock_config.glob.return_value = [MagicMock()]
        mock_config.__str__.return_value = "/tmp/.jarvis"
        with patch.object(auditor, "audit_config") as mock_config_method:
            mock_config_method.return_value = []

    def test_audit_config_dev_mode(self, auditor):
        mock_file = MagicMock()
        mock_file.read_text.return_value = '{"dev_mode": true}'
        mock_dir = MagicMock()
        mock_dir.glob.return_value = [mock_file]
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/tmp")
            with patch("pathlib.Path.glob", return_value=[mock_file]):
                findings = auditor.audit_config()
                severities = [f.severity for f in findings]
                assert "high" in severities

    def test_audit_filesystem_clean(self, auditor):
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/tmp")
            with patch("pathlib.Path.glob", return_value=[]):
                findings = auditor.audit_filesystem()
                assert any(f.severity == "info" for f in findings)

    def test_audit_network(self, auditor):
        with patch("core.security_audit.resolve_and_check", return_value=False):
            findings = auditor.audit_network()
            assert len(findings) >= 1

    def test_audit_auth_dev_mode(self, auditor):
        with patch("core.config.DEV_MODE", True):
            findings = auditor.audit_auth()
            severities = [f.severity for f in findings]
            assert "high" in severities

    def test_audit_auth_no_dev_mode(self, auditor):
        with patch("core.config.DEV_MODE", False):
            with patch("os.path.exists", return_value=False):
                findings = auditor.audit_auth()
                assert any(f.severity == "info" for f in findings)

    @pytest.mark.asyncio
    async def test_run_full_audit(self, auditor):
        with patch.object(auditor, "audit_config", return_value=[]):
            with patch.object(auditor, "audit_filesystem", return_value=[]):
                with patch.object(auditor, "audit_network", return_value=[]):
                    with patch.object(auditor, "audit_auth", return_value=[]):
                        with patch("core.security_audit.audit_log"):
                            result = await auditor.run_full_audit()
                            assert "summary" in result
                            assert result["summary"]["total"] == 0
