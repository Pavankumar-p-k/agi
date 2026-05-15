# test_raw_intent.py
# Run: python test_raw_intent.py

import httpx
import json
import re

INTENT_PROMPT = (
    "You are an intent parser for JARVIS. Return ONLY raw JSON. Nothing else.\n"
    "No explanation. No markdown. No thinking. Just JSON.\n\n"
    "JSON structure:\n"
    "{\"intent\": \"INTENT_NAME\", \"target\": \"TARGET\"}\n\n"
    "INTENT_NAME must be exactly one of:\n"
    "chat, open_url, play_media, open_app, web_search, reminder, pc_control\n\n"
    "Examples:\n"
    "play cry for me on yt => {\"intent\":\"play_media\",\"target\":\"cry for me\"}\n"
    "play beat it => {\"intent\":\"play_media\",\"target\":\"beat it\"}\n"
    "opn yt => {\"intent\":\"open_url\",\"target\":\"youtube\"}\n"
    "open youtube => {\"intent\":\"open_url\",\"target\":\"youtube\"}\n"
    "search latest news => {\"intent\":\"web_search\",\"target\":\"latest news\"}\n"
    "open notepad => {\"intent\":\"open_app\",\"target\":\"notepad\"}\n"
    "what is python => {\"intent\":\"chat\",\"target\":\"python\"}\n"
    "remind me call mom => {\"intent\":\"reminder\",\"target\":\"call mom\"}\n"
)

TEST_MESSAGES = [
    "play cry for me on yt",
    "opn yt",
    "play beat it michael jackson",
    "what is python",
    "open notepad",
    "search latest ai news",
]

print("=" * 60)
print("RAW INTENT TEST - direct Ollama call")
print("=" * 60)

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
                "options": {
                    "temperature": 0,
                    "num_predict": 60
                }
            },
            timeout=60
        )
        raw = r.json()["message"]["content"]
        # Strip thinking
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        # Strip markdown
        raw = re.sub(r"```json|```", "", raw).strip()

        print("\nMESSAGE: " + repr(msg))
        print("RAW    : " + repr(raw))

        try:
            parsed = json.loads(raw)
            print("INTENT : " + str(parsed.get("intent")))
            print("TARGET : " + str(parsed.get("target")))
        except Exception as e:
            print("PARSE FAILED: " + str(e))

    except Exception as e:
        print("\nMESSAGE: " + repr(msg))
        print("ERROR  : " + str(e))

print("\n" + "=" * 60)
print("KEY: play_media and open_url = JARVIS will act")
print("     chat = JARVIS will only respond, no action")
print("=" * 60)
