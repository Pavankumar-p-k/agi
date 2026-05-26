"""100-task test suite for JARVIS - low to high complexity."""
import requests, sys, time, json
BASE = 'http://localhost:8000'

TEST_LOG = []

def chat(msg, timeout=120):
    t = time.time()
    r = requests.post(f'{BASE}/api/chat', json={'message': msg}, timeout=timeout)
    j = r.json()
    return j.get('response',''), j.get('intent',{}).get('intent','?'), j.get('action',{}), time.time()-t

def run(test_id, name, msg, expect_intent=None, max_time=120):
    print(f"[{test_id:03d}] {name} ({expect_intent or 'any'})...", end=" ")
    sys.stdout.flush()
    try:
        resp, intent, action, elapsed = chat(msg, timeout=max_time)
        ok = True
        if expect_intent and intent != expect_intent:
            ok = False
        if action.get("error"):
            ok = False
        status = "PASS" if ok else "FAIL"
        err = action.get("error","")[:40] if action.get("error") else ""
        print(f"[{status}] {intent} {elapsed:.0f}s {err}")
        TEST_LOG.append((test_id, name, status, intent, elapsed, action.get("error","")))
        return ok
    except Exception as e:
        print(f"[TIMEOUT] {e}")
        TEST_LOG.append((test_id, name, "TIMEOUT", "?", 0, str(e)[:60]))
        return False

# Start server
print("Waiting for server...")
t0 = time.time()
while time.time() - t0 < 120:
    try:
        requests.get(f"{BASE}/health", timeout=2)
        print(f"Server ready in {time.time()-t0:.0f}s\n")
        break
    except:
        time.sleep(3)

print("=" * 70)
print("PHASE 1: LOW COMPLEXITY - Simple greetings & basic chat")
print("=" * 70)

tests_run = 0
# --- 1-10: Greetings, small talk ---
test_id = 1
for msg in [
    "Hi", "Hello", "Hey", "What's up", "How are you",
    "Good morning", "Hello JARVIS", "Hey there", "Hi buddy", "Greetings"
]:
    run(test_id, f"Greeting: {msg[:20]}", msg, expect_intent="chat"); test_id += 1; tests_run += 1

# --- 11-20: Simple questions ---
for msg in [
    "What time is it", "What day is it", "What is Python",
    "What is AI", "Who are you", "What can you do",
    "Tell me a joke", "What is 2+2", "What is the capital of France",
    "How does the internet work"
]:
    run(test_id, f"Question: {msg[:25]}", msg, expect_intent="chat"); test_id += 1; tests_run += 1

print(f"\nPhase 1 done: {tests_run} tests")

print("=" * 70)
print("PHASE 2: MEDIUM - Memory, intents, tools")
print("=" * 70)

# --- 21-25: Memory store & recall ---
run(test_id, "Store fact: favorite food", "Remember that I love pizza and my favorite drink is coffee", expect_intent="chat"); test_id += 1
run(test_id, "Recall fact", "What's my favorite food?", expect_intent="chat"); test_id += 1
run(test_id, "Recall another fact", "What's my favorite drink?", expect_intent="chat"); test_id += 1
run(test_id, "Store second fact", "I have a cat named Whiskers", expect_intent="chat"); test_id += 1
run(test_id, "Cross-reference recall", "What's my cat's name and my favorite food?", expect_intent="chat"); test_id += 1; tests_run += 5

# --- 26-30: PC control ---
run(test_id, "PC: open notepad", "Open notepad", expect_intent="pc_control"); test_id += 1
run(test_id, "PC: open calculator", "Open calculator", expect_intent="pc_control"); test_id += 1
run(test_id, "PC: open cmd", "Open cmd", expect_intent="pc_control"); test_id += 1
run(test_id, "PC: open vscode", "Open vscode", expect_intent="pc_control"); test_id += 1
run(test_id, "PC: open chrome", "Open chrome", expect_intent="pc_control"); test_id += 1; tests_run += 5

