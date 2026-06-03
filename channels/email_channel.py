import os
import logging
import imaplib
import smtplib
import email
import email.header
import json
import re
from email.mime.text import MIMEText
from typing import List, Dict, Optional
from core.llm_router import complete

logger = logging.getLogger("jarvis.channels.email")

class EmailChannel:
    def __init__(self):
        self.host = os.getenv("EMAIL_HOST")
        self.port = int(os.getenv("EMAIL_PORT", 993))
        self.user = os.getenv("EMAIL_USER")
        self.password = os.getenv("EMAIL_PASS")
        self.use_ssl = os.getenv("EMAIL_USE_SSL", "true").lower() == "true"
        
        if not self.host:
            logger.warning("EMAIL_HOST not set. EmailChannel will operate in mock/no-op mode.")

    def _is_configured(self) -> bool:
        return bool(self.host and self.user and self.password)

    def fetch_inbox(self, limit: int = 20) -> List[Dict]:
        """Fetch UNSEEN and recent messages from the inbox."""
        if not self._is_configured():
            return []
            
        messages = []
        try:
            mail = imaplib.IMAP4_SSL(self.host, self.port) if self.use_ssl else imaplib.IMAP4(self.host, self.port)
            mail.login(self.user, self.password)
            mail.select("inbox")
            
            # Search for unseen messages first
            status, response = mail.search(None, "UNSEEN")
            ids = response[0].split()
            
            # If not enough unseen, fetch recent ones
            if len(ids) < limit:
                status, recent_response = mail.search(None, "ALL")
                all_ids = recent_response[0].split()
                # Get the last (limit - len(ids)) messages that are not already in ids
                recent_ids = [i for i in all_ids if i not in ids][- (limit - len(ids)):]
                ids.extend(recent_ids)
            
            # Limit to requested amount, latest first
            ids = ids[-limit:]
            ids.reverse()
            
            for msg_id in ids:
                status, data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue
                    
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                # Extract subject
                subject = str(email.header.make_header(email.header.decode_header(msg.get("Subject", "(No Subject)"))))
                sender = msg.get("From", "Unknown")
                date = msg.get("Date", "")
                
                # Extract body
                body_text = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_text = payload.decode(errors="replace")
                            break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode(errors="replace")
                
                snippet = body_text[:200].replace("\n", " ").strip()
                
                messages.append({
                    "id": msg_id.decode(),
                    "subject": subject,
                    "sender": sender,
                    "date": date,
                    "body_text": body_text,
                    "snippet": snippet
                })
                
            mail.logout()
        except Exception as e:
            logger.error(f"Failed to fetch inbox: {e}")
            
        return messages

    async def ai_triage(self, messages: List[Dict]) -> List[Dict]:
        """Classify emails using LLM."""
        if not messages:
            return []
            
        messages_slim = [
            {"id": m["id"], "subject": m["subject"], "snippet": m["snippet"]} 
            for m in messages
        ]
        
        prompt = (
            "Classify these emails. For each, return urgency (high/medium/low) and category "
            "(work/newsletter/personal/spam) and a 1-sentence summary.\n"
            f"Input: {json.dumps(messages_slim)}\n\n"
            "Return valid JSON array of objects with fields: id, urgency, category, summary."
        )
        
        try:
            response = await complete(prompt, group="analysis")
            # Parse JSON safely
            json_block = re.search(r'\[.*\]', response, re.DOTALL)
            if json_block:
                triaged_data = json.loads(json_block.group())
            else:
                triaged_data = json.loads(response)
                
            # Map back to original messages
            triage_map = {str(item["id"]): item for item in triaged_data if "id" in item}
            
            for m in messages:
                t = triage_map.get(str(m["id"]), {})
                m["urgency"] = t.get("urgency", "medium")
                m["category"] = t.get("category", "personal")
                m["summary"] = t.get("summary", "No summary available.")
                
        except Exception as e:
            logger.warning(f"AI triage failed: {e}. Falling back to defaults.")
            for m in messages:
                m["urgency"] = "medium"
                m["category"] = "personal"
                m["summary"] = m["snippet"]
                
        return messages

    async def draft_reply(self, message: Dict, instruction: str) -> str:
        """Generate a draft reply using LLM."""
        prompt = (
            f"Write a draft reply to this email.\n"
            f"Original Email from {message.get('sender', 'Unknown')}:\n"
            f"Subject: {message.get('subject', 'No Subject')}\n"
            f"Body: {message.get('body_text', '')}\n\n"
            f"Instruction for reply: {instruction}\n\n"
            "Return only the draft text."
        )
        
        try:
            draft = await complete(prompt, group="analysis")
            return draft.strip()
        except Exception as e:
            logger.error(f"Failed to draft reply: {e}")
            return "Error generating draft."

    def send_email(self, to: str, subject: str, body: str) -> bool:
        """Send an email using SMTP."""
        if not self._is_configured():
            logger.error("Email not configured. Cannot send.")
            return False
            
        try:
            smtp_host = os.getenv("SMTP_HOST", self.host.replace("imap", "smtp") if self.host and "imap" in self.host else self.host)
            smtp_port = int(os.getenv("SMTP_PORT", 465 if self.use_ssl else 587))
            
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = self.user
            msg["To"] = to
            
            if self.use_ssl:
                with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                    server.login(self.user, self.password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    server.login(self.user, self.password)
                    server.send_message(msg)
            
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
