import pytest

from core.config_schema import ServerConfig
from core.configuration.service import ConfigurationService
from core.settings.schema import ServerSettings


def test_production_defaults_are_not_development_or_wildcard():
    assert ServerConfig().dev_mode is False
    assert ServerSettings().dev_mode is False
    assert "*" not in ServerSettings().cors_origins
    assert "*" not in ServerConfig().allowed_origins


@pytest.mark.parametrize("secret", [None, "", "short", "x" * 31])
def test_production_requires_strong_secret(secret):
    with pytest.raises(ValueError):
        ConfigurationService.validate_security_settings(False, secret)


def test_development_opt_in_allows_missing_secret():
    ConfigurationService.validate_security_settings(True, None)


def test_api_values_redact_secrets_and_paths():
    assert ConfigurationService._safe_api_value("server.secret_key", "secret") == "[redacted]"
    assert ConfigurationService._safe_api_value("build.vault_path", r"C:\private\vault") == "[redacted]"
    assert ConfigurationService._safe_api_value("server.port", 8000) == 8000
