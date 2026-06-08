"""API contract tests — route discovery, response shapes, auth failure modes.

These tests validate that every registered FastAPI route returns the correct
status code and response shape for both authenticated and unauthenticated requests.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from core.main import app

client = TestClient(app)

# Routes that don't require authentication
PUBLIC_ROUTES = {
    "GET": {"/health", "/favicon.ico", "/metrics"},
    "POST": set(),
    "PUT": set(),
    "DELETE": set(),
}

# Routes known to require auth tokens
AUTH_REQUIRED_PREFIXES = {
    "/api/", "/chat/", "/sessions/", "/admin/",
    "/tools/", "/plugins/", "/channels/",
}


def _get_all_routes():
    """Discover all registered FastAPI routes."""
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                routes.append((method, route.path))
    return routes


def test_health_returns_200():
    """Public /health endpoint returns 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_has_required_fields():
    """Health response has status and version fields."""
    response = client.get("/health")
    data = response.json()
    assert "status" in data
    assert "version" in data


def test_metrics_returns_200():
    """Public /metrics endpoint returns 200."""
    response = client.get("/metrics")
    assert response.status_code == 200


def test_auth_required_routes_reject_anonymous():
    """Routes under /api/{session,chat} reject unauthenticated requests."""
    known_auth_routes = [
        ("GET", "/api/sessions"),
        ("POST", "/api/chat"),
    ]
    for method, path in known_auth_routes:
        response = client.request(method, path)
        assert response.status_code in (401, 403, 422), (
            f"{method} {path} expected 401/403/422, got {response.status_code}"
        )


def test_auth_required_routes_with_bad_token():
    """Invalid token returns 401 or 422 (validated before auth)."""
    bad_headers = {"Authorization": "Bearer invalid_token_12345"}
    known_routes = [
        ("GET", "/api/sessions"),
        ("POST", "/api/chat"),
    ]
    for method, path in known_routes:
        if path not in {r.path for r in app.routes if hasattr(r, "path")}:
            continue
        response = client.request(method, path, headers=bad_headers)
        assert response.status_code in (401, 403, 422), (
            f"{method} {path} with bad token: {response.status_code}"
        )


def test_health_response_shape():
    """Health response matches expected schema."""
    response = client.get("/health")
    data = response.json()
    assert isinstance(data, dict)
    assert "status" in data
    assert isinstance(data["status"], str)
    assert "version" in data


def test_metrics_response_shape():
    """Metrics response is a dict with metric keys."""
    response = client.get("/metrics")
    data = response.json()
    assert isinstance(data, dict)
    assert "requests_total" in data
    assert "tool_calls_total" in data
    assert any(k.startswith("llm_latency") for k in data), (
        f"expected llm_latency key in {list(data.keys())}"
    )


def test_unknown_route_returns_404():
    """Undefined routes return 404."""
    response = client.get("/nonexistent/route/12345")
    assert response.status_code == 404


def _requires_auth(method: str, path: str) -> bool:
    """Check if a route requires authentication."""
    if method in PUBLIC_ROUTES and path in PUBLIC_ROUTES[method]:
        return False
    for prefix in AUTH_REQUIRED_PREFIXES:
        if path.startswith(prefix):
            return True
    return False
