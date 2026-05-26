"""Test automation tasks + chat."""
import requests, json, sys
BASE = 'http://localhost:8000'

results = []

def chat(msg):
    r = requests.post(f'{BASE}/api/chat', json={'message': msg}, timeout=120)
    j = r.json()
    return j.get('response',''), j.get('intent',{}).get('intent','?'), j.get('action',{})

def log(name, resp, intent, action, expect_intent=None):
    ok = expect_intent is None or intent == expect_intent
    status = 'PASS' if ok else 'CHECK'
    print(f"  [{status}] intent={intent} executed={action.get('executed')}")
    print(f"         {resp[:150]}")
    results.append((name, status))
    print()

print("=" * 60)
print("TEST 1: PC control - launch notepad")
resp, intent, action = chat("Open notepad")
log("launch notepad", resp, intent, action, expect_intent="pc_control")

print("=" * 60)
print("TEST 2: PC control - open calculator")
resp, intent, action = chat("Open calculator")
log("open calculator", resp, intent, action, expect_intent="pc_control")

print("=" * 60)
print("TEST 3: Open URL - go to google")
resp, intent, action = chat("Go to google.com")
log("go to google", resp, intent, action, expect_intent="open_url")

print("=" * 60)
print("TEST 4: Open URL - open youtube")
resp, intent, action = chat("Open youtube")
log("open youtube", resp, intent, action, expect_intent="open_url")

print("=" * 60)
print("TEST 5: Browser task - multi-step")
resp, intent, action = chat("Open youtube and search for AI 2026")
log("browser multi-step", resp, intent, action, expect_intent="browser_task")

print("=" * 60)
print("TEST 6: Play media - play a song")
resp, intent, action = chat("Play never gonna give you up")
log("play media", resp, intent, action, expect_intent="play_media")

print("=" * 60)
print("TEST 7: Combined - open vscode and create a file")
resp, intent, action = chat("Open vscode and create a new python file")
log("combined action", resp, intent, action)

print("=" * 60)
print("TEST 8: General chat after automation")
resp, intent, action = chat("What did you just do for me?")
log("recall actions", resp, intent, action)

print("=" * 60)
print("SUMMARY")
for name, status in results:
    print(f"  {name}: {status}")
