from __future__ import annotations

import os
import sqlite3
import threading
import time
import dateparser
import webbrowser
import subprocess
import httpx
import urllib.parse
from datetime import datetime, timezone
from plyer import notification
from typing import Any

DB_PATH = os.path.join(os.getcwd(), "data", "jarvis.db")

def create_reminder(text: str, time_str: str) -> dict:
    # Parse time
    reminder_time = dateparser.parse(time_str, settings={"PREFER_DATES_FROM": "future"})
    if not reminder_time:
        return {"executed": False, "error": f"Could not parse time: {time_str}"}

    # Ensure time is in UTC for database storage to match SQLite's datetime('now')
    if reminder_time.tzinfo is None:
        reminder_time = reminder_time.astimezone(timezone.utc)
    else:
        reminder_time = reminder_time.astimezone(timezone.utc)

    # Write to DB
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    db_time = reminder_time.strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY, text TEXT, remind_at TEXT, notified INTEGER)")
    cur.execute(
        "INSERT INTO reminders (text, remind_at, notified) VALUES (?, ?, 0)",
        (text, db_time)
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()

    return {
        "executed": True,
        "type": "reminder",
        "id": row_id,
        "text": text,
        "time": db_time
    }

def check_reminders_loop():
    while True:
        try:
            if os.path.exists(DB_PATH):
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY, text TEXT, remind_at TEXT, notified INTEGER)")
                cur.execute(
                    "SELECT id, text FROM reminders WHERE remind_at <= datetime('now') AND notified = 0"
                )
                due = cur.fetchall()
                for row_id, text in due:
                    try:
                        notification.notify(
                            title="JARVIS Reminder",
                            message=text,
                            timeout=10
                        )
                    except Exception:
                        pass
                    print(f"[REMINDER FIRED] {text}")
                    cur.execute("UPDATE reminders SET notified = 1 WHERE id = ?", (row_id,))
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"[WARN] Reminder check error: {e}")
        time.sleep(60)

# Start reminder loop in background
reminder_thread = threading.Thread(target=check_reminders_loop, daemon=True)
reminder_thread.start()

def execute_action(tool_call: dict, jarvis_os_obj: Any) -> dict:
    """
    True Automation Dispatcher.
    Dynamically executes tool calls based on LLM reasoning.
    No keyword matching or hardcoded maps.
    """
    tool_name = tool_call.get("tool")
    params = tool_call.get("parameters", {})

    if not tool_name or tool_name == "chat":
        return {"executed": False, "type": "chat_only"}

    # 1. Reminders (Integrated Persistence)
    if tool_name == "create_reminder":
        return create_reminder(params.get("text", ""), params.get("time", ""))

    # 2. Native OS Execution (True Automation)
    if tool_name == "open_url":
        url = params.get("url", "")
        if url:
            webbrowser.open(url)
            return {"executed": True, "type": "browser", "url": url}

    elif tool_name == "play_media":
        target = params.get("query", "")
        query = urllib.parse.quote(target)
        url = f"https://www.youtube.com/results?search_query={query}"
        webbrowser.open(url)
        return {"executed": True, "type": "media", "platform": "youtube", "query": target, "url": url}

    elif tool_name == "search_google":
        target = params.get("query", "")
        try:
            query = urllib.parse.quote(target)
            r = httpx.get(
                f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1",
                timeout=10,
                follow_redirects=True
            )
            data = r.json()
            results = []
            if data.get("AbstractText"):
                results.append({"title": "Summary", "text": data["AbstractText"][:300], "url": data.get("AbstractURL", "")})
            for item in data.get("RelatedTopics", [])[:4]:
                if "Text" in item and "FirstURL" in item:
                    results.append({"title": item["Text"][:100], "url": item["FirstURL"]})
            return {"executed": True, "type": "search", "query": target, "results": results}
        except Exception as e:
            return {"executed": False, "error": str(e)}

    elif tool_name == "open_application":
        exe = params.get("application", "")
        if not exe:
             return {"executed": False, "error": "No application specified"}
        # Robustness for common user shorthand
        if not exe.endswith(".exe") and os.name == 'nt':
             exe += ".exe"
        try:
            subprocess.Popen([exe], shell=True)
            return {"executed": True, "type": "app", "launched": exe}
        except Exception as e:
            return {"executed": False, "error": str(e)}

    # 3. Dynamic JARVIS OS Registry Fallback (100+ Tools)
    if jarvis_os_obj and jarvis_os_obj.tools:
        try:
            result = jarvis_os_obj.tools.invoke(tool_name, **params)
            return {
                "executed": True,
                "tool": tool_name,
                "status": result.get("status"),
                "data": result.get("data"),
                "error": result.get("error")
            }
        except Exception as e:
            return {"executed": False, "error": f"Tool execution failed: {e}"}

    return {"executed": False, "error": f"Tool {tool_name} not recognized."}
