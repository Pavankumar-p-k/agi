"""20-second demo: build hello.html to showcase the pipeline."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from core.setup.report import InstallResult

logger = logging.getLogger(__name__)


def run_hello_demo(on_progress: Callable[[str], None] | None = None) -> InstallResult:
    """Create a hello.html file as a quick demo of JARVIS capabilities."""
    demo_dir = Path.home() / ".jarvis" / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)

    html_path = demo_dir / "hello.html"

    if on_progress:
        on_progress("Creating hello.html...")

    html_content = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hello from JARVIS</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0a0f1a;
            color: #e0e8f0;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }
        .card {
            background: #111927;
            border: 1px solid #1e2d45;
            padding: 3rem 4rem;
            text-align: center;
            border-radius: 4px;
        }
        h1 {
            font-size: 3rem;
            font-weight: 300;
            letter-spacing: 0.15em;
            text-transform: uppercase;
        }
        h1 span { color: #00d4ff; }
        p {
            margin-top: 1rem;
            color: #7a8ba8;
            font-size: 0.9rem;
            letter-spacing: 0.08em;
        }
        .dot {
            display: inline-block;
            width: 6px; height: 6px;
            background: #00ff88;
            border-radius: 50%;
            margin-right: 8px;
            animation: pulse 2s ease-in-out infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        .status {
            margin-top: 2rem;
            font-size: 0.75rem;
            color: #4a5a72;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>JARVIS <span>ONLINE</span></h1>
        <p>Your local AI workspace is ready.</p>
        <div class="status"><span class="dot"></span>System operational</div>
    </div>
</body>
</html>"""

    try:
        html_path.write_text(html_content, encoding="utf-8")
    except OSError as e:
        return InstallResult("Demo", False, f"failed to write: {e}")

    if on_progress:
        on_progress("Opening in browser...")

    # Open in default browser
    try:
        import webbrowser
        webbrowser.open(html_path.as_uri())
    except Exception as e:
        logger.warning("Could not open browser: %s", e)

    return InstallResult("Demo", True, str(html_path))


def run_portfolio_demo(on_progress: Callable[[str], None] | None = None) -> InstallResult:
    """Full end-to-end demo: portfolio → GitHub → Pages → email.
    
    This is the launch showcase demo. For now, stubs out as hello.html.
    """
    return run_hello_demo(on_progress)
