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
