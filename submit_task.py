import json
import urllib.request

content = """Research the current best practices for building a headless realtime automation agent in Python. Do this as a web automation task:
1. Search the web for reliable sources about agent runtimes, browser automation, job queues, event streams, MCP, and permission systems.
2. Visit at least 5 useful sources.
3. Extract concrete implementation patterns.
4. Compare Playwright, Selenium, browser-use style agents, and MCP tool servers.
5. Identify what parts apply to this local JARVIS repo.
6. Produce a practical implementation plan for turning JARVIS into a headless realtime automation daemon.
7. Include risks, dependencies, and next coding steps.
8. Save or return a structured report with sections: Summary, Sources, Architecture, Recommended Stack, Implementation Plan, Risks, Next PRs."""

body = json.dumps({
    "tool": "chat_with_model",
    "content": "ollama/qwen2.5:3b\n" + content,
    "session_id": "web-automation-large-1",
    "owner": "local-user"
}).encode()

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/tools/execute",
    data=body,
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())
        print(json.dumps(result, indent=2))
except Exception as e:
    print("Error:", e)