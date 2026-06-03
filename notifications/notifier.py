"""notifications/notifier.py
Status broadcasting for SupervisorAgent — push notifications,
email digests, WebSocket updates.
"""
import os, smtplib, json, logging, asyncio
from pathlib import Path
from datetime import datetime
from email.message import EmailMessage
from typing import Optional

logger = logging.getLogger("notifier")

PROJECTS_DIR = Path.home() / ".jarvis" / "projects"

class SupervisorNotifier:
    def __init__(self):
        self.ws_clients: list = []
        self._email_enabled = bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("NOTIFY_EMAIL"))
        self._push_enabled = bool(os.getenv("PUSHOVER_USER") or os.getenv("NTFY_TOPIC"))

    async def notify(self, project: str, event: str, data: dict):
        tasks = []
        tasks.append(self._write_event_log(project, event, data))
        if self._email_enabled and event in ("build_completed", "task_failed"):
            tasks.append(self._send_email(project, event, data))
        if self._push_enabled and event in ("build_completed", "build_started", "task_failed"):
            tasks.append(self._send_push(project, event, data))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _write_event_log(self, project: str, event: str, data: dict):
        log_dir = PROJECTS_DIR / project
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "events.jsonl"
        entry = {"timestamp": datetime.now().isoformat(), "event": event, "data": data}
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    async def _send_email(self, project: str, event: str, data: dict):
        try:
            host = os.getenv("SMTP_HOST", "smtp.gmail.com")
            port = int(os.getenv("SMTP_PORT", "587"))
            user = os.getenv("SMTP_USER", "")
            pwd = os.getenv("SMTP_PASS", "")
            to = os.getenv("NOTIFY_EMAIL", "")

            msg = EmailMessage()
            msg["Subject"] = f"[JARVIS] {project}: {event}"
            msg["From"] = user
            msg["To"] = to
            body = f"Project: {project}\nEvent: {event}\nTime: {datetime.now().isoformat()}\n\n"
            for k, v in data.items():
                body += f"{k}: {v}\n"
            msg.set_content(body)

            with smtplib.SMTP(host, port, timeout=15) as s:
                s.starttls()
                s.login(user, pwd)
                s.send_message(msg)
            logger.info(f"[NOTIFIER] Email sent for {project}/{event}")
        except Exception as e:
            logger.warning(f"[NOTIFIER] Email failed: {e}")

    async def _send_push(self, project: str, event: str, data: dict):
        import httpx
        title = f"JARVIS: {project}"
        message = f"{event}: {data.get('status', '')} - {data.get('completed', 0)} tasks done"
        topic = os.getenv("NTFY_TOPIC", "")
        if topic:
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    await c.post(f"https://ntfy.sh/{topic}",
                                 content=message, headers={"Title": title, "Tags": "robot"})
                logger.info(f"[NOTIFIER] Push sent to ntfy.sh/{topic}")
            except Exception as e:
                logger.warning(f"[NOTIFIER] ntfy.sh push failed: {e}")

        pushover_user = os.getenv("PUSHOVER_USER", "")
        pushover_token = os.getenv("PUSHOVER_TOKEN", "")
        if pushover_user and pushover_token:
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    await c.post("https://api.pushover.net/1/messages.json", json={
                        "token": pushover_token, "user": pushover_user,
                        "title": title, "message": message
                    })
                logger.info(f"[NOTIFIER] Push sent to Pushover")
            except Exception as e:
                logger.warning(f"[NOTIFIER] Pushover failed: {e}")

    def register_ws(self, client):
        self.ws_clients.append(client)

    def unregister_ws(self, client):
        self.ws_clients = [c for c in self.ws_clients if c is not client]

notifier = SupervisorNotifier()
