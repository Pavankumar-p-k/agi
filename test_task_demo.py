#!/usr/bin/env python3
"""FULL END-TO-END task: opens Notepad, types text, closes it.
Watch your screen - it will do all this by itself."""
import sys, time, subprocess
sys.path.insert(0, "C:/Users/peter/Desktop/jarvis")

from core.desktop.controller import desktop_controller
from core.desktop.window import window_controller
from core.workspace.process_monitor import ProcessMonitor

print("=" * 55)
print(" AUTONOMOUS TASK DEMO - opening Notepad...")
print("=" * 55)

# STEP 1: Launch Notepad
print("\n[1] Launching Notepad app...")
desktop_controller.launch_app("notepad")
time.sleep(2)

# STEP 2: Verify it launched by checking process monitor
pm = ProcessMonitor()
if pm.is_running("notepad"):
    print("[2] CONFIRMED: Notepad process is running")
else:
    print("[2] Notepad not detected, giving it more time...")
    time.sleep(2)

# STEP 3: Type text into the new window (it should be focused)
print("[3] Typing text into Notepad...")
desktop_controller.type_text("Hello JARVIS! This text was typed automatically.")
time.sleep(1)

# STEP 4: Press Enter, type another line
desktop_controller.press_key("enter")
desktop_controller.type_text("Desktop automation is working!")
time.sleep(1)

# STEP 5: Find and close the Notepad window
print("[4] Closing the Notepad window...")
result = window_controller.close("Untitled - Notepad")
print(f"[5] Close result: {'SUCCESS' if result.success else result.error}")

import os
print("\n" + "=" * 55)
print(" DONE! Check Notepad - it should have typed:")
print("  'Hello JARVIS! This text was typed automatically.'")
print("  'Desktop automation is working!'")
print("=" * 55)
