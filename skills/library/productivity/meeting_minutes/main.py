import re
from datetime import datetime

from skills.utils import success_response, error_response

def _extract_title(text):
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    for l in lines[:5]:
        if l.lower().startswith(("title:", "subject:", "re:")):
            return l.split(":", 1)[1].strip()
    for l in lines[:3]:
        if len(l) < 100 and not l.startswith(("#", "http")):
            return l
    return "Meeting Notes"

def _extract_date(text):
    patterns = [
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
        r"\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return datetime.now().strftime("%Y-%m-%d")

def _extract_attendees(text):
    attendees = set()
    for prefix in ["attendees:", "attendee:", "participants:", "present:", "people:"]:
        for l in text.split("\n"):
            if l.strip().lower().startswith(prefix):
                parts = l.split(":", 1)[1] if ":" in l else ""
                for name in re.split(r"[,;]", parts):
                    name = name.strip().strip("-* ")
                    if name:
                        attendees.add(name)
    email_pattern = r'\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b'
    for m in re.findall(email_pattern, text):
        attendees.add(m)
    return list(attendees)

def _extract_agenda(text):
    items = []
    in_agenda = False
    for l in text.split("\n"):
        stripped = l.strip()
        if stripped.lower().startswith("agenda"):
            in_agenda = True
            continue
        if in_agenda:
            if stripped.lower().startswith(("decision", "action", "notes")):
                break
            if stripped.startswith(("-", "*", "1.", "2.", "3.", "4.", "5.")):
                items.append(stripped.lstrip("-* ").strip())
            elif stripped and not stripped.startswith("#"):
                items.append(stripped)
    return items if items else ["General discussion"]

def _extract_decisions(text):
    decisions = []
    in_section = False
    for l in text.split("\n"):
        stripped = l.strip()
        if stripped.lower().startswith("decision"):
            in_section = True
            continue
        if in_section:
            if stripped.lower().startswith(("action", "next", "notes")):
                break
            if stripped.startswith(("-", "*")):
                decisions.append(stripped.lstrip("-* ").strip())
            elif stripped:
                decisions.append(stripped)
    return decisions

def _extract_action_items(text):
    items = []
    for l in text.split("\n"):
        stripped = l.strip()
        if stripped.lower().startswith(("action", "todo", "owner:")):
            parts = re.split(r"[:]", stripped, maxsplit=1)
            rest = parts[1].strip() if len(parts) > 1 else parts[0]
            owner = ""
            if "@" in rest:
                owner = rest.split("@")[-1].split()[0] if rest.split("@")[-1].split() else ""
            items.append({"action": rest.lstrip("-* "), "owner": owner})
        elif stripped.startswith(("-", "*")) and any(w in stripped.lower() for w in ["will", "to ", "need", "@"]):
            text_part = stripped.lstrip("-* ").strip()
            owner = ""
            at_match = re.search(r'@(\w+)', text_part)
            if at_match:
                owner = at_match.group(1)
            items.append({"action": text_part, "owner": owner})
    return items

async def meeting_minutes(params: dict) -> dict:
    text = params.get("text", "").strip()
    if not text:
        return error_response("text is required")
    fmt = params.get("format", "structured")
    title = _extract_title(text)
    date_val = _extract_date(text)
    attendees = _extract_attendees(text)
    agenda = _extract_agenda(text)
    decisions = _extract_decisions(text)
    action_items = _extract_action_items(text)
    summary = {
        "title": title,
        "date": date_val,
        "attendees": attendees,
        "agenda": agenda,
        "decisions": decisions,
        "action_items": action_items,
        "next_steps": [a["action"] for a in action_items if a["action"]],
    }
    if fmt == "bullet":
        lines = [f"- {k}: {v}" if not isinstance(v, list) else f"- {k}: " + "; ".join(str(x) for x in v) for k, v in summary.items()]
        return success_response({"summary": summary, "formatted": "\n".join(lines)})
    elif fmt == "paragraph":
        para = f"{title} ({date_val}). "
        if attendees:
            para += f"Attendees: {', '.join(attendees)}. "
        para += f"Agenda: {'; '.join(agenda)}. "
        if decisions:
            para += f"Decisions: {'; '.join(decisions)}. "
        if action_items:
            para += f"Action items: {'; '.join(a['action'] for a in action_items)}."
        return success_response({"summary": summary, "formatted": para})
    return success_response({"summary": summary})

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest

    async def on_load(self):
        pass
