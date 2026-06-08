import logging
"""jarvis_website_cli.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JARVIS Website CLI — paste these blocks into jarvis.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO INTEGRATE:

1. Find the section in jarvis.py where sub-parsers are created:
       sub = parser.add_subparsers(dest="command")
   Add the website sub-command right after:
       _add_website_commands(sub)

2. In the command dispatch section (the big if/elif block), add:
       elif args.command == "website":
           return cmd_website(args)

3. Paste the _add_website_commands() and cmd_website() functions
   from this file into jarvis.py.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import argparse
import asyncio
import json
import os
import webbrowser
from pathlib import Path
logger = logging.getLogger(__name__)


# ─── Sub-parser registration ─────────────────────────────────────────────────
def _add_website_commands(subparsers) -> None:
    """Register  jarvis website <build|preview|stop>  sub-commands."""
    wp = subparsers.add_parser(
        "website",
        help="AI-powered website generator",
        description="Generate, preview, and manage multi-page websites using JARVIS AI.",
    )
    ws = wp.add_subparsers(dest="website_action")

    # ── build ─────────────────────────────────────────────────────────────────
    wb = ws.add_parser(
        "build",
        help='Generate a website.  Example: jarvis website build "Coffee Shop"',
    )
    wb.add_argument("topic", help='Site topic / brand name, e.g. "Coffee Shop"')
    wb.add_argument(
        "--pages",
        default="index,about,services,contact",
        help="Comma-separated page names (default: index,about,services,contact)",
    )
    wb.add_argument(
        "--style",
        default="modern",
        choices=["modern","corporate","creative","dark","elegant","tech","warm","minimal"],
        help="Visual style preset (default: modern)",
    )
    wb.add_argument(
        "--output",
        default=None,
        metavar="DIR",
        help="Output directory (default: ~/.jarvis/generated_sites/<slug>)",
    )
    wb.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open browser after generation",
    )

    # ── preview ───────────────────────────────────────────────────────────────
    wpr = ws.add_parser(
        "preview",
        help="Serve a generated site.  Example: jarvis website preview ./my_site",
    )
    wpr.add_argument("directory", help="Path to generated site directory")
    wpr.add_argument("--port", type=int, default=None, help="Force a specific port")

    # ── stop ──────────────────────────────────────────────────────────────────
    wst = ws.add_parser("stop", help="Kill preview server(s)")
    wst.add_argument("--port", type=int, default=None, help="Stop specific port; omit for all")

    # ── styles ────────────────────────────────────────────────────────────────
    ws.add_parser("styles", help="List available style presets")


# ─── Command handler ──────────────────────────────────────────────────────────
def cmd_website(args: argparse.Namespace) -> int:
    """Handler for  jarvis website <action>."""
    action = getattr(args, "website_action", None)
    if not action:
        print("Usage: jarvis website <build|preview|stop|styles>")
        print("       jarvis website build --help")
        return 1

    if action == "build":
        return _cmd_website_build(args)
    elif action == "preview":
        return _cmd_website_preview(args)
    elif action == "stop":
        return _cmd_website_stop(args)
    elif action == "styles":
        return _cmd_website_styles()
    else:
        print(f"Unknown website action: {action}")
        return 1


def _cmd_website_build(args: argparse.Namespace) -> int:
    topic  = args.topic
    pages  = [p.strip() for p in args.pages.split(",") if p.strip()]
    style  = args.style
    outdir = args.output
    no_br  = getattr(args, "no_browser", False)

    print(f"\n🌐 JARVIS Website Generator")
    print(f"   Topic : {topic}")
    print(f"   Pages : {', '.join(pages)}")
    print(f"   Style : {style}")
    if outdir:
        print(f"   Output: {outdir}")
    print()

    from tools.website_generator import generate_site_async  # type: ignore

    print("⏳ Step 1/5 — Researching topic...")
    print("🎨 Step 2/5 — Designing CSS system...")
    print("📝 Step 3/5 — Generating pages (this may take 1-2 min)...")

    try:
        result = asyncio.run(generate_site_async(topic, pages, outdir, style))
    except KeyboardInterrupt:
        print("\n⚠️  Generation interrupted.")
        return 130

    if not result.get("success"):
        print(f"❌ Generation failed: {result.get('error','unknown error')}")
        return 1

    print(f"\n✅ Website generated in {result['elapsed_seconds']}s")
    print(f"   Output  : {result['output_dir']}")
    print(f"   Pages   : {result['page_count']}")
    print()

    for pg in result["pages"]:
        flag = " ⚠️  fallback" if pg.get("fallback") else ""
        print(f"   📄 {pg['file']:30s} {pg['size_bytes']:>8,} bytes{flag}")

    print(f"\n🚀 Preview: {result['preview_url']}")
    print(f"   Open  : {result['open_in_browser']}\n")

    if not no_br:
        try:
            webbrowser.open(result["open_in_browser"])
        except Exception as e:
            logger.warning("[tools.jarvis_website_cli] generate_website failed: %s", e)

    return 0


def _cmd_website_preview(args: argparse.Namespace) -> int:
    directory = args.directory
    if not os.path.isdir(directory):
        print(f"❌ Directory not found: {directory}")
        return 1

    from tools.website_generator import start_preview  # type: ignore

    port = start_preview(directory)
    url  = f"http://localhost:{port}"
    print(f"\n🌐 Preview server running at {url}")
    print(f"   Serving: {directory}")
    print("   Press Ctrl+C to stop.\n")

    try:
        webbrowser.open(url + "/index.html")
    except Exception as e:
        logger.warning("[tools.jarvis_website_cli] website_cli_operation failed: %s", e)

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        from tools.website_generator import stop_preview  # type: ignore
        stop_preview(port)
        print(f"\n⏹  Preview server on port {port} stopped.")

    return 0


def _cmd_website_stop(args: argparse.Namespace) -> int:
    from tools.website_generator import stop_preview  # type: ignore
    result = stop_preview(getattr(args, "port", None))
    stopped = result.get("stopped_ports", [])
    if stopped:
        print(f"⏹  Stopped preview server(s) on port(s): {', '.join(map(str, stopped))}")
    else:
        print("ℹ️  No active preview servers found.")
    return 0


def _cmd_website_styles() -> int:
    from tools.website_generator import STYLE_HINTS  # type: ignore
    print("\n🎨 Available style presets:\n")
    for name, desc in STYLE_HINTS.items():
        print(f"   {name:<12}  {desc}")
    print()
    return 0


# ─── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # python jarvis_website_cli.py
    import sys
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command")
    _add_website_commands(sub)
    args = p.parse_args(sys.argv[1:] or ["website", "build", "Test Brand", "--no-browser"])
    if args.command == "website":
        sys.exit(cmd_website(args))
