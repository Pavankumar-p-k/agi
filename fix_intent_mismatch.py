# fix_intent_mismatch.py
# Run: python fix_intent_mismatch.py
# This fixes the ONE bug causing JARVIS to not execute actions

import re

path = "core/main.py"

with open(path, "r", encoding="utf-8", errors="replace") as f:
    content = f.read()

print("=" * 60)
print("FIXING INTENT NAME MISMATCH IN core/main.py")
print("=" * 60)

# ─────────────────────────────────────────────────────────────
# THE BUG:
# execute_action() checks for:  "open_app"   "media_play"
# LLM actually returns:         "open_url"   "play_media"
# They never match = action never executes
#
# THE FIX:
# Update execute_action() to handle BOTH names
# so it works regardless of which the LLM returns
# ─────────────────────────────────────────────────────────────

# Fix 1: open_app → also handle open_url
old1 = '    if intent == "open_app":'
new1 = '    if intent in ("open_app", "open_url"):'

# Fix 2: media_play → also handle play_media
old2 = '    elif intent == "media_play":'
new2 = '    elif intent in ("media_play", "play_media"):'

# Fix 3: pc_control check
old3 = '    elif intent == "pc_control":'
new3 = '    elif intent in ("pc_control", "open_app_desktop"):'

# Fix 4: Also fix action_context check — currently skips if intent == "chat"
# but intent might be "open_url" which is also not "chat" — this should already work
# Let's also make sure reminder is handled
old4 = '    elif intent == "reminder":'
new4 = '    elif intent in ("reminder", "set_reminder"):'

# Apply fixes
fixes = [
    (old1, new1, "open_app + open_url"),
    (old2, new2, "media_play + play_media"),
    (old3, new3, "pc_control variants"),
    (old4, new4, "reminder variants"),
]

applied = 0
for old, new, name in fixes:
    if old in content:
        content = content.replace(old, new, 1)
        print("[FIXED] " + name)
        applied += 1
    else:
        print("[SKIP]  " + name + " (not found — may already be fixed)")

# Also fix the INTENT_SYSTEM_PROMPT if it uses wrong intent names
# The prompt should tell LLM to use the same names execute_action expects
# OR we make execute_action accept both (which we just did above)

# Fix 5: Update extract_intent examples to be consistent
# Change examples to use the names that execute_action now handles
old_examples = '''USER: opn yt
AI: {"intent":"open_app","action":"open","target":"youtube","parameters":{}}'''

new_examples = '''USER: opn yt
AI: {"intent":"open_url","action":"open","target":"youtube","parameters":{}}'''

if old_examples in content:
    content = content.replace(old_examples, new_examples, 1)
    print("[FIXED] extract_intent example: open_app -> open_url")
    applied += 1

old_examples2 = '''USER: play beat it by michael jackson
AI: {"intent":"media_play","action":"play","target":"beat it by michael jackson","parameters":{}}'''

new_examples2 = '''USER: play beat it by michael jackson
AI: {"intent":"play_media","action":"play","target":"beat it by michael jackson","parameters":{}}'''

if old_examples2 in content:
    content = content.replace(old_examples2, new_examples2, 1)
    print("[FIXED] extract_intent example: media_play -> play_media")
    applied += 1

# Write fixed content back
with open(path, "w", encoding="utf-8", errors="replace") as f:
    f.write(content)

print("\n[DONE] Applied " + str(applied) + " fixes to core/main.py")

# Verify the fix
import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("[PASS] Syntax check passed")
except py_compile.PyCompileError as e:
    print("[FAIL] Syntax error: " + str(e))

print("\n" + "=" * 60)
print("NOW TEST:")
print("1. Restart JARVIS server: python jarvis.py server")
print("2. Send: play cry for me on yt")
print("3. YouTube should ACTUALLY open in browser")
print("4. Response should say it opened, not 'I cant play videos'")
print("=" * 60)
