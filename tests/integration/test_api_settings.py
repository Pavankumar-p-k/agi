import pytest


class TestSettingsEndpoints:
    def test_get_all_settings(self, api_client):
        resp = api_client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_single_setting(self, api_client):
        resp = api_client.get("/api/settings/llm.default_model")
        assert resp.status_code == 200
        data = resp.json()
        assert "key" in data
        assert "value" in data

    def test_get_nonexistent_setting(self, api_client):
        resp = api_client.get("/api/settings/does.not.exist")
        assert resp.status_code == 404

    def test_get_settings_categories(self, api_client):
        resp = api_client.get("/api/settings/meta/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_update_setting(self, api_client):
        resp = api_client.put(
            "/api/settings/llm.default_model",
            json={"value": "test-model"},
        )
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("key") == "llm.default_model"
        elif resp.status_code == 400:
            assert "restart_required" in resp.text.lower() or "invalid" in resp.text.lower()

    def test_update_nonexistent_setting(self, api_client):
        resp = api_client.put(
            "/api/settings/does.not.exist",
            json={"value": "test"},
        )
        assert resp.status_code == 404

    def test_bulk_update_settings(self, api_client):
        resp = api_client.post(
            "/api/settings/bulk",
            json={"llm.default_model": "bulk-test-model"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "updated" in data

    def test_reset_setting(self, api_client):
        resp = api_client.post("/api/settings/reset/llm.default_model")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("key") == "llm.default_model"

    def test_reset_all_settings(self, api_client):
        resp = api_client.post("/api/settings/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
