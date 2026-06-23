"""integrations/gmail/client.py — Production-grade Gmail API client.

Covers all 12 acceptance criteria:
1. OAuth2 authentication
2. Token refresh (in auth module)
3. Send email
4. Read inbox
5. Search emails
6. Read attachments (headers)
7. Download attachments (binary)
8. Label management (CRUD + list)
9. Thread support (list + get + modify)
10. Health checks (in auth module)
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from .auth import GmailAuth
from .types import (
    GmailAttachment,
    GmailLabel,
    GmailMessage,
    GmailProfile,
    GmailThread,
    label_from_api,
    message_from_api,
    thread_from_api,
)

logger = logging.getLogger(__name__)


class GmailClient:
    """High-level Gmail API client.

    All methods are sync (the underlying API is HTTP-based).
    For async callers, use asyncio.to_thread() or run_in_executor().
    """

    def __init__(self, auth: GmailAuth | None = None):
        self._auth = auth or GmailAuth()
        self._authenticated_once = False

    @property
    def service(self):
        return self._auth.service

    # ── Authentication ───────────────────────────────────────────────────────

    def authenticate(self, headless: bool = False) -> bool:
        ok = self._auth.authenticate(headless=headless)
        if ok:
            self._authenticated_once = True
        return ok

    def is_authenticated(self) -> bool:
        return self._auth.is_authenticated

    def health_check(self) -> dict[str, Any]:
        return self._auth.health_check()

    # ── Profile ──────────────────────────────────────────────────────────────

    def get_profile(self) -> GmailProfile | None:
        try:
            resp = self.service.users().getProfile(userId="me").execute()
            return GmailProfile(
                email=resp.get("emailAddress", ""),
                messages_total=resp.get("messagesTotal", 0),
                threads_total=resp.get("threadsTotal", 0),
                history_id=resp.get("historyId", ""),
            )
        except Exception as e:
            logger.error("[GmailClient] get_profile failed: %s", e)
            return None

    # ── Read Inbox ───────────────────────────────────────────────────────────

    def list_messages(
        self,
        query: str = "in:inbox",
        max_results: int = 20,
        label_ids: list[str] | None = None,
        include_spam_trash: bool = False,
    ) -> list[GmailMessage]:
        try:
            kwargs = dict(userId="me", q=query, maxResults=min(max_results, 500))
            if label_ids:
                kwargs["labelIds"] = label_ids
            if include_spam_trash:
                kwargs["includeSpamTrash"] = True

            resp = self.service.users().messages().list(**kwargs).execute()
            messages = resp.get("messages", [])
            return self._fetch_messages_detail(messages)
        except Exception as e:
            logger.error("[GmailClient] list_messages failed: %s", e)
            return []

    def get_message(self, msg_id: str, format: str = "full") -> GmailMessage | None:
        try:
            msg = self.service.users().messages().get(
                userId="me", id=msg_id, format=format
            ).execute()
            return message_from_api(msg)
        except Exception as e:
            logger.error("[GmailClient] get_message(%s) failed: %s", msg_id, e)
            return None

    def _fetch_messages_detail(
        self, messages: list[dict], batch_size: int = 50
    ) -> list[GmailMessage]:
        result: list[GmailMessage] = []
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i + batch_size]
            for msg_ref in batch:
                try:
                    msg = self.service.users().messages().get(
                        userId="me", id=msg_ref["id"], format="full"
                    ).execute()
                    result.append(message_from_api(msg))
                except Exception as e:
                    logger.warning("[GmailClient] fetch detail %s failed: %s",
                                   msg_ref["id"], e)
        return result

    def batch_get_messages(self, msg_ids: list[str]) -> list[GmailMessage]:
        return self._fetch_messages_detail([{"id": m} for m in msg_ids])

    # ── Send Email ───────────────────────────────────────────────────────────

    def send_message(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        body_type: str = "plain",
        attachments: list[dict] | None = None,
        thread_id: str | None = None,
    ) -> dict | None:
        try:
            msg = EmailMessage()
            if isinstance(to, str):
                to = [to]
            msg["To"] = ", ".join(to)
            msg["Subject"] = subject
            if cc:
                if isinstance(cc, str):
                    cc = [cc]
                msg["Cc"] = ", ".join(cc)
            if bcc:
                if isinstance(bcc, str):
                    bcc = [bcc]
                msg["Bcc"] = ", ".join(bcc)

            if body_type == "html":
                msg.set_content(
                    _strip_html(body), subtype="plain"
                )
                msg.add_alternative(body, subtype="html")
            else:
                msg.set_content(body)

            if attachments:
                self._attach_files(msg, attachments)

            encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            body = {"raw": encoded}
            if thread_id:
                body["threadId"] = thread_id

            sent = self.service.users().messages().send(
                userId="me", body=body
            ).execute()
            logger.info("[GmailClient] Sent message id=%s thread=%s",
                        sent.get("id"), sent.get("threadId"))
            return sent
        except Exception as e:
            logger.error("[GmailClient] send_message failed: %s", e)
            return None

    def _attach_files(self, msg: EmailMessage, attachments: list[dict]):
        import mimetypes
        for att in attachments:
            path = att.get("path", "")
            filename = att.get("filename", os.path.basename(path) if path else "attachment")
            data = att.get("data")
            mime_type = att.get("mime_type")
            if data is None and path:
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                except Exception as e:
                    logger.warning("[GmailClient] Cannot attach %s: %s", path, e)
                    continue
            if data is None:
                continue
            if not mime_type:
                mime_type, _ = mimetypes.guess_type(filename)
                mime_type = mime_type or "application/octet-stream"
            main_type, sub_type = mime_type.split("/", 1) if "/" in mime_type else ("application", "octet-stream")
            msg.add_attachment(data, maintype=main_type, subtype=sub_type, filename=filename)

    # ── Search Emails ────────────────────────────────────────────────────────

    def search_messages(
        self,
        query: str,
        max_results: int = 20,
    ) -> list[GmailMessage]:
        return self.list_messages(query=query, max_results=max_results)

    # ── Attachments ──────────────────────────────────────────────────────────

    def get_attachment(
        self, msg_id: str, attachment_id: str
    ) -> GmailAttachment | None:
        try:
            resp = self.service.users().messages().attachments().get(
                userId="me", messageId=msg_id, id=attachment_id
            ).execute()
            data = base64.urlsafe_b64decode(resp.get("data", ""))
            return GmailAttachment(
                attachment_id=attachment_id,
                message_id=msg_id,
                filename="",
                mime_type=resp.get("mimeType", "application/octet-stream"),
                size=resp.get("size", len(data)),
                data=data,
            )
        except Exception as e:
            logger.error("[GmailClient] get_attachment(%s/%s) failed: %s",
                         msg_id, attachment_id, e)
            return None

    def download_attachment(
        self,
        msg_id: str,
        attachment_id: str,
        save_dir: str | Path,
        filename: str | None = None,
    ) -> Path | None:
        att = self.get_attachment(msg_id, attachment_id)
        if att is None or att.data is None:
            return None
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        fname = filename or att.filename or f"{attachment_id}"
        file_path = save_path / fname
        file_path.write_bytes(att.data)
        logger.info("[GmailClient] Downloaded %s to %s (%d bytes)",
                    fname, file_path, len(att.data))
        return file_path

    # ── Label Management ─────────────────────────────────────────────────────

    def list_labels(self) -> list[GmailLabel]:
        try:
            resp = self.service.users().labels().list(userId="me").execute()
            return [label_from_api(l) for l in resp.get("labels", [])]
        except Exception as e:
            logger.error("[GmailClient] list_labels failed: %s", e)
            return []

    def get_label(self, label_id: str) -> GmailLabel | None:
        try:
            resp = self.service.users().labels().get(
                userId="me", id=label_id
            ).execute()
            return label_from_api(resp)
        except Exception as e:
            logger.error("[GmailClient] get_label(%s) failed: %s", label_id, e)
            return None

    def create_label(
        self,
        name: str,
        message_list_visibility: str = "show",
        label_list_visibility: str = "labelShow",
    ) -> GmailLabel | None:
        try:
            body = {
                "name": name,
                "messageListVisibility": message_list_visibility,
                "labelListVisibility": label_list_visibility,
            }
            resp = self.service.users().labels().create(
                userId="me", body=body
            ).execute()
            logger.info("[GmailClient] Created label: %s (id=%s)", name, resp["id"])
            return label_from_api(resp)
        except Exception as e:
            logger.error("[GmailClient] create_label(%s) failed: %s", name, e)
            return None

    def update_label(self, label_id: str, **kwargs) -> GmailLabel | None:
        try:
            existing = self.get_label(label_id)
            if existing is None:
                return None
            body = {
                "name": kwargs.get("name", existing.name),
                "messageListVisibility": kwargs.get(
                    "message_list_visibility", existing.message_list_visibility
                ),
                "labelListVisibility": kwargs.get(
                    "label_list_visibility", existing.label_list_visibility
                ),
            }
            resp = self.service.users().labels().update(
                userId="me", id=label_id, body=body
            ).execute()
            return label_from_api(resp)
        except Exception as e:
            logger.error("[GmailClient] update_label(%s) failed: %s", label_id, e)
            return None

    def delete_label(self, label_id: str) -> bool:
        try:
            self.service.users().labels().delete(
                userId="me", id=label_id
            ).execute()
            logger.info("[GmailClient] Deleted label: %s", label_id)
            return True
        except Exception as e:
            logger.error("[GmailClient] delete_label(%s) failed: %s", label_id, e)
            return False

    # ── Modify Labels on Messages ────────────────────────────────────────────

    def modify_message_labels(
        self,
        msg_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> bool:
        try:
            body = {}
            if add_label_ids:
                body["addLabelIds"] = add_label_ids
            if remove_label_ids:
                body["removeLabelIds"] = remove_label_ids
            if not body:
                return False
            self.service.users().messages().modify(
                userId="me", id=msg_id, body=body
            ).execute()
            return True
        except Exception as e:
            logger.error("[GmailClient] modify_labels(%s) failed: %s", msg_id, e)
            return False

    def mark_as_read(self, msg_id: str) -> bool:
        return self.modify_message_labels(
            msg_id, remove_label_ids=["UNREAD"]
        )

    def mark_as_unread(self, msg_id: str) -> bool:
        return self.modify_message_labels(
            msg_id, add_label_ids=["UNREAD"]
        )

    def move_to_trash(self, msg_id: str) -> bool:
        try:
            self.service.users().messages().trash(
                userId="me", id=msg_id
            ).execute()
            return True
        except Exception as e:
            logger.error("[GmailClient] trash(%s) failed: %s", msg_id, e)
            return False

    def untrash(self, msg_id: str) -> bool:
        try:
            self.service.users().messages().untrash(
                userId="me", id=msg_id
            ).execute()
            return True
        except Exception as e:
            logger.error("[GmailClient] untrash(%s) failed: %s", msg_id, e)
            return False

    def batch_modify_labels(
        self,
        msg_ids: list[str],
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> bool:
        try:
            body = {"ids": msg_ids}
            if add_label_ids:
                body["addLabelIds"] = add_label_ids
            if remove_label_ids:
                body["removeLabelIds"] = remove_label_ids
            self.service.users().messages().batchModify(
                userId="me", body=body
            ).execute()
            return True
        except Exception as e:
            logger.error("[GmailClient] batch_modify failed: %s", e)
            return False

    # ── Thread Support ───────────────────────────────────────────────────────

    def list_threads(
        self,
        query: str = "in:inbox",
        max_results: int = 20,
        label_ids: list[str] | None = None,
    ) -> list[GmailThread]:
        try:
            kwargs = dict(userId="me", q=query, maxResults=min(max_results, 500))
            if label_ids:
                kwargs["labelIds"] = label_ids
            resp = self.service.users().threads().list(**kwargs).execute()
            threads_data = resp.get("threads", [])
            return self._fetch_threads_detail(threads_data)
        except Exception as e:
            logger.error("[GmailClient] list_threads failed: %s", e)
            return []

    def get_thread(self, thread_id: str) -> GmailThread | None:
        try:
            resp = self.service.users().threads().get(
                userId="me", id=thread_id, format="full"
            ).execute()
            return thread_from_api(resp)
        except Exception as e:
            logger.error("[GmailClient] get_thread(%s) failed: %s", thread_id, e)
            return None

    def _fetch_threads_detail(
        self, threads: list[dict], batch_size: int = 50
    ) -> list[GmailThread]:
        result: list[GmailThread] = []
        for i in range(0, len(threads), batch_size):
            batch = threads[i:i + batch_size]
            for t in batch:
                try:
                    resp = self.service.users().threads().get(
                        userId="me", id=t["id"], format="full"
                    ).execute()
                    result.append(thread_from_api(resp))
                except Exception as e:
                    logger.warning("[GmailClient] thread %s detail failed: %s",
                                   t["id"], e)
        return result

    def modify_thread_labels(
        self,
        thread_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> bool:
        try:
            body = {}
            if add_label_ids:
                body["addLabelIds"] = add_label_ids
            if remove_label_ids:
                body["removeLabelIds"] = remove_label_ids
            if not body:
                return False
            self.service.users().threads().modify(
                userId="me", id=thread_id, body=body
            ).execute()
            return True
        except Exception as e:
            logger.error("[GmailClient] modify_thread(%s) failed: %s", thread_id, e)
            return False

    # ── Draft Support ────────────────────────────────────────────────────────

    def list_drafts(self, max_results: int = 20) -> list[dict]:
        try:
            resp = self.service.users().drafts().list(
                userId="me", maxResults=min(max_results, 500)
            ).execute()
            return resp.get("drafts", [])
        except Exception as e:
            logger.error("[GmailClient] list_drafts failed: %s", e)
            return []

    def get_draft(self, draft_id: str) -> dict | None:
        try:
            return self.service.users().drafts().get(
                userId="me", id=draft_id, format="full"
            ).execute()
        except Exception as e:
            logger.error("[GmailClient] get_draft(%s) failed: %s", draft_id, e)
            return None

    def create_draft(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        body_type: str = "plain",
    ) -> dict | None:
        try:
            msg = EmailMessage()
            if isinstance(to, str):
                to = [to]
            msg["To"] = ", ".join(to)
            msg["Subject"] = subject
            if cc:
                if isinstance(cc, str):
                    cc = [cc]
                msg["Cc"] = ", ".join(cc)
            if body_type == "html":
                msg.set_content(_strip_html(body), subtype="plain")
                msg.add_alternative(body, subtype="html")
            else:
                msg.set_content(body)
            encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            body_payload = {"raw": encoded}
            resp = self.service.users().drafts().create(
                userId="me", body={"message": body_payload}
            ).execute()
            return resp
        except Exception as e:
            logger.error("[GmailClient] create_draft failed: %s", e)
            return None

    def send_draft(self, draft_id: str) -> dict | None:
        try:
            resp = self.service.users().drafts().send(
                userId="me", body={"id": draft_id}
            ).execute()
            return resp
        except Exception as e:
            logger.error("[GmailClient] send_draft(%s) failed: %s", draft_id, e)
            return None

    def delete_draft(self, draft_id: str) -> bool:
        try:
            self.service.users().drafts().delete(
                userId="me", id=draft_id
            ).execute()
            return True
        except Exception as e:
            logger.error("[GmailClient] delete_draft(%s) failed: %s", draft_id, e)
            return False


def _strip_html(html: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", html).strip()
