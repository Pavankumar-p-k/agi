"""
TEST_MEMORY_001-003 — Conversation memory persistence tests.

RELEASE_BLOCKER if any test fails.

Requires a running server at 127.0.0.1:8000.
"""
import json
import os
import sys
import time
import uuid
from pathlib import Path

import pytest
import requests

WS_URL = "ws://127.0.0.1:8000/ws/agent_stream"
HTTP_URL = "http://127.0.0.1:8000"
SESSION_DIR = Path.home() / ".jarvis" / "sessions"


def _check_server() -> bool:
    try:
        r = requests.get(f"{HTTP_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _connect_ws(session_id: str, origin: str = "http://localhost:3000"):
    """Connect to /ws/agent_stream. Raises if 403 or connection fails."""
    import websockets
    import asyncio

    async def _connect():
        async with websockets.connect(
            WS_URL, close_timeout=5, origin=origin
        ) as ws:
            await ws.send(json.dumps({
                "type": "session_init",
                "session_id": session_id,
                "project_context": {},
            }))
            resp = json.loads(await ws.recv())
            assert resp.get("type") == "workspace_summary", f"Expected workspace_summary, got {resp.get('type')}"
            return ws

    return asyncio.run(_connect())


def _send_chat(ws, text: str, session_id: str, timeout_s: float = 15.0) -> str:
    """Send a chat message over WS and return the full response text."""
    import asyncio
    import websockets

    payload = {"type": "chat", "text": text, "session_id": session_id}

    async def _send_recv():
        await ws.send(json.dumps(payload))
        full_reply = ""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                break
            data = json.loads(raw)
            t = data.get("type", "")
            if t == "stream_token":
                full_reply += data.get("token", "")
                if data.get("complete"):
                    break
            elif t == "stream_end":
                break
            elif t == "error":
                pytest.fail(f"Server error: {data.get('message')}")
            # Ignore classification, tool_start/end, phase_change, etc.
        return full_reply.strip()

    return asyncio.run(_send_recv())


def _send_chat_reconnect(session_id: str, text: str) -> str:
    """Send chat over a new WS connection (simulates reconnect)."""
    import asyncio
    import websockets

    async def _send():
        async with websockets.connect(WS_URL, close_timeout=5, origin="http://localhost:3000") as ws:
            await ws.send(json.dumps({
                "type": "session_init",
                "session_id": session_id,
                "project_context": {},
            }))
            _ = json.loads(await ws.recv())  # workspace_summary

            await ws.send(json.dumps({
                "type": "chat", "text": text, "session_id": session_id,
            }))
            full_reply = ""
            deadline = time.time() + 15
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    break
                data = json.loads(raw)
                t = data.get("type", "")
                if t == "stream_token":
                    full_reply += data.get("token", "")
                    if data.get("complete"):
                        break
                elif t == "stream_end":
                    break
                elif t == "error":
                    pytest.fail(f"Server error: {data.get('message')}")
            return full_reply.strip()

    return asyncio.run(_send())


def _check_conversation_file(session_id: str, min_messages: int = 2) -> dict | None:
    """Check that the session was persisted to disk. Returns parsed data or None."""
    fpath = SESSION_DIR / f"{session_id}.json"
    if not fpath.exists():
        return None
    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)
    msgs = data.get("messages", [])
    if len(msgs) < min_messages:
        return None
    return data


# ── Tests ──

@pytest.fixture(scope="module")
def server_running():
    if not _check_server():
        pytest.skip("Server not running at 127.0.0.1:8000")


def test_memory_001_same_connection(server_running):
    """TEST_MEMORY_001: Same-connection memory.

    "My name is Pavan"
    "What is my name?"
    Expected: Pavan
    """
    session_id = f"memtest_001_{uuid.uuid4().hex[:8]}"
    ws = _connect_ws(session_id)

    resp1 = _send_chat(ws, "My name is Pavan", session_id)
    assert resp1, "Expected non-empty response to 'My name is Pavan'"

    resp2 = _send_chat(ws, "What is my name?", session_id)
    assert resp2, "Expected non-empty response to 'What is my name?'"
    assert "Pavan" in resp2, (
        f"RELEASE_BLOCKER: Same-connection memory failed.\n"
        f"  Q1: 'My name is Pavan' -> '{resp1}'\n"
        f"  Q2: 'What is my name?' -> '{resp2}'\n"
        f"  Expected 'Pavan' in response, got: '{resp2}'"
    )

    ws.close()


def test_memory_002_multi_fact(server_running):
    """TEST_MEMORY_002: Multi-fact memory.

    "I live in Hyderabad"
    "Where do I live?"
    Expected: Hyderabad
    """
    session_id = f"memtest_002_{uuid.uuid4().hex[:8]}"
    ws = _connect_ws(session_id)

    resp1 = _send_chat(ws, "I live in Hyderabad", session_id)
    assert resp1, "Expected non-empty response to 'I live in Hyderabad'"

    resp2 = _send_chat(ws, "Where do I live?", session_id)
    assert resp2, "Expected non-empty response to 'Where do I live?'"
    assert "Hyderabad" in resp2, (
        f"RELEASE_BLOCKER: Multi-fact memory failed.\n"
        f"  Q1: 'I live in Hyderabad' -> '{resp1}'\n"
        f"  Q2: 'Where do I live?' -> '{resp2}'\n"
        f"  Expected 'Hyderabad' in response"
    )

    ws.close()


def test_memory_003_reconnect(server_running):
    """TEST_MEMORY_003: Reconnect memory.

    (new WS connection)
    "What is my name?"
    Expected: Pavan  (from prior session)
    """
    # First, tell our name on one connection
    session_id = f"memtest_003_{uuid.uuid4().hex[:8]}"
    ws1 = _connect_ws(session_id)
    resp1 = _send_chat(ws1, "My name is Pavan", session_id)
    assert resp1, "Expected non-empty response"
    ws1.close()

    # Reconnect with a new WebSocket, same session_id
    resp2 = _send_chat_reconnect(session_id, "What is my name?")
    assert resp2, "Expected non-empty response to 'What is my name?' on reconnect"
    assert "Pavan" in resp2, (
        f"RELEASE_BLOCKER: Reconnect memory failed.\n"
        f"  Connection 1: 'My name is Pavan' -> '{resp1}'\n"
        f"  Connection 2 (reconnect): 'What is my name?' -> '{resp2}'\n"
        f"  Expected 'Pavan' in response"
    )


def test_conversation_file_persisted():
    """Verify that conversation files are actually written to disk."""
    found = False
    for fpath in SESSION_DIR.glob("memtest_*.json"):
        with open(fpath) as f:
            data = json.load(f)
        msgs = data.get("messages", [])
        if len(msgs) >= 2:
            found = True
            break
    assert found, (
        f"RELEASE_BLOCKER: No conversation file found with >=2 messages in {SESSION_DIR}.\n"
        f"  conv.add_message() or conv.save() is NOT being called."
    )
