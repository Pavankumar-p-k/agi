# find_broken_wire.py
# Drop this in C:\Users\peter\Desktop\jarvis\
# Run: python find_broken_wire.py

import httpx
import json
import re
import webbrowser
import os
import urllib.parse
import time

print("=" * 60)
print("BROKEN WIRE DIAGNOSTIC")
print("=" * 60)

# TEST 1: Intent extraction
print("\n[TEST 1] Intent extraction from Ollama...")
INTENT_PROMPT = (
    "You are an intent parser. Return ONLY raw JSON. No text.\n"
    "Format: {\"intent\": \"chat|open_url|play_media|open_app\", \"target\": \"what\"}\n"
    "play cry for me on yt -> {\"intent\":\"play_media\",\"target\":\"cry for me\"}\n"
    "opn yt -> {\"intent\":\"open_url\",\"target\":\"youtube\"}\n"
    "what is python -> {\"intent\":\"chat\",\"target\":\"python\"}\n"
)
try:
    r = httpx.post(
        "http://localhost:11434/api/chat",
        json={
            "model": "qwen3:4b",
            "messages": [
                {"role": "system", "content": INTENT_PROMPT},
                {"role": "user", "content": "play cry for me on yt"}
            ],
            "stream": False,
            "options": {"temperature": 0, "num_predict": 50}
        },
        timeout=30
    )
    raw = r.json()["message"]["content"]
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    intent_data = json.loads(raw)
    print("[PASS] Intent: " + str(intent_data))
except Exception as e:
    print("[FAIL] " + str(e))
    intent_data = None

# TEST 2: webbrowser works?
print("\n[TEST 2] webbrowser.open() test...")
print("Opening youtube in 2 seconds - watch your screen...")
time.sleep(2)
result = webbrowser.open("https://youtube.com")
print("[RESULT] webbrowser.open returned: " + str(result))
print("Did browser open? YES=works, NO=webbrowser broken")

# TEST 3: Does action_executor exist?
print("\n[TEST 3] Searching for action executor...")
search_paths = [
    "core/action_executor.py",
    "tools/action_executor.py",
    "tools/executor.py",
    "core/actions.py",
]
found = None
for p in search_paths:
    if os.path.exists(p):
        print("[FOUND] " + p)
        found = p
        break
if not found:
    print("[NOT FOUND] Checking whole project...")
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", "node_modules"]]
        for f in files:
            if "action" in f.lower() and f.endswith(".py"):
                print("  -> " + os.path.join(root, f))

# TEST 4: Check core/main.py
print("\n[TEST 4] Checking core/main.py for wiring...")
if os.path.exists("core/main.py"):
    with open("core/main.py", "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    checks = {
        "extract_intent exists": "extract_intent" in content,
        "execute_action exists": "execute_action" in content,
        "webbrowser imported": "webbrowser" in content,
        "action_executor imported": "action_executor" in content,
        "intent != chat check": ("intent" in content and "!= \"chat\"" in content) or ("intent !=" in content),
    }
    for name, result in checks.items():
        print(("[YES] " if result else "[NO]  ") + name)

    # Show the chat handler
    print("\n--- /api/chat handler (first 30 lines) ---")
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if ("/api/chat" in line or "async def chat" in line) and "def " in lines[min(i+1, len(lines)-1)] or "api/chat" in line:
            for j in range(i, min(i+30, len(lines))):
                print(str(j+1).rjust(4) + " | " + lines[j])
            break
else:
    print("[FAIL] core/main.py not found")

# TEST 5: Manual action bypass
print("\n[TEST 5] Manual action - bypassing all of JARVIS...")
song = "cry for me"
url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(song)
print("Opening YouTube for: " + song)
webbrowser.open(url)
print("[DONE] If YouTube search opened = execution works, wiring is broken")

print("\n" + "=" * 60)
print("PASTE THIS OUTPUT AND WE FIX THE EXACT LINE")
print("=" * 60)
