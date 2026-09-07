# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest


class TestSettingsEndpoints:
    def test_get_all_settings(self, api_client):
        resp = api_client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_single_setting(self, api_client):
        resp = api_client.get("/api/settings/llm.chat_model")
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
            "/api/settings/llm.chat_model",
            json={"value": "test-model"},
        )
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("key") == "llm.chat_model"
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
            json={"llm.chat_model": "bulk-test-model"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "updated" in data

    def test_reset_setting(self, api_client):
        resp = api_client.post("/api/settings/reset/llm.chat_model")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("key") == "llm.chat_model"

    def test_reset_all_settings(self, api_client):
        resp = api_client.post("/api/settings/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
