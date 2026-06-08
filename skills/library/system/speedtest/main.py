import asyncio
import platform
import time
from skills.utils import success_response, error_response

PING_HOSTS = ["google.com", "cloudflare.com"]

async def _ping_host(host):
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", host]
    else:
        cmd = ["ping", "-c", "1", host]
    try:
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.DEVNULL, stderr=asyncio.DEVNULL)
        await proc.wait()
        elapsed = (time.monotonic() - start) * 1000
        if proc.returncode == 0:
            return {"host": host, "latency_ms": round(elapsed, 1), "alive": True}
        return {"host": host, "latency_ms": None, "alive": False}
    except Exception as e:
        return {"host": host, "latency_ms": None, "alive": False, "error": str(e)}

async def speedtest(params: dict) -> dict:
    action = params.get("action", "info")
    if action == "ping":
        results = await asyncio.gather(*[_ping_host(h) for h in PING_HOSTS])
        return success_response({"results": results})
    elif action == "info":
        uname = platform.uname()
        return success_response({
            "system": uname.system,
            "node": uname.node,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
            "processor": uname.processor,
        })
    elif action == "download-test":
        return success_response({
            "note": "Full speed test requires an external tool like speedtest-cli. Install with: pip install speedtest-cli",
            "suggestion": "Install speedtest-cli for actual bandwidth measurements",
        })
    else:
        return error_response(f"Unknown action '{action}'. Use ping/info/download-test.")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
