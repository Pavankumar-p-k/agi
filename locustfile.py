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