# --- 31-33: Open URL ---
run(test_id, "URL: go to google", "Go to google.com", expect_intent="open_url"); test_id += 1
run(test_id, "URL: open youtube", "Open youtube", expect_intent="open_url"); test_id += 1
run(test_id, "URL: open github", "Open github", expect_intent="open_url"); test_id += 1; tests_run += 3

# --- 34-38: Web search ---
run(test_id, "Search: latest AI", "Search latest AI developments 2026", expect_intent="web_search"); test_id += 1
run(test_id, "Search: weather", "What's the weather in London", expect_intent="web_search"); test_id += 1
run(test_id, "Search: news", "Search for today's news", expect_intent="web_search"); test_id += 1
run(test_id, "Search: python", "Search for Python 3.13 features", expect_intent="web_search"); test_id += 1
run(test_id, "Search: stocks", "Search for stock market news", expect_intent="web_search"); test_id += 1; tests_run += 5

print(f"\nPhase 2 done: {tests_run} tests")

print("=" * 70)
print("PHASE 3: HIGH - Multi-intent, composio, browser")
print("=" * 70)

# --- 39-48: Message/composio ---
run(test_id, "Composio: send email", "Send an email to pavankumarunnam99@gmail.com with subject JARVIS test saying This is a test from the 100-test suite", expect_intent="message"); test_id += 1
run(test_id, "Composio: github issue", "Create a github issue in pavan/jarvis with title Test 100 and body Automated test", expect_intent="message"); test_id += 1
run(test_id, "Composio: email with CC", "Send email to pavankumarunnam99@gmail.com with subject CC test saying This has a CC", expect_intent="message"); test_id += 1
run(test_id, "Composio: long email", "Send an email to pavankumarunnam99@gmail.com with subject Long test saying This is a longer test email body to verify that the composio integration handles longer content properly with multiple sentences and formatting", expect_intent="message"); test_id += 1
run(test_id, "Composio: github with body", "Create a github issue in pavan/jarvis with title Automated test with body This has a detailed body with steps to reproduce", expect_intent="message"); test_id += 1; tests_run += 5

# --- 49-53: Browser automation ---
run(test_id, "Browser: navigate URL", "Go to https://example.com", expect_intent="browser_task", max_time=90); test_id += 1
run(test_id, "Browser: search site", "Open google and search for Python", expect_intent="browser_task", max_time=90); test_id += 1
run(test_id, "Browser: visit page", "Visit stackoverflow.com", expect_intent="browser_task", max_time=90); test_id += 1
run(test_id, "Browser: open and read", "Go to example.com and tell me what the page says", expect_intent="browser_task", max_time=90); test_id += 1; tests_run += 4

# --- 54-58: Play media ---
run(test_id, "Play: song", "Play Never Gonna Give You Up", expect_intent="play_media"); test_id += 1
run(test_id, "Play: music", "Play some relaxing music", expect_intent="play_media"); test_id += 1
run(test_id, "Play: video", "Play funny cat videos", expect_intent="play_media"); test_id += 1
run(test_id, "Play: specific", "Play Bohemian Rhapsody on YouTube", expect_intent="play_media"); test_id += 1; tests_run += 4

# --- 59-68: Intent switching + memory persistence ---
run(test_id, "Memory: recall after tools", "What's my cat's name?", expect_intent="chat"); test_id += 1
run(test_id, "Memory: recall food", "What food do I like?", expect_intent="chat"); test_id += 1
run(test_id, "Switch: search after memory", "Search for cat care tips", expect_intent="web_search"); test_id += 1
run(test_id, "Switch: chat after search", "Thanks! That was helpful", expect_intent="chat"); test_id += 1
run(test_id, "Switch: email after chat", "Send an email to pavankumarunnam99@gmail.com with subject Thanks saying Thanks for all the help", expect_intent="message"); test_id += 1
run(test_id, "Switch: pc after message", "Open notepad", expect_intent="pc_control"); test_id += 1
run(test_id, "Memory: recall across switches", "What's my favorite drink again?", expect_intent="chat"); test_id += 1
run(test_id, "Switch: url after pc", "Go to google.com", expect_intent="open_url"); test_id += 1
run(test_id, "Switch: media after url", "Play some lo-fi music", expect_intent="play_media"); test_id += 1
run(test_id, "Memory: full context recall", "Tell me everything you remember about me", expect_intent="chat"); test_id += 1; tests_run += 10

