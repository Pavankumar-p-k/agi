import re

from skills.utils import success_response, error_response

def _parse_email_thread(text):
    messages = []
    blocks = re.split(r"\n(?=From:|On \w+ \d|>?-{2,}Original)", text.strip(), flags=re.MULTILINE | re.IGNORECASE)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        sender = ""
        subject = ""
        m = re.search(r"From:\s*(.*?)(?:\n|$)", block, re.IGNORECASE)
        if m:
            sender = m.group(1).strip()
        m = re.search(r"Subject:\s*(.*?)(?:\n|$)", block, re.IGNORECASE)
        if m:
            subject = m.group(1).strip()
        body_lines = []
        in_body = False
        for line in block.split("\n"):
            if line.strip().startswith("Subject:") or re.match(r"^\s*(On\s+\w+|From:)", line):
                continue
            if not in_body and sender and line.strip().lower().startswith("to:"):
                in_body = True
                continue
            if in_body or (not line.startswith(">") and sender):
                cleaned = line.strip().lstrip(">").strip()
                if cleaned:
                    body_lines.append(cleaned)
        if not body_lines:
            body_lines = [line.strip() for line in block.split("\n") if line.strip() and not line.startswith(("From:", "Subject:", "Date:", "To:"))]
        body = " ".join(body_lines) if body_lines else block[:200]
        messages.append({
            "sender": sender or "Unknown",
            "subject": subject or "No subject",
            "body": body,
        })
    return messages

def _extract_actions(text):
    actions = []
    patterns = [
        r"(?:I will|I\'ll|I need to|will|need to|please)\s+(.+?)[\.!\n]",
        r"(?:action item|todo|to do|next step)[:\s]+(.+?)[\n\.]",
        r"@(\w+)\s+(.+?)[\n\.]",
    ]
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            actions.append(m.group(0).strip().rstrip("."))
    return actions

def _extract_decisions(text):
    decisions = []
    for m in re.finditer(r"(?:decided|agreed|concluded|consensus|resolution)[:\s]+(.+?)[\.!\n]", text, re.IGNORECASE):
        decisions.append(m.group(1).strip())
    return decisions

async def email_summarizer(params: dict) -> dict:
    text = params.get("text", "").strip()
    if not text:
        return error_response("text is required")
    max_bullets = int(params.get("max_bullets", 5))
    include_actions = params.get("include_actions", True)

    messages = _parse_email_thread(text)
    if not messages:
        return error_response("Could not parse email thread")

    summary = {
        "thread_summary": f"Email thread with {len(messages)} messages",
        "messages": [],
        "key_points": [],
        "action_items": [],
        "decisions": [],
    }

    all_text = text
    for msg in messages:
        entry = {
            "sender": msg["sender"],
            "subject": msg["subject"],
        }
        points = [s.strip() for s in re.split(r'[.!?]\s+', msg["body"]) if len(s.strip()) > 20]
        entry["key_points"] = points[:max_bullets]
        summary["messages"].append(entry)

    all_text_lower = all_text.lower()
    key_point_candidates = []
    for msg in messages:
        for pt in re.split(r'[.!?]\s+', msg["body"]):
            pt = pt.strip()
            if len(pt) > 30 and pt not in key_point_candidates:
                key_point_candidates.append(pt)

    summary["key_points"] = key_point_candidates[:max_bullets]

    if include_actions:
        summary["action_items"] = _extract_actions(all_text)
        summary["decisions"] = _extract_decisions(all_text)

    return success_response(summary)

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest

    async def on_load(self):
        pass
