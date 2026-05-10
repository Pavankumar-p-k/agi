"""JARVIS OS API Server - Phase 7 Mythos Omega.

Enhanced with extensions, routes, links, and improved serving process.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from ..bootstrap import build_jarvis_os

# Global server reference for signal handling
_server_instance = None


def serve(host: str = "127.0.0.1", port: int = 8011, detached: bool = False) -> None:
    """Start the API server."""
    if detached:
        return _start_detached(host, port)

    return _start_server(host, port)


def _start_detached(host: str, port: int) -> Dict[str, Any]:
    """Start API server as a detached process."""
    # Create a script to run the server
    script_path = os.path.join(os.path.dirname(__file__), "_serve_daemon.py")

    # Write a simple daemon script
    daemon_dir = os.path.dirname(os.path.dirname(__file__))
    with open(script_path, "w") as f:
        f.write(f'''"""Auto-generated daemon script."""
import sys
sys.path.insert(0, r"{daemon_dir}")
from jarvis_os.interface.api_server import _start_server
_start_server("{host}", {port})
''')

    # Start as detached process
    try:
        pid = subprocess.Popen(
            [sys.executable, script_path, host, str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        ).pid

        return {
            "ok": True,
            "pid": pid,
            "host": host,
            "port": port,
            "url": f"http://{host}:{port}",
            "detached": True,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _start_server(host: str, port: int) -> None:
    """Start the server in the current process."""
    global _server_instance

    runtime = build_jarvis_os()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            """Suppress default logging."""
            return

        def _write(self, code: int, payload: dict) -> None:
            """Write JSON response."""
            data = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _write_html(self, html: str) -> None:
            """Write HTML response."""
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            """Handle GET requests."""
            path = self.path.split("?")[0]

            # Health check
            if path == "/health":
                self._write(200, {"ok": True, "version": "Phase 7 Mythos Omega"})
                return

            # Core endpoints
            if path == "/tools":
                self._write(200, {"tools": runtime.tools.catalog()})
                return
            if path == "/status":
                self._write(200, runtime.status())
                return
            if path == "/config":
                self._write(200, runtime.config_summary())
                return
            if path == "/monitor":
                self._write(200, runtime.monitor_summary())
                return
            if path == "/compat":
                self._write(200, runtime.compat_summary())
                return
            if path == "/agents":
                self._write(200, runtime.list_agents())
                return
            if path == "/jobs":
                self._write(200, runtime.list_jobs())
                return
            if path == "/skills":
                self._write(200, runtime.list_skills())
                return
            if path == "/plugins":
                self._write(200, runtime.list_plugins())
                return
            if path == "/schedules":
                self._write(200, runtime.list_schedules())
                return
            if path == "/telemetry":
                self._write(200, runtime.telemetry_summary())
                return
            if path == "/daemon":
                self._write(200, runtime.daemon_status())
                return
            if path == "/memory":
                self._write(200, {"memory": runtime.memory.recent()})
                return

            # Extension endpoints
            if path == "/extensions":
                self._write(200, {"extensions": runtime.list_extensions()})
                return
            if path.startswith("/extensions/"):
                ext_name = path.split("/", 2)[2]
                self._write(200, runtime.get_extension_info(ext_name))
                return

            # Route endpoints
            if path == "/routes":
                self._write(200, {"routes": runtime.list_routes()})
                return

            # Link endpoints
            if path == "/links":
                self._write(200, {"links": runtime.list_links()})
                return
            if path.startswith("/links/"):
                link_name = path.split("/", 2)[2]
                self._write(200, runtime.open_link(link_name))
                return

            # Resource endpoints
            if path.startswith("/jobs/"):
                self._write(200, runtime.get_job(path.split("/", 2)[2]))
                return
            if path.startswith("/agents/"):
                self._write(200, runtime.get_agent(path.split("/", 2)[2]))
                return
            if path.startswith("/skills/"):
                self._write(200, runtime.get_skill(path.split("/", 2)[2]))
                return
            if path.startswith("/plugins/"):
                self._write(200, runtime.get_plugin(path.split("/", 2)[2]))
                return

            # UI endpoint
            if path == "/" or path == "/ui":
                self._write_html(_generate_ui())
                return

            self._write(404, {"error": "not found", "path": path})

        def do_POST(self) -> None:
            """Handle POST requests."""
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")

            path = self.path.split("?")[0]

            # Prompt execution
            if path == "/run":
                result = runtime.handle_prompt(
                    payload.get("prompt", ""),
                    context=payload.get("context", {}),
                    agent_name=payload.get("agent_name", "auto"),
                )
                self._write(200, result)
                return

            if path == "/preview":
                result = runtime.preview_prompt(
                    payload.get("prompt", ""),
                    context=payload.get("context", {}),
                    agent_name=payload.get("agent_name", "auto"),
                )
                self._write(200, result)
                return

            if path == "/submit":
                result = runtime.submit_prompt(
                    payload.get("prompt", ""),
                    context=payload.get("context", {}),
                    agent_name=payload.get("agent_name", "auto"),
                )
                self._write(200, result)
                return

            # Job management
            if path.startswith("/jobs/") and path.endswith("/pause"):
                result = runtime.pause_job(path.split("/")[2])
                self._write(200, result)
                return
            if path.startswith("/jobs/") and path.endswith("/resume"):
                result = runtime.resume_job(path.split("/")[2])
                self._write(200, result)
                return

            # Skill execution
            if path == "/skills/run":
                result = runtime.run_skill(payload.get("name", ""))
                self._write(200, result)
                return

            # Plugin workflow
            if path == "/plugins/run-workflow":
                result = runtime.run_plugin_workflow(
                    payload.get("plugin", ""),
                    payload.get("workflow", ""),
                    payload.get("input", ""),
                )
                self._write(200, result)
                return

            # Schedules
            if path == "/schedules/run-due":
                result = runtime.run_due_schedules()
                self._write(200, result)
                return

            # Daemon control
            if path == "/daemon/start":
                result = runtime.daemon_start()
                self._write(200, result)
                return
            if path == "/daemon/stop":
                result = runtime.daemon_stop()
                self._write(200, result)
                return
            if path == "/daemon/tick":
                result = runtime.daemon_tick()
                self._write(200, result)
                return

            # Extension management
            if path == "/extensions/install":
                result = runtime.install_extension(payload.get("path", ""))
                self._write(200, result)
                return
            if path.startswith("/extensions/") and path.endswith("/enable"):
                ext_name = path.split("/")[2]
                result = runtime.enable_extension(ext_name)
                self._write(200, result)
                return
            if path.startswith("/extensions/") and path.endswith("/disable"):
                ext_name = path.split("/")[2]
                result = runtime.disable_extension(ext_name)
                self._write(200, result)
                return

            # Link management
            if path == "/links/add":
                result = runtime.add_link(payload.get("name", ""), payload.get("url", ""))
                self._write(200, result)
                return
            if path.startswith("/links/") and path.endswith("/remove"):
                link_name = path.split("/")[2]
                result = runtime.remove_link(link_name)
                self._write(200, result)
                return

            self._write(404, {"error": "not found", "path": path})

        def do_OPTIONS(self) -> None:
            """Handle CORS preflight."""
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

    # Start server
    server = ThreadingHTTPServer((host, port), Handler)
    _server_instance = server

    print(f"JARVIS OS API Server listening on http://{host}:{port}")
    print(f"UI available at http://{host}:{port}/ui")
    print("Press Ctrl+C to stop.")

    # Handle shutdown signals
    def _signal_handler(sig, frame):
        print("\nShutting down server...")
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


def _generate_ui() -> str:
    """Generate a simple HTML UI for the API."""
    return """<!DOCTYPE html>
