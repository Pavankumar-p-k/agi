"""core/supabase_gateway.py
Supabase bridge — polls for pending mobile messages, processes them through JARVIS,
handles goals/plans/progress, and can find + upload files to Supabase Storage.
"""

import os
import json
import asyncio
import httpx
import logging
from datetime import datetime, timezone

logger = logging.getLogger("supabase_gateway")


class SupabaseGateway:
    def __init__(self, supabase_url: str, service_key: str):
        self.url = supabase_url
        self.key = service_key
        self._client = None
        self._task = None
        self._running = False
        self._process_fn = None
        self._goal_fn = None
        self._plan_status_fn = None

    async def _get_client(self):
        if self._client is None:
            from supabase import create_client
            self._client = create_client(self.url, self.key)
        return self._client

    async def start(self, process_fn, goal_fn=None, plan_status_fn=None):
        self._process_fn = process_fn
        self._goal_fn = goal_fn
        self._plan_status_fn = plan_status_fn
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("[SUPABASE] Gateway started — polling for messages every 2s")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("[SUPABASE] Gateway stopped")

    async def _poll_loop(self):
        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[SUPABASE] Poll error: {e}")
            await asyncio.sleep(2)

    async def _poll_once(self):
        client = await self._get_client()
        result = client.table("messages") \
            .select("*") \
            .eq("role", "user") \
            .eq("status", "pending") \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()

        rows = result.data
        if not rows:
            return

        msg = rows[0]
        msg_id = msg["id"]
        user_id = msg.get("user_id", "default")
        content = msg.get("content", "")
        intent = msg.get("intent", "chat")

        client.table("messages").update({"status": "processing", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", msg_id).execute()

        try:
            # Route by intent
            if intent == "goal" and self._goal_fn:
                response_data = await self._goal_fn(content, user_id)
            elif intent == "plan_status" and self._plan_status_fn:
                response_data = await self._plan_status_fn(content, user_id)
            else:
                response_data = await self._process_fn(content, user_id)

            if isinstance(response_data, str):
                response_text = response_data
                file_metadata = None
            else:
                response_text = response_data.get("text", "")
                file_metadata = response_data.get("file")
                plan_data = response_data.get("plan")
                progress_data = response_data.get("progress")

            insert_data = {
                "user_id": user_id,
                "role": "assistant",
                "content": response_text,
                "status": "completed",
                "intent": intent,
            }

            metadata = {}
            if file_metadata:
                metadata["file"] = file_metadata
            if plan_data:
                metadata["plan"] = plan_data
            if progress_data:
                metadata["progress"] = progress_data
            if metadata:
                insert_data["metadata"] = json.dumps(metadata)

            client.table("messages").insert(insert_data).execute()
            client.table("messages").update({
                "status": "completed",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", msg_id).execute()

        except Exception as e:
            logger.error(f"[SUPABASE] Processing failed: {e}")
            client.table("messages").update({
                "status": "error",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", msg_id).execute()

    # ── File upload helper ──────────────────────────────────────

    async def upload_file(self, local_path: str, user_id: str = "default") -> dict:
        """Upload a local file to Supabase Storage bucket 'jarvis-files'.
        Returns file metadata dict or None on failure.
        """
        if not os.path.isfile(local_path):
            return None

        filename = os.path.basename(local_path)
        storage_path = f"{user_id}/{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{filename}"
        file_size = os.path.getsize(local_path)

        headers = {
            "Authorization": f"Bearer {self.key}",
        }

        try:
            with open(local_path, "rb") as f:
                async with httpx.AsyncClient() as http:
                    resp = await http.post(
                        f"{self.url}/storage/v1/object/jarvis-files/{storage_path}",
                        headers=headers,
                        content=f.read(),
                    )

            if resp.status_code in (200, 201):
                public_url = f"{self.url}/storage/v1/object/public/jarvis-files/{storage_path}"
                return {
                    "name": filename,
                    "url": public_url,
                    "size": file_size,
                    "type": self._guess_mime(filename),
                }
            else:
                logger.warning(f"[SUPABASE] Upload failed: {resp.status_code} {resp.text}")
                return None
        except Exception as e:
            logger.warning(f"[SUPABASE] Upload error: {e}")
            return None

    @staticmethod
    def _guess_mime(filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp",
            ".svg": "image/svg+xml", ".pdf": "application/pdf",
            ".doc": "application/msword", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain", ".md": "text/markdown",
            ".zip": "application/zip", ".py": "text/x-python",
            ".js": "text/javascript", ".json": "application/json",
            ".csv": "text/csv", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        return mime_map.get(ext, "application/octet-stream")
