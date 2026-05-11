"""Quick targeted audit - no recursion, just critical checks"""
import sys
import time
import subprocess
import requests
import sqlite3
import os

print("=== OLLAMA CHECK ===")
try:
    import json
    from urllib.request import urlopen
    with urlopen("http://localhost:11434/api/tags", timeout=5) as resp:
        data = json.loads(resp.read())
        print(f"OLLAMA: {len(data.get('models', []))} models installed")
except Exception as e:
    print(f"OLLAMA: FAILED - {e}")

print("\n=== SERVER START ===")
proc = subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'core.main:app', '--host', '127.0.0.1', '--port', '8001'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)
time.sleep(8)
print("(Server started in background, checking endpoints...)")

print("\n=== ENDPOINT CHECKS ===")
endpoints = [
    "http://127.0.0.1:8001/",
    "http://127.0.0.1:8001/health",
]
for url in endpoints:
    try:
        resp = requests.get(url, timeout=5)
        print(f"  GET {url} => {resp.status_code} | {resp.text[:150]}")
    except Exception as e:
        print(f"  GET {url} => ERROR: {e}")

print("\n=== DATABASE CHECK ===")
for db in ['data/jarvis.db', 'data/jarvis_memory.db']:
    if os.path.exists(db):
        try:
            conn = sqlite3.connect(db)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            print(f"  {db}: {len(tables)} tables")
            for t in tables:
                cur.execute(f"SELECT count(*) FROM [{t}]")
                print(f"    {t}: {cur.fetchone()[0]} rows")
            conn.close()
        except Exception as e:
            print(f"  {db}: ERROR {e}")
    else:
        print(f"  {db}: NOT FOUND")

print("\n=== COMPONENT IMPORTS ===")
tests = [
    ("from assistant.stt import JarvisSTT", "JarvisSTT"),
    ("from assistant.tts import JarvisTTS", "JarvisTTS"),
    ("from tools.search_tool import SearXNGSearch", "SearXNGSearch"),
    ("from memory.embedding_memory import EmbeddingMemory", "EmbeddingMemory"),
    ("from core.model_router import resolve_model", "resolve_model"),
    ("from pc_agent.computer_agent import ComputerAgent", "ComputerAgent"),
    ("from core.privacy_classifier import PrivacyClassifier", "PrivacyClassifier"),
    ("from brain.UnifiedBrain import UnifiedBrain", "UnifiedBrain"),
    ("from assistant.wake_word import WakeWordDetector", "WakeWordDetector"),
    ("from browser_use import Agent", "browser_use.Agent"),
]
for code, name in tests:
    try:
        exec(code)
        print(f"  {name} => OK")
    except Exception as e:
        err = str(e).split('\n')[0]
        print(f"  {name} => FAILED: {err[:100]}")

proc.terminate()
print("\n=== DONE ===")