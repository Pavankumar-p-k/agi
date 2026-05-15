# show_and_fix.py
# Run: python show_and_fix.py
# Shows exact execute_action code then fixes it

import os

path = "core/main.py"

with open(path, "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

# ─────────────────────────────────────────
# STEP 1: Show EXACT execute_action code
# ─────────────────────────────────────────
print("=" * 60)
print("EXACT execute_action CODE:")
print("=" * 60)

in_execute = False
execute_start = 0
for i, line in enumerate(lines):
    if "def execute_action" in line or "async def execute_action" in line:
        in_execute = True
        execute_start = i
    if in_execute:
        print(str(i+1).rjust(4) + " | " + line.rstrip())
        # Stop at next function definition
        if i > execute_start + 3 and ("def " in line or "async def " in line) and i != execute_start:
            break

# ─────────────────────────────────────────
# STEP 2: Show what intent names are checked
# ─────────────────────────────────────────
print("\n" + "=" * 60)
print("ALL INTENT CHECKS IN execute_action:")
print("=" * 60)
in_execute = False
for i, line in enumerate(lines):
    if "def execute_action" in line or "async def execute_action" in line:
        in_execute = True
    if in_execute and ("intent ==" in line or "intent in" in line or "if intent" in line or "elif intent" in line):
        print(str(i+1).rjust(4) + " | " + line.rstrip())

# ─────────────────────────────────────────
# STEP 3: Show what LLM examples use
# ─────────────────────────────────────────
print("\n" + "=" * 60)
print("INTENT NAMES IN EXAMPLES (what LLM is told to return):")
print("=" * 60)
for i, line in enumerate(lines):
    if '"intent"' in line and ("play" in line.lower() or "open" in line.lower() or "search" in line.lower()):
        print(str(i+1).rjust(4) + " | " + line.rstrip())

# ─────────────────────────────────────────
# STEP 4: THE ACTUAL FIX
# Make execute_action handle ALL possible intent names
# by adding aliases for each
# ─────────────────────────────────────────
print("\n" + "=" * 60)
print("APPLYING FIX - Adding intent name aliases...")
print("=" * 60)

content = "".join(lines)

# Find all if/elif intent checks and add aliases
replacements = [
    # open_app variants
    ('if intent == "open_app":', 'if intent in ("open_app", "open_url", "open_website", "open_browser"):'),
    ("if intent == 'open_app':", "if intent in ('open_app', 'open_url', 'open_website', 'open_browser'):"),

    # media_play variants
    ('elif intent == "media_play":', 'elif intent in ("media_play", "play_media", "play", "play_music", "play_video"):'),
    ("elif intent == 'media_play':", "elif intent in ('media_play', 'play_media', 'play', 'play_music', 'play_video'):"),

    # open_url variants (in case execute_action uses this instead)
    ('if intent == "open_url":', 'if intent in ("open_url", "open_app", "open_website", "open_browser"):'),
    ("if intent == 'open_url':", "if intent in ('open_url', 'open_app', 'open_website', 'open_browser'):"),

    # play_media variants
    ('elif intent == "play_media":', 'elif intent in ("play_media", "media_play", "play", "play_music", "play_video"):'),
    ("elif intent == 'play_media':", "elif intent in ('play_media', 'media_play', 'play', 'play_music', 'play_video'):"),

    # web_search variants
    ('elif intent == "web_search":', 'elif intent in ("web_search", "search", "search_web", "google"):'),
    ("elif intent == 'web_search':", "elif intent in ('web_search', 'search', 'search_web', 'google'):"),

    # pc_control variants
    ('elif intent == "pc_control":', 'elif intent in ("pc_control", "open_app_desktop", "launch_app", "run_app"):'),
    ("elif intent == 'pc_control':", "elif intent in ('pc_control', 'open_app_desktop', 'launch_app', 'run_app'):"),

    # reminder variants
    ('elif intent == "reminder":', 'elif intent in ("reminder", "set_reminder", "remind", "alarm"):'),
    ("elif intent == 'reminder':", "elif intent in ('reminder', 'set_reminder', 'remind', 'alarm'):"),
]

applied = 0
for old, new in replacements:
    if old in content:
        content = content.replace(old, new, 1)
        print("[FIXED] " + old[:50] + "...")
        applied += 1

if applied == 0:
    print("[WARN] No standard patterns found.")
    print("Showing all if/elif intent lines for manual check:")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("if intent") or stripped.startswith("elif intent"):
            print(str(i+1).rjust(4) + " | " + line.rstrip())
else:
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        f.write(content)
    print("\n[SAVED] " + str(applied) + " fixes written to core/main.py")

    import py_compile
    try:
        py_compile.compile(path, doraise=True)
        print("[PASS] Syntax OK")
    except py_compile.PyCompileError as e:
        print("[FAIL] Syntax error: " + str(e))

print("\n" + "=" * 60)
print("NEXT STEPS:")
print("1. Run: python jarvis.py server")
print("2. In new terminal test:")
print('   python -c "import httpx; r=httpx.post(')
print("   'http://localhost:8000/api/chat',")
print("   json={'message':'play cry for me on yt'},timeout=60)")
print("   ; print(r.json()['action'])")
print("   ; print(r.json()['response'])")
print('   "')
print("=" * 60)
