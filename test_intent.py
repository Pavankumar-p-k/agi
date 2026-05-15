# test_intent.py
# Run: python test_intent.py

import httpx
import json
import re

INTENT_PROMPT = (
    "You are an intent parser for JARVIS AI assistant.\n"
    "Read the user message and return ONLY a JSON object. Nothing else.\n"
    "No explanation. No markdown. No code blocks. Raw JSON only.\n\n"
    "JSON format:\n"
    "{\"intent\": \"chat|open_url|play_media|open_app|web_search|reminder|pc_control\","
    " \"target\": \"extracted target\"}\n\n"
    "Intent definitions:\n"
    "- chat: user wants to talk, ask a question, get information\n"
    "- open_url: user wants to open a website\n"
    "- play_media: user wants to play a song, video, or music\n"
    "- open_app: user wants to open a desktop application\n"
    "- web_search: user wants to search for something online\n"
    "- reminder: user wants to set a reminder or alarm\n"
    "- pc_control: user wants to control the computer\n\n"
    "Examples:\n"
    "play cry for me on yt -> {\"intent\":\"play_media\",\"target\":\"cry for me\"}\n"
    "play beat it michael jackson -> {\"intent\":\"play_media\",\"target\":\"beat it michael jackson\"}\n"
    "opn yt -> {\"intent\":\"open_url\",\"target\":\"youtube\"}\n"
    "open youtube -> {\"intent\":\"open_url\",\"target\":\"youtube\"}\n"
    "search latest ai news -> {\"intent\":\"web_search\",\"target\":\"latest ai news\"}\n"
    "open notepad -> {\"intent\":\"open_app\",\"target\":\"notepad\"}\n"
    "remind me call mom tomorrow 9am -> {\"intent\":\"reminder\",\"target\":\"call mom\"}\n"
    "take a screenshot -> {\"intent\":\"pc_control\",\"target\":\"screenshot\"}\n"
    "what is machine learning -> {\"intent\":\"chat\",\"target\":\"machine learning\"}\n"
    "who is elon musk -> {\"intent\":\"chat\",\"target\":\"elon musk\"}\n"
)

TEST_MESSAGES = [
    "play cry for me on yt",
    "opn yt",
    "play beat it by michael jackson",
    "open notepad",
    "what is python",
    "search latest ai tools",
    "remind me to drink water in 1 hour",
    "take screenshot",
    "open vs code",
    "who built you",
    "play kushi songs",
    "youtube lo open chey",
]

print("=" * 60)
print("INTENT TEST - qwen3:4b as brain, NOT keyword matching")
print("=" * 60)

correct = 0
total = len(TEST_MESSAGES)

for msg in TEST_MESSAGES:
    try:
        r = httpx.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen3:4b",
                "messages": [
                    {"role": "system", "content": INTENT_PROMPT},
                    {"role": "user", "content": msg}
                ],
                "stream": False,
                "options": {"temperature": 0}
            },
            timeout=30
        )
        raw = r.json()["message"]["content"]
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        parsed = json.loads(raw)
        intent = parsed.get("intent", "unknown")
        target = parsed.get("target", "")
        print("[OK] " + repr(msg))
        print("     intent=" + intent + " | target=" + target)
        correct += 1
    except json.JSONDecodeError:
        print("[FAIL-JSON] " + repr(msg))
        print("     Raw output: " + raw[:300])
    except Exception as e:
        print("[ERROR] " + repr(msg) + " => " + str(e))

print("=" * 60)
print("Results: " + str(correct) + "/" + str(total) + " parsed successfully")
print()
print("KEY CHECKS:")
print("  play cry for me on yt  -> should be play_media")
print("  opn yt                 -> should be open_url")
print("  what is python         -> should be chat")
print("  youtube lo open chey   -> should be open_url (Telugu)")
print("=" * 60)