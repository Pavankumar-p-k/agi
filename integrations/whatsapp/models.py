from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VOICE = "voice"
    VIDEO = "video"
    DOCUMENT = "document"
    LOCATION = "location"
    CONTACTS = "contacts"
    INTERACTIVE = "interactive"
    BUTTON = "button"
    ORDER = "order"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class MessageDirection(Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    PENDING = "pending"


@dataclass
class WhatsAppMedia:
    id: str
    mime_type: str
    sha256: str
    file_size: int
    filename: str | None = None
    caption: str | None = None
    local_path: str | None = None

    @classmethod
    def from_api(cls, data: dict, media_type: str) -> WhatsAppMedia:
        return cls(
            id=data.get("id", ""),
            mime_type=data.get("mime_type", data.get("mimetype", "")),
            sha256=data.get("sha256", ""),
            file_size=int(data.get("file_size", 0)),
            filename=data.get("filename", f"{media_type}_{data.get('id', 'unknown')}"),
            caption=data.get("caption"),
        )


@dataclass
class WhatsAppLocation:
    latitude: float
    longitude: float
    name: str | None = None
    address: str | None = None


@dataclass
class WhatsAppContact:
    name: str
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    birthday: str | None = None


@dataclass
class WhatsAppMessage:
    id: str
    type: MessageType
    direction: MessageDirection
    from_number: str
    to_number: str
    timestamp: datetime | None = None
    text: str | None = None
    media: WhatsAppMedia | None = None
    location: WhatsAppLocation | None = None
    contacts: list[WhatsAppContact] = field(default_factory=list)
    context_message_id: str | None = None
    status: MessageStatus = MessageStatus.PENDING
    statuses: list[dict] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_webhook_payload(cls, payload: dict, business_phone: str) -> WhatsAppMessage:
        msg = payload.get("message", payload)
        msg_type = msg.get("type", "unknown")
        type_map = {
            "text": MessageType.TEXT,
            "image": MessageType.IMAGE,
            "audio": MessageType.AUDIO,
            "voice": MessageType.VOICE,
            "video": MessageType.VIDEO,
            "document": MessageType.DOCUMENT,
            "location": MessageType.LOCATION,
            "contacts": MessageType.CONTACTS,
            "interactive": MessageType.INTERACTIVE,
            "button": MessageType.BUTTON,
            "order": MessageType.ORDER,
            "system": MessageType.SYSTEM,
        }
        mtype = type_map.get(msg_type, MessageType.UNKNOWN)
        message_id = msg.get("id", "")
        from_number = payload.get("from", msg.get("from", ""))
        ts = msg.get("timestamp")
        parsed_ts = None
        if ts:
            try:
                parsed_ts = datetime.fromtimestamp(int(ts))
            except (ValueError, OSError):
                pass

        text = None
        if mtype == MessageType.TEXT:
            text = msg.get("text", {}).get("body", "")
        elif mtype == MessageType.INTERACTIVE:
            interactive = msg.get("interactive", {})
            if interactive.get("type") == "button_reply":
                text = interactive.get("button_reply", {}).get("title", "")
            elif interactive.get("type") == "list_reply":
                text = interactive.get("list_reply", {}).get("title", "")

        media = None
        if mtype in (MessageType.IMAGE, MessageType.AUDIO, MessageType.VOICE, MessageType.VIDEO, MessageType.DOCUMENT):
            media_data = msg.get(msg_type, {})
            if media_data:
                media = WhatsAppMedia.from_api(media_data, msg_type)

        location = None
        if mtype == MessageType.LOCATION:
            loc_data = msg.get("location", {})
            if loc_data:
                location = WhatsAppLocation(
                    latitude=loc_data.get("latitude", 0.0),
                    longitude=loc_data.get("longitude", 0.0),
                    name=loc_data.get("name"),
                    address=loc_data.get("address"),
                )

        contacts_list = []
        if mtype == MessageType.CONTACTS:
            for c in msg.get("contacts", []):
                name_data = c.get("name", {})
                formatted_name = name_data.get("formatted_name", "")
                phones = [p.get("phone", "") for p in c.get("phones", [])]
                emails = [e.get("email", "") for e in c.get("emails", [])]
                contacts_list.append(WhatsAppContact(name=formatted_name, phones=phones, emails=emails))

        context_id = None
        context = msg.get("context", {})
        if context:
            context_id = context.get("id")

        return cls(
            id=message_id,
            type=mtype,
            direction=MessageDirection.INBOUND,
            from_number=from_number,
            to_number=business_phone,
            timestamp=parsed_ts,
            text=text,
            media=media,
            location=location,
            contacts=contacts_list,
            context_message_id=context_id,
            raw=payload,
        )

    @classmethod
    def from_status_payload(cls, payload: dict) -> WhatsAppMessage:
        status = payload.get("status", {})
        statuses = status.get("statuses", [payload])
        msg = statuses[0]
        return cls(
            id=msg.get("id", ""),
            type=MessageType.SYSTEM,
            direction=MessageDirection.OUTBOUND,
            from_number=msg.get("recipient_id", ""),
            to_number="",
            status=MessageStatus(msg.get("status", "pending")),
            statuses=statuses,
            raw=payload,
        )


@dataclass
class InteractiveButton:
    id: str
    title: str


@dataclass
class InteractiveListRow:
    id: str
    title: str
    description: str | None = None


@dataclass
class InteractiveListSection:
    title: str
    rows: list[InteractiveListRow]


@dataclass
class InteractiveAction:
    button: str
    buttons: list[InteractiveButton] | None = None
    sections: list[InteractiveListSection] | None = None


@dataclass
class InteractiveBody:
    text: str
    title: str | None = None
    footer: str | None = None
    action: InteractiveAction | None = None


@dataclass
class SendResult:
    success: bool
    message_id: str | None = None
    error: str | None = None
    retry_attempts: int = 0
    provider: str = ""


class ProviderType(Enum):
    CLOUD_API = "cloud_api"
    TWILIO = "twilio"
