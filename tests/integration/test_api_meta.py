import pytest


class TestDocsEndpoints:
    def test_openapi_json(self, api_client):
        resp = api_client.get("/openapi.json")
        assert resp.status_code == 200

    def test_docs_page(self, api_client):
        resp = api_client.get("/docs")
        assert resp.status_code in (200, 307)


class TestModelEndpoints:
    def test_models_groups(self, api_client):
        resp = api_client.get("/api/models/groups")
        assert resp.status_code == 200
        data = resp.json()
        assert "groups" in data

    def test_models_list(self, api_client):
        resp = api_client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data or "ollama_url" in data