print(f"\nPhase 3 done: {tests_run} tests")

print("=" * 70)
print("PHASE 4: COMPLEX - Edge cases, combined requests")
print("=" * 70)

# --- 69-73: Combined requests ---
run(test_id, "Combined: two pc actions", "Open notepad and then open calculator", max_time=120); test_id += 1
run(test_id, "Combined: search + chat", "Search for quantum computing and explain it simply", max_time=120); test_id += 1
run(test_id, "Combined: url + question", "Go to google.com and tell me what you see", max_time=90); test_id += 1
run(test_id, "Combined: play + search", "Play jazz music and search for jazz history", max_time=120); test_id += 1
run(test_id, "Combined: email + memory", "Send an email using my info saying I love pizza and coffee", max_time=120); test_id += 1; tests_run += 5

# --- 74-83: Edge cases ---
run(test_id, "Edge: empty message", " ", max_time=30); test_id += 1  # might fail
run(test_id, "Edge: very long query", "I need help with " + "hello " * 50, max_time=60); test_id += 1
run(test_id, "Edge: special chars", "What is @#$%! testing *&^ symbols", max_time=60); test_id += 1
run(test_id, "Edge: numbers only", "42", max_time=60); test_id += 1
run(test_id, "Edge: single word", "JARVIS", max_time=60); test_id += 1
run(test_id, "Edge: URL directly", "https://www.google.com", max_time=90); test_id += 1
run(test_id, "Edge: non-English greeting", "Bonjour JARVIS", max_time=60); test_id += 1
run(test_id, "Edge: negative test", "Do something impossible that you cannot do", max_time=60); test_id += 1
run(test_id, "Edge: repeat request", "Open notepad", max_time=60); test_id += 1
run(test_id, "Edge: what did you do", "What did you do just now?", max_time=60); test_id += 1; tests_run += 10

# --- 84-93: Stress test ---
for i in range(10):
    run(test_id, f"Stress: rapid chat {i+1}", f"Message number {i+1} in rapid succession test", max_time=60); test_id += 1; tests_run += 1

# --- 94-100: Final memory & wrap-up ---
run(test_id, "Final: recall everything", "What do you know about me from our conversation?", expect_intent="chat"); test_id += 1
run(test_id, "Final: search weather", "Search weather forecast for tomorrow", expect_intent="web_search"); test_id += 1
run(test_id, "Final: send summary email", "Send an email to pavankumarunnam99@gmail.com with subject Test summary saying All 100 tests completed", expect_intent="message"); test_id += 1
run(test_id, "Final: goodbye", "Goodbye JARVIS, thanks for your help", expect_intent="chat"); test_id += 1
run(test_id, "Final: memory check", "What was the subject of the last email I sent?", expect_intent="chat"); test_id += 1
run(test_id, "Final: what happened", "What happened during our test session?", expect_intent="chat"); test_id += 1; tests_run += 6

print("=" * 70)
print("SUMMARY")
print("=" * 70)
passed = sum(1 for t in TEST_LOG if t[2] == "PASS")
failed = sum(1 for t in TEST_LOG if t[2] == "FAIL")
timeout = sum(1 for t in TEST_LOG if t[2] == "TIMEOUT")
print(f"Total: {len(TEST_LOG)}  Passed: {passed}  Failed: {failed}  Timeout: {timeout}")
print()

if failed > 0:
    print("FAILURES:")
    for t in TEST_LOG:
        if t[2] == "FAIL":
            print(f"  [{t[0]:03d}] {t[1]} - intent={t[3]} ({t[4]:.0f}s) err={t[5]}")
if timeout > 0:
    print("TIMEOUTS:")
    for t in TEST_LOG:
        if t[2] == "TIMEOUT":
            print(f"  [{t[0]:03d}] {t[1]} - {t[5]}")

# Save log
with open("test_results.json", "w") as f:
    json.dump(TEST_LOG, f)
print("\nResults saved to test_results.json")
