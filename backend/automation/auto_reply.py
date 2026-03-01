from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROFILE_FILE = DATA_DIR / "auto_reply_profile.json"

DEFAULT_PROFILE: dict[str, Any] = {
    "persona_name": "Pavan",
    "style_prompt": (
        "Reply exactly like Pavan: short, natural, polite, practical, and human. "
        "Avoid robotic words. Keep it clear."
    ),
    "signature": "",
    "max_chars": 280,
}


class AutoReplyManager:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._profile: dict[str, Any] = dict(DEFAULT_PROFILE)
        self._load()

    def _load(self) -> None:
        if not PROFILE_FILE.exists():
            self._save()
            return
        try:
            raw = PROFILE_FILE.read_text(encoding="utf-8")
            if raw.strip():
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    self._profile = self._sanitize_profile(payload)
        except Exception:
            self._profile = dict(DEFAULT_PROFILE)
            self._save()

    def _save(self) -> None:
        PROFILE_FILE.write_text(json.dumps(self._profile, indent=2), encoding="utf-8")

    def _sanitize_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        base = dict(DEFAULT_PROFILE)
        persona_name = str(payload.get("persona_name", base["persona_name"])).strip()
        style_prompt = str(payload.get("style_prompt", base["style_prompt"])).strip()
        signature = str(payload.get("signature", base["signature"])).strip()
        max_chars_raw = payload.get("max_chars", base["max_chars"])
        try:
            max_chars = int(max_chars_raw)
        except Exception:
            max_chars = int(base["max_chars"])
        max_chars = min(1200, max(40, max_chars))
        return {
            "persona_name": persona_name or base["persona_name"],
            "style_prompt": style_prompt or base["style_prompt"],
            "signature": signature,
            "max_chars": max_chars,
        }

    def get_profile(self) -> dict[str, Any]:
        return dict(self._profile)

    def update_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        merged = dict(self._profile)
        merged.update(payload or {})
        self._profile = self._sanitize_profile(merged)
        self._save()
        return self.get_profile()

    def _fallback_reply(self, incoming_message: str, sender: str) -> str:
        sender_name = sender.strip() or "there"
        text = incoming_message.strip()
        if text.endswith("?"):
            return f"Hey {sender_name}, got your message. Yes, I will check and update you soon."
        return f"Hey {sender_name}, got it. I will take care of this and get back to you soon."

    def generate_reply(
        self,
        incoming_message: str,
        platform: str = "",
        sender: str = "",
        extra_context: str = "",
    ) -> dict[str, Any]:
        incoming = incoming_message.strip()
        if not incoming:
            return {"success": False, "error": "incoming_message is required"}

        profile = self.get_profile()
        max_chars = int(profile.get("max_chars", 280))
        persona_name = str(profile.get("persona_name", "Pavan")).strip() or "Pavan"
        style_prompt = str(profile.get("style_prompt", "")).strip()
        signature = str(profile.get("signature", "")).strip()
        platform_name = (platform or "").strip().lower() or "message"
        sender_name = sender.strip() or "unknown"

        llm_reply = ""
        llm_error = ""
        try:
            from assistant.engine import jarvis

            prompt_context = (
                f"You are writing as {persona_name}. "
                f"Platform: {platform_name}. "
                f"Sender: {sender_name}. "
                f"Style rules: {style_prompt}. "
                f"Keep response under {max_chars} characters. "
                "Output only the final reply text."
            )
            user_prompt = (
                f"Incoming message: {incoming}\n"
                f"Additional context: {extra_context.strip()}\n"
                "Write the reply now."
            )
            llm_reply = jarvis.llm.chat(user_prompt, context=prompt_context).strip()
        except Exception as exc:
            llm_error = str(exc)

        reply = llm_reply or self._fallback_reply(incoming, sender_name)
        if signature and signature.lower() not in reply.lower():
            reply = f"{reply}\n\n{signature}".strip()
        if len(reply) > max_chars:
            reply = reply[:max_chars].rstrip()

        return {
            "success": True,
            "platform": platform_name,
            "sender": sender_name,
            "incoming_message": incoming,
            "reply": reply,
            "profile": profile,
            "llm_error": llm_error,
        }


auto_reply_manager = AutoReplyManager()
