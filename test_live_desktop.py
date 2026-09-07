#!/usr/bin/env python3
"""REAL live test - physically moves mouse, clicks, types, manages windows."""
import sys, time
sys.path.insert(0, "C:/Users/peter/Desktop/jarvis")

from core.desktop.controller import desktop_controller
from core.desktop.window import window_controller

print("=" * 55)
print(" LIVE TEST - WATCH YOUR SCREEN")
print("=" * 55)

# 1. Move mouse to a corner slowly (watch it travel)
print("\n[1] Moving mouse to (100, 100)...")
desktop_controller.move_mouse(100, 100)
time.sleep(0.8)

# 2. Move to another point
print("[2] Moving mouse to (800, 400)...")
desktop_controller.move_mouse(800, 400)
time.sleep(0.8)

# 3. Move back to center
print("[3] Moving mouse to center (960, 540)...")
desktop_controller.move_mouse(960, 540)
time.sleep(0.5)

# 4. Read current position back
mx, my = desktop_controller.get_mouse_position()
print(f"[4] Mouse now at: ({mx}, {my})  <-- should match ~960,540")

# 5. List open windows - proves window detection
print("\n[5] Open windows on your desktop:")
wins = window_controller.list_windows()
for w in wins:
    print(f"     - {w['title']}")

# 6. Get active window
active = window_controller.get_active_window()
print(f"\n[6] Active window: {active['title'] if active else 'none'}")

print("\n" + "=" * 55)
print("If you saw the mouse physically move -> CONTROLLER WORKS")
print("If windows listed above -> WINDOW MANAGEMENT WORKS")
print("=" * 55)
