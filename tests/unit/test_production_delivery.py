from scripts.validate_production import validate_environment
from scripts.smoke_test import check


class _Response:
    status = 200

    def read(self):
        return b'{"status":"healthy"}'

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_production_environment_requires_secure_values():
    errors = validate_environment({
        "JARVIS_ENV": "production",
        "JARVIS_SECRET_KEY": "x" * 32,
        "HOST": "0.0.0.0",
        "ALLOWED_ORIGINS": "https://example.test",
        "JARVIS_DB__URL": "sqlite+aiosqlite:////app/data/app.db",
    })
    assert errors == []


def test_production_environment_rejects_placeholders_and_wildcard_origin():
    errors = validate_environment({
        "JARVIS_ENV": "production",
        "JARVIS_SECRET_KEY": "change-me",
        "ALLOWED_ORIGINS": "*",
    })
    assert any("SECRET_KEY" in error for error in errors)
    assert any("ALLOWED_ORIGINS" in error for error in errors)
    assert any("DB__URL" in error for error in errors)


def test_smoke_check_accepts_existing_health_contract(monkeypatch):
    monkeypatch.setattr(
        "scripts.smoke_test.urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response(),
    )
    check("http://localhost:8000/health", 1)
