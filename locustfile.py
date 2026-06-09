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

"""Load testing with locust.

Usage:
    pip install locust
    locust -f locustfile.py --host http://localhost:8000
    # Open http://localhost:8089 in browser

SLOs (p95):
  - Tool execution: < 2s
  - LLM completion: < 30s
  - API routes: < 5s
"""

from locust import HttpUser, task, between


class JarvisHealthUser(HttpUser):
    """Lightweight user that hits health and metrics endpoints."""

    wait_time = between(1, 3)

    @task(5)
    def health(self):
        self.client.get("/health", name="/health")

    @task(3)
    def metrics(self):
        self.client.get("/metrics", name="/metrics")


class JarvisApiUser(HttpUser):
    """Simulates a real user making API requests."""

    wait_time = between(2, 5)

    def on_start(self):
        self.token = "test_token"

    @task(3)
    def list_sessions(self):
        self.client.get(
            "/api/sessions",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/api/sessions",
        )

    @task(2)
    def list_tools(self):
        self.client.get(
            "/api/tools",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/api/tools",
        )

    @task(1)
    def list_plugins(self):
        self.client.get(
            "/api/plugins",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/api/plugins",
        )
