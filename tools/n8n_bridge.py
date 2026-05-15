"""tools/n8n_bridge.py — JARVIS-n8n workflow automation bridge.

Triggers n8n workflows via webhooks and REST API.
n8n must be running in Docker or separately.

Workflows are defined and managed in the n8n UI at http://localhost:5678.
Once a workflow has a Webhook trigger, it gets a URL like:
    http://localhost:5678/webhook/<workflow-id>

Usage:
    import tools.n8n_bridge as n8n
    n8n.trigger_webhook("research-news", {"query": "AI"})
    n8n.list_workflows()
"""
import os
import json
import requests
from typing import Optional, List, Dict

N8N_URL = os.getenv("N8N_URL", "http://localhost:5678")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")

_WEBHOOK_REGISTRY: Dict[str, str] = {}


def register_workflow(name: str, webhook_path: str):
    """Register an n8n workflow so JARVIS can trigger it by name.

    Args:
        name: Short name JARVIS uses (e.g. "research-news", "send-daily-summary")
        webhook_path: Path after /webhook/ (e.g. "research-news" or "abc123")
    """
    _WEBHOOK_REGISTRY[name] = webhook_path


def get_webhook_url(name: str) -> Optional[str]:
    path = _WEBHOOK_REGISTRY.get(name)
    if path:
        return f"{N8N_URL}/webhook/{path}"
    return None


def trigger_webhook(workflow_name: str, payload: dict = None) -> dict:
    """Trigger an n8n workflow by its registered name.

    Uses GET with query params (n8n webhook nodes accept GET by default).
    For POST payloads, set httpMethod in the n8n workflow node settings.

    Returns:
        dict with keys: success, data, error
    """
    url = get_webhook_url(workflow_name)
    if not url:
        return {"success": False, "error": f"Workflow '{workflow_name}' not registered"}
    try:
        headers = {}
        if N8N_API_KEY:
            headers["X-N8N-API-KEY"] = N8N_API_KEY
        resp = requests.get(url, params=payload or {}, headers=headers, timeout=60)
        resp.raise_for_status()
        return {"success": True, "data": resp.json() if resp.text else {}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_workflows() -> List[dict]:
    """List all workflows from n8n API.

    Requires N8N_API_KEY to be set.
    """
    if not N8N_API_KEY:
        return []
    try:
        headers = {"X-N8N-API-KEY": N8N_API_KEY}
        resp = requests.get(f"{N8N_URL}/rest/workflows", headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return [
            {"id": w["id"], "name": w["name"], "active": w.get("active", False)}
            for w in data.get("data", [])
        ]
    except Exception as e:
        print(f"[n8n] List workflows error: {e}")
        return []


def is_running() -> bool:
    """Check if n8n service is reachable."""
    try:
        resp = requests.get(f"{N8N_URL}/healthz", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False



# Register default workflows (users can add more in n8n UI)
register_workflow("research-news", "research-news")
register_workflow("send-daily-summary", "send-daily-summary")
register_workflow("scrape-and-summarize", "scrape-and-summarize")
