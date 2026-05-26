"""Test real-time data integrations."""
import requests
BASE = 'http://localhost:8000'

def chat(msg, timeout=120):
    r = requests.post(f'{BASE}/api/chat', json={'message': msg}, timeout=timeout)
    try:
        j = r.json()
    except Exception:
        return 'error', False, r.text[:200]
    return j.get('intent',{}).get('intent','?'), j.get('action',{}).get('executed'), j.get('response','')[:150]

tests = [
    ("What's the weather in London", "weather"),
    ("Temperature in New York", "weather"),
    ("AAPL stock price", "stocks"),
    ("latest technology news", "news"),
    ("NBA scores", "sports"),
    ("what time is it in Tokyo", "time"),
    ("What is Python", "chat"),
    ("Open cmd", "pc_control"),
]

for msg, exp in tests:
    intent, executed, resp = chat(msg)
    ok = 'PASS' if intent == exp else 'FAIL'
    print(f'{ok}: "{msg}" -> {intent} (expected {exp})')
    if ok: print(f'       {resp}')
    print()
