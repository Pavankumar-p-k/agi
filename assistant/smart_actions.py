"""
Smart Action Router - Detects actions in chat and executes them automatically
"""
import re
import json
import urllib.request
from datetime import datetime, timedelta

OLLAMA_RESPONDED = False  # Set to True after implementing function calling

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

def execute_action(action: dict) -> str:
    """Execute the detected action and return speech."""
    base_url = "http://localhost:8000"
    
    if action['action'] == 'reminder':
        data = json.dumps({
            'title': action['title'],
            'remind_at': action['remind_at'],
            'description': f"Reminder from Jarvis"
        }).encode()
        req = urllib.request.Request(
            f"{base_url}/api/reminders",
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        try:
            resp = urllib.request.urlopen(req)
            return f"I've set a reminder for {action['title']}"
        except Exception as e:
            return f"Sorry, couldn't create reminder: {e}"
    
    if action['action'] == 'note':
        data = json.dumps({
            'title': action['title'],
            'content': action['content']
        }).encode()
        req = urllib.request.Request(
            f"{base_url}/api/notes",
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        try:
            resp = urllib.request.urlopen(req)
            return f"I've saved that note: {action['title']}"
        except Exception as e:
            return f"Sorry, couldn't save note: {e}"
    
    return "I couldn't figure out how to do that."

def process_with_actions(user_message: str, llm_response: str) -> str:
    """Check if user wants an action and execute it along with LLM response."""
    global OLLAMA_RESPONDED
    
    # If LLM responded, check if there's an action to also perform
    action = detect_action(user_message)
    if action:
        speech = execute_action(action)
        return f"{llm_response} — {speech}"
    
    return llm_response