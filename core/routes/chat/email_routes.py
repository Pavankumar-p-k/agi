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
import os

from fastapi import APIRouter, HTTPException

from channels.email_channel import EmailChannel

router = APIRouter(prefix="/email", tags=["email"])

@router.get("/status")
async def email_status():
    """Return email configuration status."""
    return {
        "configured": bool(os.getenv("EMAIL_HOST")),
        "host": os.getenv("EMAIL_HOST"),
        "user": os.getenv("EMAIL_USER")
    }

@router.get("/inbox")
async def get_inbox(limit: int = 20):
    """Fetch and triage inbox messages."""
    ch = EmailChannel()
    messages = ch.fetch_inbox(limit=limit)
    if messages:
        triaged = await ch.ai_triage(messages)
    else:
        triaged = []
    return {"messages": triaged, "count": len(triaged)}

@router.post("/draft")
async def draft_reply(body: dict):
    """Generate a draft reply for a message."""
    message = body.get("message")
    instruction = body.get("instruction", "Reply professionally")
    if not message:
        raise HTTPException(400, "message object required")

    ch = EmailChannel()
    draft = await ch.draft_reply(message, instruction)
    return {"draft": draft}

@router.post("/send")
async def send_email(body: dict):
    """Send an email."""
    to = body.get("to")
    subject = body.get("subject")
    body_text = body.get("body")

    if not all([to, subject, body_text]):
        raise HTTPException(400, "to, subject, and body are required")

    ch = EmailChannel()
    success = ch.send_email(to, subject, body_text)
    return {"sent": success}
