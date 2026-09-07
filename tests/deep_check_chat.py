# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
# deep_check_chat.py
# Run: python deep_check_chat.py
# Shows exactly what /api/chat does line by line

import os
logger = logging.getLogger(__name__)

path = "core/main.py"

if not os.path.exists(path):
    print("[FAIL] core/main.py not found")
    exit()

with open(path, "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

print("=" * 70)
print("DEEP CHECK: core/main.py chat handler")
print("=" * 70)

# Find ALL chat-related sections
print("\n[1] IMPORTS at top of file:")
for i, line in enumerate(lines[:50]):
    if any(x in line for x in ["webbrowser", "action_executor", "subprocess", "execute_action", "extract_intent"]):
        print(str(i+1).rjust(4) + " | " + line.rstrip())

print("\n[2] INTENT PROMPT definition:")
for i, line in enumerate(lines):
    if "INTENT_PROMPT" in line or "intent_prompt" in line.lower():
        for j in range(i, min(i+5, len(lines))):
            print(str(j+1).rjust(4) + " | " + lines[j].rstrip())
        print("...")
        break

print("\n[3] extract_intent function:")
for i, line in enumerate(lines):
    if "def extract_intent" in line or "async def extract_intent" in line:
        print("Found at line " + str(i+1))
        for j in range(i, min(i+40, len(lines))):
            print(str(j+1).rjust(4) + " | " + lines[j].rstrip())
            if j > i and ("def " in lines[j] or "async def " in lines[j]):
                break
        break

print("\n[4] execute_action function:")
found_execute = False
for i, line in enumerate(lines):
    if "def execute_action" in line or "async def execute_action" in line:
        found_execute = True
        print("Found at line " + str(i+1))
        for j in range(i, min(i+60, len(lines))):
            print(str(j+1).rjust(4) + " | " + lines[j].rstrip())
            if j > i and ("def " in lines[j] or "async def " in lines[j]):
                break
        break
if not found_execute:
    print("[NOT FOUND] execute_action function does not exist in core/main.py")
    print("This is the broken wire. It was never created.")

print("\n[5] /api/chat POST handler - THE KEY:")
for i, line in enumerate(lines):
    if ('"/api/chat"' in line or "'/api/chat'" in line) and ("post" in line.lower() or "Post" in line):
        print("Found at line " + str(i+1))
        # Print 60 lines of the handler
        for j in range(max(0,i-2), min(i+80, len(lines))):
            print(str(j+1).rjust(4) + " | " + lines[j].rstrip())
        break

print("\n[6] WHERE IS execute_action CALLED in main.py?")
called = False
for i, line in enumerate(lines):
    if "execute_action" in line and "def execute_action" not in line:
        called = True
        print("Line " + str(i+1) + ": " + line.rstrip())
if not called:
    print("[NOT CALLED ANYWHERE] execute_action is never called from chat handler")
    print("This confirms the broken wire - intent is extracted but action never runs")

print("\n[7] WHERE IS extract_intent CALLED?")
called2 = False
for i, line in enumerate(lines):
    if "extract_intent" in line and "def extract_intent" not in line:
        called2 = True
        print("Line " + str(i+1) + ": " + line.rstrip())
if not called2:
    print("[NOT CALLED] extract_intent is never called from chat handler")

print("\n[8] Full action executor search in whole project:")
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", "node_modules", "build", ".dart_tool", "archive"]]
    for f in files:
        if f.endswith(".py"):
            fpath = os.path.join(root, f)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as fp:
                    content = fp.read()
                if "webbrowser.open" in content:
                    print("webbrowser.open found in: " + fpath)
                if "execute_action" in content and "def execute_action" in content:
                    print("execute_action DEFINED in: " + fpath)
            except Exception as e:
                logger.warning("[tests.deep_check_chat] verify_chat_response failed: %s", e)

print("\n" + "=" * 70)
print("VERDICT:")
print("If execute_action is [NOT FOUND] above = it was never created")
print("If execute_action is [NOT CALLED] above = it exists but not wired")
print("Either way paste this output and we write the exact fix")
print("=" * 70)
