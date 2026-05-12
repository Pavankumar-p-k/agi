"""
Smart Action Router - Detects actions in chat and executes them automatically
"""
import re
import json
import httpx
import webbrowser
import subprocess
from datetime import datetime, timedelta

OLLAMA_RESPONDED = False  # Set to True after implementing function calling

PC_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "terminal": "cmd.exe",
    "powershell": "powershell.exe",
    "vscode": "code",
}

def parse_time_relative(time_str: str) -> datetime:
    """Parse relative time strings like 'in 2 hours', 'tomorrow at 9am'."""
    now = datetime.now()
    time_str = time_str.lower().strip()

    # Defaults
    target_time = now + timedelta(hours=1)

    try:
        if 'minute' in time_str:
            mins = int(re.search(r'(\d+)', time_str).group(1))
            target_time = now + timedelta(minutes=mins)
        elif 'hour' in time_str:
            hours = int(re.search(r'(\d+)', time_str).group(1))
            target_time = now + timedelta(hours=hours)
        elif 'day' in time_str:
            days = int(re.search(r'(\d+)', time_str).group(1))
            target_time = now + timedelta(days=days)
        elif 'tomorrow' in time_str:
            target_time = now + timedelta(days=1)
            # Check for specific time like "tomorrow at 9am"
            time_match = re.search(r'(\d+)\s*(am|pm)', time_str)
            if time_match:
                hour = int(time_match.group(1))
                if time_match.group(2) == 'pm' and hour < 12:
                    hour += 12
                elif time_match.group(2) == 'am' and hour == 12:
                    hour = 0
                target_time = target_time.replace(hour=hour, minute=0, second=0, microsecond=0)
        elif 'at' in time_str:
            time_match = re.search(r'(\d+)\s*(am|pm)', time_str)
            if time_match:
                hour = int(time_match.group(1))
                if time_match.group(2) == 'pm' and hour < 12:
                    hour += 12
                elif time_match.group(2) == 'am' and hour == 12:
                    hour = 0
                target_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                if target_time < now:
                    target_time += timedelta(days=1)
    except Exception:
        pass # Fallback to default

    return target_time

def detect_action(text: str) -> dict | None:
    """Detect if user wants an action, return (action, params) or None."""
    text = text.lower().strip()
    
    # Reminder patterns
    reminder_match = re.search(r'(remind|reminder|alert) (me|us)? (.+) (at|in) (.+)', text)
    if reminder_match:
        what = reminder_match.group(3).strip()
        when = reminder_match.group(5).strip()
        # Parse time
        remind_at = datetime.now() + timedelta(hours=1)  # Default 1 hour
        if 'tomorrow' in when:
            remind_at = datetime.now() + timedelta(days=1)
        return {'action': 'reminder', 'title': what, 'remind_at': remind_at.isoformat()}
    
    # Note patterns  
    note_match = re.search(r'(note|save|write) (.+)', text)
    if note_match:
        content = note_match.group(2).strip()
        return {'action': 'note', 'content': content, 'title': content[:50]}
    
    # Contact patterns
    contact_match = re.search(r'(add|new) contact (.+)', text)
    if contact_match:
        name = contact_match.group(2).strip()
        return {'action': 'contact', 'name': name}
    
    return None

async def execute_action(action: dict) -> dict:
    """Execute the detected action and return structured result."""
    base_url = "http://localhost:8000"
    result = {"executed": False, "speech": ""}

    act = action.get('action')
    
    async with httpx.AsyncClient() as client:
        if act == 'set_reminder' or act == 'reminder':
            title = action.get('title')
            time_str = action.get('time', 'in 1 hour')
            remind_at = parse_time_relative(time_str)

            payload = {
                'title': title,
                'remind_at': remind_at.isoformat(),
                'description': f"Reminder from Jarvis"
            }
            try:
                await client.post(f"{base_url}/api/reminders", json=payload)
                result["executed"] = True
                result["speech"] = f"I've set a reminder for {title} at {remind_at.strftime('%I:%M %p')}."
            except Exception as e:
                result["speech"] = f"Sorry, I couldn't create that reminder."
                print(f"[Action] Reminder error: {e}")

        elif act == 'create_note' or act == 'note':
            content = action.get('content')
            title = action.get('title', content[:30])
            payload = {
                'title': title,
                'content': content
            }
            try:
                await client.post(f"{base_url}/api/notes", json=payload)
                result["executed"] = True
                result["speech"] = f"I've saved that note."
            except Exception as e:
                result["speech"] = f"Sorry, I couldn't save the note."
                print(f"[Action] Note error: {e}")

        elif act == 'pc_control':
            app_name = action.get('app', '').lower()
            exe = PC_APPS.get(app_name, app_name)
            try:
                subprocess.Popen(exe, shell=True)
                result["executed"] = True
                result["speech"] = f"Opening {app_name}."
            except Exception as e:
                result["speech"] = f"Failed to open {app_name}."
                print(f"[Action] PC Control error: {e}")

        elif act == 'media_play':
            query = action.get('query', '')
            url = f"https://www.youtube.com/results?search_query={query}"
            try:
                webbrowser.open(url)
                result["executed"] = True
                result["speech"] = f"Playing {query} on YouTube."
            except Exception as e:
                result["speech"] = f"Failed to play media."
                print(f"[Action] Media error: {e}")

        elif act == 'web_search':
            query = action.get('query', '')
            url = f"https://www.google.com/search?q={query}"
            try:
                webbrowser.open(url)
                result["executed"] = True
                result["speech"] = f"Searching for {query}."
            except Exception as e:
                result["speech"] = f"Failed to perform search."
                print(f"[Action] Search error: {e}")
    
    return result

async def process_with_actions(user_message: str, llm_response: str) -> str:
    """Check if user wants an action and execute it along with LLM response."""
    # This is legacy rule-based action detection
    action = detect_action(user_message)
    if action:
        res = await execute_action(action)
        if res.get("executed"):
            return f"{llm_response} — {res.get('speech')}"
    
    return llm_response