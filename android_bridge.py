from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx


class AndroidBridge:
    """
    Bridge for device actions triggered by backend endpoints.

    Modes:
    - mock: simulate success (default)
    - adb: use local adb commands
    - device_api: forward to a companion API running on phone
    """

    def __init__(self):
        self.mode = os.getenv("JARVIS_BRIDGE_MODE", "mock").strip().lower()
        self.serial = os.getenv("ANDROID_SERIAL", "").strip()
        self.device_api = os.getenv("ANDROID_DEVICE_API", "").strip().rstrip("/")
        self.auto_tap_send = os.getenv("JARVIS_ADB_AUTO_TAP_SEND", "0").strip() == "1"
        self.bridge_token = os.getenv("JARVIS_BRIDGE_TOKEN", "").strip()

    def config(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "serial": self.serial,
            "device_api": self.device_api,
            "auto_tap_send": self.auto_tap_send,
            "token_configured": bool(self.bridge_token),
        }

    async def send_message(self, contact: str, text: str, platform: str = "auto") -> dict[str, Any]:
        contact = (contact or "").strip()
        text = (text or "").strip()
        if not contact or not text:
            return {"success": False, "error": "missing_contact_or_text"}

        if self.mode == "mock":
            return {"success": True, "mode": "mock", "contact": contact, "platform": platform}

        if self.mode == "device_api" and self.device_api:
            return await self._post_device_api(
                "/bridge/messages/send",
                {"contact": contact, "text": text, "platform": platform},
            )

        if self.mode == "adb":
            return await self._send_message_via_adb(contact=contact, text=text)

        return {"success": False, "error": f"unsupported_mode:{self.mode}"}

    async def speak(self, text: str) -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"success": False, "error": "missing_text"}

        if self.mode == "mock":
            return {"success": True, "mode": "mock"}

        if self.mode == "device_api" and self.device_api:
            return await self._post_device_api("/bridge/tts", {"text": text})

        if self.mode == "adb":
            # Broadcast for optional Android receiver/service support.
            ok, out = await self._adb(
                "shell",
                "am",
                "broadcast",
                "-a",
                "com.jarvis.TTS",
                "--es",
                "text",
                text,
            )
            if ok:
                return {"success": True, "mode": "adb", "output": out}
            return {"success": False, "mode": "adb", "error": out}

        return {"success": False, "error": f"unsupported_mode:{self.mode}"}

    async def answer_call_with_tts(self, caller: str, script: str) -> dict[str, Any]:
        caller = (caller or "").strip()
        script = (script or "").strip()
        if not script:
            return {"success": False, "error": "missing_script"}

        if self.mode == "mock":
            return {"success": True, "mode": "mock", "caller": caller}

        if self.mode == "device_api" and self.device_api:
            return await self._post_device_api(
                "/bridge/calls/answer_tts",
                {"caller": caller, "script": script},
            )

        if self.mode == "adb":
            return await self._answer_call_via_adb(caller=caller, script=script)

        return {"success": False, "error": f"unsupported_mode:{self.mode}"}

    async def _post_device_api(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.device_api}{path}"
        headers = {}
        if self.bridge_token:
            headers["X-Bridge-Token"] = self.bridge_token
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code >= 400:
                    return {"success": False, "error": res.text, "status": res.status_code}
                data = res.json() if res.text.strip() else {}
                if isinstance(data, dict):
                    data.setdefault("success", True)
                    data.setdefault("mode", "device_api")
                    return data
                return {"success": True, "mode": "device_api", "data": data}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _adb(self, *args: str) -> tuple[bool, str]:
        cmd = ["adb"]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(args)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out_b, err_b = await proc.communicate()
            output = (out_b or b"").decode(errors="ignore").strip()
            error = (err_b or b"").decode(errors="ignore").strip()
            if proc.returncode == 0:
                return True, output or "ok"
            return False, error or output or f"adb_exit_{proc.returncode}"
        except Exception as exc:
            return False, str(exc)

    async def _send_message_via_adb(self, contact: str, text: str) -> dict[str, Any]:
        ok, out = await self._adb(
            "shell",
            "am",
            "start",
            "-a",
            "android.intent.action.SENDTO",
            "-d",
            f"sms:{contact}",
            "--es",
            "sms_body",
            text,
            "--ez",
            "exit_on_sent",
            "true",
        )
        if not ok:
            # Fallback path for custom app receiver integration.
            ok_b, out_b = await self._adb(
                "shell",
                "am",
                "broadcast",
                "-a",
                "com.jarvis.SEND_MESSAGE",
                "--es",
                "contact",
                contact,
                "--es",
                "text",
                text,
                "--es",
                "platform",
                "sms",
            )
            if not ok_b:
                return {"success": False, "mode": "adb", "error": out}
            return {"success": True, "mode": "adb", "output": out_b, "strategy": "broadcast_fallback"}

        if self.auto_tap_send:
            await asyncio.sleep(1.0)
            # Device specific fallback tap sequence for send button.
            await self._adb("shell", "input", "keyevent", "22")
            ok2, out2 = await self._adb("shell", "input", "keyevent", "66")
            if not ok2:
                return {"success": False, "mode": "adb", "error": out2}

        return {"success": True, "mode": "adb", "output": out}

    async def _answer_call_via_adb(self, caller: str, script: str) -> dict[str, Any]:
        # Requires companion Android receiver/service to handle this broadcast.
        ok, out = await self._adb(
            "shell",
            "am",
            "broadcast",
            "-a",
            "com.jarvis.ANSWER_CALL_TTS",
            "--es",
            "caller",
            caller,
            "--es",
            "script",
            script,
        )
        if not ok:
            return {"success": False, "mode": "adb", "error": out}
        return {"success": True, "mode": "adb", "output": out}
