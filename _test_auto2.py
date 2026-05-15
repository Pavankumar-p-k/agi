"""Quick automation test suite."""
import requests, sys, time
BASE = 'http://localhost:8000'

def chat(msg):
    t = time.time()
    r = requests.post(f'{BASE}/api/chat', json={'message': msg}, timeout=120)
    j = r.json()
    return j.get('response',''), j.get('intent',{}).get('intent','?'), j.get('action',{}), time.time()-t

tests = [
    ("open_url - go to google.com", "Go to google.com"),
    ("open_url - open youtube", "Open youtube"),
    ("play_media - play a song", "Play never gonna give you up"),
    ("browser_task - multi step", "Open youtube and search for AI 2026"),
    ("pc_control - open notepad", "Open notepad"),
    ("message - send email", "Send an email to pavankumarunnam99@gmail.com with subject Test saying Hi"),
    ("chat after auto", "What did you just do?"),
    ("web_search - search news", "Search for latest AI news"),
    ("open_url - open github", "Open github"),
    ("pc_control - open calculator", "Open calculator"),
]

passed = 0
failed = 0
for i, (name, msg) in enumerate(tests, 1):
    print(f"{i}. {name}...", end=" ")
    sys.stdout.flush()
    try:
        resp, intent, action, elapsed = chat(msg)
        ok = action.get("executed") == True or intent == "chat"
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"[{status}] {intent} ({elapsed:.0f}s) {resp[:60]}")
    except Exception as e:
        print(f"[ERROR] {e}")
        failed += 1

print(f"\nResults: {passed}/{len(tests)} passed, {failed} failed")
