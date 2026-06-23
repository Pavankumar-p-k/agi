"""core/routes/terminal.py — Real-time terminal WebSocket for Web UI."""
import asyncio
import json
import logging
import os
import subprocess

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("jarvis.terminal")
router = APIRouter(tags=["Terminal"])

@router.websocket("/ws/terminal")
async def terminal_websocket(ws: WebSocket):
    await ws.accept()
    process = None
    
    try:
        # On Windows, we'll use powershell. On others, bash.
        shell = "powershell.exe" if os.name == "nt" else "bash"
        
        # Start a persistent shell process
        process = await asyncio.create_subprocess_exec(
            shell,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.getcwd(),
        )

        async def read_stream(stream, stream_type):
            while True:
                line = await stream.read(4096)
                if not line:
                    break
                await ws.send_json({
                    "type": "output",
                    "stream": stream_type,
                    "data": line.decode(errors="replace")
                })

        # Run stream readers in background
        stdout_task = asyncio.create_task(read_stream(process.stdout, "stdout"))
        stderr_task = asyncio.create_task(read_stream(process.stderr, "stderr"))

        while True:
            # Wait for command from frontend
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "command":
                cmd = msg.get("data", "")
                if cmd:
                    process.stdin.write((cmd + "\n").encode())
                    await process.stdin.drain()
            elif msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("Terminal WebSocket disconnected")
    except Exception as e:
        logger.error(f"Terminal error: {e}")
    finally:
        if process:
            try:
                process.terminate()
            except:
                pass
        if 'stdout_task' in locals(): stdout_task.cancel()
        if 'stderr_task' in locals(): stderr_task.cancel()
