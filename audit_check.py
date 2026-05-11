import sys
import time
import subprocess
import requests

print("=== CHECK 1: Project Structure ===")
print("Core Python files found in jarvis root (non-data dirs):")
import os
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if 'data' not in d.lower() and 'tmp' not in d.lower() and '.git' not in d]
    for f in files:
        if f.endswith('.py') and not f.startswith('.'):
            path = os.path.join(root, f)
            try:
                lines = len(open(path, encoding='utf-8', errors='ignore').readlines())
                print(f"  {path}: {lines} lines")
            except:
                pass

print("\n=== CHECK 2: Server Start ===")
proc = subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'core.main:app', '--host', '127.0.0.1', '--port', '8000'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
)
time.sleep(6)
output_lines = []
for line in proc.stdout:
    output_lines.append(line)
    if len(output_lines) > 100:
        break
print("Server output (first 100 lines):")
for l in output_lines:
    print(f"  {l.rstrip()}")

time.sleep(2)

print("\n=== CHECK 3: Ollama Connectivity ===")
try:
    import json
    from urllib.request import urlopen
    with urlopen("http://localhost:11434/api/tags", timeout=5) as resp:
        data = json.loads(resp.read())
        print(f"Ollama API response: {len(data.get('models', []))} models available")
        for m in data['models'][:3]:
            print(f"  - {m['name']} ({m.get('size', 'N/A')})")
except Exception as e:
    print(f"Ollama API FAILED: {e}")

print("\n=== CHECK 4: API Endpoints ===")
endpoints_to_test = [
    ("GET", "http://127.0.0.1:8000/"),
    ("GET", "http://127.0.0.1:8000/health"),
    ("GET", "http://127.0.0.1:8000/docs"),
]
for method, url in endpoints_to_test:
    try:
        if method == "GET":
            resp = requests.get(url, timeout=5)
            print(f"  {method} {url} => {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  {method} {url} => ERROR: {e}")

print("\n=== CHECK 5: Database ===")
import sqlite3
for db_path in ['data/jarvis.db', 'data/jarvis_memory.db', 'ai_os_memory.db']:
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            print(f"  {db_path}: {len(tables)} tables")
            for t in tables[:5]:
                cur.execute(f"SELECT count(*) FROM [{t}]")
                count = cur.fetchone()[0]
                print(f"    {t}: {count} rows")
            conn.close()
        except Exception as e:
            print(f"  {db_path}: ERROR {e}")

print("\n=== CHECK 6: Component Imports ===")
imports_to_test = [
    ("assistant.stt", "JarvisSTT", "from assistant.stt import JarvisSTT"),
    ("assistant.tts", "JarvisTTS", "from assistant.tts import JarvisTTS"),
    ("assistant.wake_word", "WakeWordDetector", "from assistant.wake_word import WakeWordDetector"),
    ("tools.search_tool", "SearXNGSearch", "from tools.search_tool import SearXNGSearch"),
    ("memory.embedding_memory", "EmbeddingMemory", "from memory.embedding_memory import EmbeddingMemory"),
    ("core.model_router", "resolve_model", "from core.model_router import resolve_model"),
    ("pc_agent.computer_agent", "ComputerAgent", "from pc_agent.computer_agent import ComputerAgent"),
    ("core.privacy_classifier", "PrivacyClassifier", "from core.privacy_classifier import PrivacyClassifier"),
    ("brain.UnifiedBrain", "UnifiedBrain", "from brain.UnifiedBrain import UnifiedBrain"),
]
for module, cls, import_stmt in imports_to_test:
    try:
        exec(import_stmt)
        print(f"  {module}.{cls} => IMPORT OK")
    except ImportError as e:
        print(f"  {module}.{cls} => IMPORT FAILED: {e}")
    except Exception as e:
        print(f"  {module}.{cls} => ERROR: {e}")

proc.terminate()
proc.wait()
print("\n=== DONE ===")