<html>
<head>
    <title>JARVIS OS API</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        h1 { color: #333; }
        .endpoint { background: #f5f5f5; padding: 10px; margin: 5px 0; border-left: 3px solid #007bff; }
        .method { font-weight: bold; color: #007bff; }
    </style>
</head>
<body>
    <h1>JARVIS OS API - Phase 7 Mythos Omega</h1>
    <p>API Server is running. Available endpoints:</p>

    <h2>Core</h2>
    <div class="endpoint"><span class="method">GET</span> /health - Health check</div>
    <div class="endpoint"><span class="method">GET</span> /status - Runtime status</div>
    <div class="endpoint"><span class="method">GET</span> /tools - Tool catalog</div>
    <div class="endpoint"><span class="method">GET</span> /agents - List agents</div>
    <div class="endpoint"><span class="method">POST</span> /run - Execute prompt</div>

    <h2>Extensions</h2>
    <div class="endpoint"><span class="method">GET</span> /extensions - List extensions</div>
    <div class="endpoint"><span class="method">POST</span> /extensions/install - Install extension</div>

    <h2>Routes</h2>
    <div class="endpoint"><span class="method">GET</span> /routes - List API routes</div>

    <h2>Links</h2>
    <div class="endpoint"><span class="method">GET</span> /links - List resource links</div>
    <div class="endpoint"><span class="method">POST</span> /links/add - Add a link</div>

    <h2>Docs</h2>
    <p>Full documentation: <a href="/docs">/docs</a></p>
</body>
</html>"""


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="JARVIS OS API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8011, help="Port to listen on")
    parser.add_argument("--detached", action="store_true", help="Run as detached process")
    args = parser.parse_args()

    serve(host=args.host, port=args.port, detached=args.detached)
