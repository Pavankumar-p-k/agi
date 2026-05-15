# fix_thinking_model.py
# Run: python fix_thinking_model.py
# Fixes qwen3:4b thinking model returning empty intent

import httpx
import json
import re

print("=" * 60)
print("DIAGNOSING qwen3:4b thinking model output")
print("=" * 60)

# First - see the RAW raw output before ANY stripping
r = httpx.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "qwen3:4b",
        "messages": [
            {"role": "system", "content": "Return ONLY this JSON, nothing else: {\"intent\":\"play_media\",\"target\":\"cry for me\"}"},
            {"role": "user", "content": "play cry for me on yt"}
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 100
        }
    },
    timeout=60
)

raw = r.json()["message"]["content"]
print("COMPLETELY RAW (first 500 chars):")
print(repr(raw[:500]))
print()

# Check if it's all inside think tags
has_think = "<think>" in raw
has_content_after = bool(re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip())

print("Has <think> tags: " + str(has_think))
print("Has content after think: " + str(has_content_after))

if has_think and not has_content_after:
    print()
    print("CONFIRMED: qwen3:4b is putting answer INSIDE <think> block")
    print("This is the thinking model behavior - need /no_think flag or different model")

print()
print("=" * 60)
print("TESTING FIX 1: Use /no_think suffix in prompt")
print("=" * 60)

r2 = httpx.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "qwen3:4b",
        "messages": [
            {"role": "system", "content": "Return ONLY raw JSON. No thinking. /no_think"},
            {"role": "user", "content": "play cry for me on yt /no_think"}
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 60,
            "stop": ["\n\n", "</s>"]
        }
    },
    timeout=60
)
raw2 = r2.json()["message"]["content"]
print("RAW with /no_think: " + repr(raw2[:300]))

print()
print("=" * 60)
print("TESTING FIX 2: Use tinyllama for intent (fast, no thinking)")
print("=" * 60)

INTENT_PROMPT = (
    "You are an intent classifier. Return ONLY JSON.\n"
    "{\"intent\": \"play_media or open_url or open_app or web_search or chat or reminder\", \"target\": \"what\"}\n"
    "Examples:\n"
    "play cry for me on yt => {\"intent\":\"play_media\",\"target\":\"cry for me\"}\n"
    "opn yt => {\"intent\":\"open_url\",\"target\":\"youtube\"}\n"
    "open notepad => {\"intent\":\"open_app\",\"target\":\"notepad\"}\n"
    "search latest news => {\"intent\":\"web_search\",\"target\":\"latest news\"}\n"
    "what is python => {\"intent\":\"chat\",\"target\":\"python\"}\n"
)

r3 = httpx.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "tinyllama",
        "messages": [
            {"role": "system", "content": INTENT_PROMPT},
            {"role": "user", "content": "play cry for me on yt"}
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 60
        }
    },
    timeout=30
)
raw3 = r3.json()["message"]["content"].strip()
raw3_clean = re.sub(r"```json|```", "", raw3).strip()
print("tinyllama RAW: " + repr(raw3_clean[:300]))
try:
    parsed3 = json.loads(raw3_clean)
    print("tinyllama INTENT: " + str(parsed3.get("intent")))
    print("tinyllama TARGET: " + str(parsed3.get("target")))
    print()
    print("SUCCESS: tinyllama works for intent extraction!")
    print("It is fast (2-3s), no thinking, returns clean JSON")
except Exception as e:
    print("tinyllama parse failed: " + str(e))

print()
print("=" * 60)
print("APPLYING FIX TO core/main.py")
print("Change extract_intent to use tinyllama instead of qwen3:4b")
print("qwen3:4b stays for actual chat responses (it is smarter)")
print("tinyllama handles intent only (fast, lightweight)")
print("=" * 60)

with open("core/main.py", "r", encoding="utf-8", errors="replace") as f:
    content = f.read()

# Fix: Change model in extract_intent to tinyllama
# Find the extract_intent function and change only its model
old = (
    '        payload = {\n'
    '            "model": "qwen3:4b",\n'
    '            "messages": [\n'
    '                {"role": "system", "content": INTENT_SYSTEM_PROMPT},'
)
new = (
    '        payload = {\n'
    '            "model": "tinyllama",\n'
    '            "messages": [\n'
    '                {"role": "system", "content": INTENT_SYSTEM_PROMPT},'
)

if old in content:
    content = content.replace(old, new, 1)
    with open("core/main.py", "w", encoding="utf-8", errors="replace") as f:
        f.write(content)
    print("[FIXED] extract_intent now uses tinyllama")
    print("        Chat responses still use qwen3:4b")
else:
    # Try alternative format
    old2 = '"model": "qwen3:4b",'
    # Only replace inside extract_intent function
    # Find extract_intent, replace first occurrence of qwen3:4b after it
    ei_pos = content.find("async def extract_intent")
    if ei_pos == -1:
        ei_pos = content.find("def extract_intent")

    if ei_pos != -1:
        # Find end of function (next def)
        next_def = content.find("\nasync def ", ei_pos + 10)
        if next_def == -1:
            next_def = content.find("\ndef ", ei_pos + 10)

        func_content = content[ei_pos:next_def]
        if '"model": "qwen3:4b"' in func_content:
            new_func = func_content.replace('"model": "qwen3:4b"', '"model": "tinyllama"', 1)
            content = content[:ei_pos] + new_func + content[next_def:]
            with open("core/main.py", "w", encoding="utf-8", errors="replace") as f:
                f.write(content)
            print("[FIXED] extract_intent model changed to tinyllama")
        else:
            print("[INFO] Model in extract_intent: checking what it uses...")
            for line in func_content.split("\n"):
                if "model" in line.lower():
                    print("  " + line.strip())

import py_compile
try:
    py_compile.compile("core/main.py", doraise=True)
    print("[PASS] Syntax OK")
except py_compile.PyCompileError as e:
    print("[FAIL] " + str(e))

print()
print("=" * 60)
print("NEXT: restart server and test")
print("python jarvis.py server")
print("then: python -c \"import httpx; r=httpx.post(")
print("  'http://localhost:8000/api/chat',")
print("  json={'message':'play cry for me on yt'},timeout=120)")
print("; print(r.json()['action'])\"")
print("=" * 60)
