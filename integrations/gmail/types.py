"""integrations/gmail/types.py — Data models for Gmail API responses."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class GmailMessage:
    id: str
    thread_id: str
    subject: str
    sender: str
    recipients: list[str]
    date: datetime
    snippet: str
    body_text: str = ""
    body_html: str = ""
    unread: bool = True
    labels: list[str] = field(default_factory=list)
    attachments: list[GmailAttachment] = field(default_factory=list)


@dataclass
class GmailAttachment:
    attachment_id: str
    message_id: str
    filename: str
    mime_type: str
    size: int
    data: bytes | None = None


@dataclass
class GmailLabel:
    id: str
    name: str
    type: str = "user"
    message_list_visibility: str = "show"
    label_list_visibility: str = "labelShow"
    messages_total: int = 0
    messages_unread: int = 0
    threads_total: int = 0
    threads_unread: int = 0


@dataclass
class GmailThread:
    id: str
    messages: list[GmailMessage] = field(default_factory=list)
    snippet: str = ""
    history_id: str = ""


@dataclass
class GmailProfile:
    email: str
    messages_total: int
    threads_total: int
    history_id: str


def message_from_api(msg: dict) -> GmailMessage:
    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    parts = msg["payload"].get("parts", [])
    body_text, body_html = _extract_body(msg["payload"])

    from datetime import timezone
    date_str = headers.get("date", "")
    try:
        from email.utils import parsedate_to_datetime
        date = parsedate_to_datetime(date_str)
    except Exception:
        date = datetime.now(timezone.utc)

    raw_recipients = headers.get("to", "")
    recipients = [r.strip() for r in raw_recipients.split(",") if r.strip()]

    label_ids = msg.get("labelIds", [])
    unread = "UNREAD" in label_ids

    attachments = _extract_attachments(msg["payload"], msg["id"])

    return GmailMessage(
        id=msg["id"],
        thread_id=msg.get("threadId", ""),
        subject=headers.get("subject", "(no subject)"),
        sender=headers.get("from", "unknown"),
        recipients=recipients,
        date=date,
        snippet=msg.get("snippet", ""),
        body_text=body_text,
        body_html=body_html,
        unread=unread,
        labels=label_ids,
        attachments=attachments,
    )


def _extract_body(payload: dict) -> tuple[str, str]:
    body_text = ""
    body_html = ""
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        body_text = _decode_data(payload.get("body", {}).get("data", ""))
    elif mime_type == "text/html":
        body_html = _decode_data(payload.get("body", {}).get("data", ""))
    elif mime_type == "multipart/alternative" or "multipart" in mime_type:
        for part in payload.get("parts", []):
            t, h = _extract_body(part)
            if t:
                body_text = t
            if h:
                body_html = h
    elif payload.get("parts"):
        for part in payload.get("parts", []):
            t, h = _extract_body(part)
            if t:
                body_text = t
            if h:
                body_html = h

    return body_text, body_html


def _extract_attachments(payload: dict, msg_id: str) -> list[GmailAttachment]:
    attachments: list[GmailAttachment] = []
    if payload.get("filename") and payload.get("body", {}).get("attachmentId"):
        attachments.append(GmailAttachment(
            attachment_id=payload["body"]["attachmentId"],
            message_id=msg_id,
            filename=payload["filename"],
            mime_type=payload.get("mimeType", "application/octet-stream"),
            size=payload["body"].get("size", 0),
        ))
    for part in payload.get("parts", []):
        attachments.extend(_extract_attachments(part, msg_id))
    return attachments


def _decode_data(data_b64: str) -> str:
    import base64
    try:
        decoded = base64.urlsafe_b64decode(data_b64)
        return decoded.decode("utf-8", errors="replace")
    except Exception:
        return ""


def label_from_api(label: dict) -> GmailLabel:
    return GmailLabel(
        id=label["id"],
        name=label["name"],
        type=label.get("type", "user"),
        message_list_visibility=label.get("messageListVisibility", "show"),
        label_list_visibility=label.get("labelListVisibility", "labelShow"),
        messages_total=label.get("messagesTotal", 0),
        messages_unread=label.get("messagesUnread", 0),
        threads_total=label.get("threadsTotal", 0),
        threads_unread=label.get("threadsUnread", 0),
    )


def thread_from_api(thread: dict) -> GmailThread:
    msgs = [message_from_api(m) for m in thread.get("messages", [])]
    return GmailThread(
        id=thread["id"],
        messages=msgs,
        snippet=thread.get("snippet", ""),
        history_id=thread.get("historyId", ""),
    )
