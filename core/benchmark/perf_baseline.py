from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

_REPORTS_DIR = Path("benchmark_reports")


async def measure_cold_start() -> dict:
    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import jarvis; jarvis.build_parser().print_help()",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    await proc.wait()
    elapsed = time.monotonic() - start
    return {"cold_start_seconds": round(elapsed, 3)}


async def measure_import_times() -> dict:
    modules = [
        "jarvis", "core.version", "core.diagnostics",
        "demo.quick_demo", "core.main",
    ]
    results = {}
    for mod in modules:
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", f"import {mod}",
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        await proc.wait()
        elapsed = time.monotonic() - start
        results[mod] = round(elapsed, 3)
    return {"import_times": results}


def measure_memory() -> dict:
    try:
        import psutil
        proc = psutil.Process(os.getpid())
        mem = proc.memory_info()
        cpu_percent = proc.cpu_percent(interval=0.5)
        return {
            "rss_mb": round(mem.rss / 1024 / 1024, 1),
            "vms_mb": round(mem.vms / 1024 / 1024, 1),
            "cpu_percent": cpu_percent,
        }
    except ImportError:
        return {"error": "psutil not available"}


def measure_demo() -> dict:
    start = time.monotonic()
    try:
        from demo.quick_demo import main as demo_main
        exit_code = demo_main()
    except Exception as e:
        exit_code = -1
    elapsed = time.monotonic() - start
    return {"demo_duration_seconds": round(elapsed, 1), "exit_code": exit_code}


async def measure_server_startup(port: int = 18998) -> dict:
    start = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c",
            f"import sys, uvicorn; "
            f"sys.argv = ['', '127.0.0.1', '{port}', 'false']; "
            f"h, p, r = sys.argv[1], int(sys.argv[2]), sys.argv[3].lower() == 'true'; "
            f"import core.main; "
            f"uvicorn.run('core.main:app', host=h, port=p, reload=r, ws_ping_interval=60, ws_ping_timeout=30)",
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        ready = False
        url = f"http://127.0.0.1:{port}/"
        for _ in range(60):
            try:
                import httpx
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(url)
                    if resp.status_code < 500:
                        ready = True
                        break
            except Exception:
                pass
            await asyncio.sleep(1.0)
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except Exception:
            proc.kill()
        elapsed = time.monotonic() - start
        return {"server_startup_seconds": round(elapsed, 1), "ready": ready, "port": port}
    except Exception as e:
        return {"server_startup_seconds": None, "ready": False, "error": str(e)}


async def measure_setup_duration() -> dict:
    from core.setup.engine import SetupEngine
    from core.setup.detector import is_first_run, mark_setup_state
    if is_first_run():
        start = time.monotonic()
        engine = SetupEngine()
        await engine.run_full_setup()
        elapsed = time.monotonic() - start
        return {"setup_duration_seconds": round(elapsed, 1)}
    return {"setup_duration_seconds": None, "note": "setup already completed"}


async def measure_provider_discovery() -> dict:
    start = time.monotonic()
    from core.providers.bootstrap import bootstrap_providers
    providers = bootstrap_providers()
    elapsed = time.monotonic() - start
    return {
        "provider_discovery_seconds": round(elapsed, 3),
        "provider_count": len(providers) if providers else 0,
    }


def get_hardware_info() -> dict:
    cpu_info = platform.processor() or platform.machine()
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
        cpu_count = psutil.cpu_count(logical=True)
    except ImportError:
        ram_gb = 0
        cpu_count = 0
    gpu_info = []
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        gpu_info = [{"name": g.name, "memory_mb": g.memoryTotal} for g in gpus] if gpus else []
    except Exception:
        pass
    if not gpu_info:
        try:
            import warnings
            warnings.filterwarnings("ignore", message="The pynvml package is deprecated")
            from pynvml import nvmlInit, nvmlDeviceGetHandleByIndex, nvmlDeviceGetName, nvmlDeviceGetMemoryInfo
            nvmlInit()
            count = 0
            while True:
                try:
                    handle = nvmlDeviceGetHandleByIndex(count)
                    name = nvmlDeviceGetName(handle)
                    mem = nvmlDeviceGetMemoryInfo(handle)
                    gpu_info.append({"name": name, "memory_mb": round(mem.total / 1024 / 1024, 1)})
                    count += 1
                except Exception:
                    break
        except Exception:
            pass
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "processor": cpu_info,
        "cpu_count": cpu_count,
        "ram_gb": ram_gb,
        "gpus": gpu_info,
    }


async def run_all() -> dict:
    results = {}
    hardware = get_hardware_info()
    results["hardware"] = hardware
    results["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    results["jarvis_version"] = "3.0.0-rc3"

    print("[1/6] Cold start...")
    try:
        results.update(await asyncio.wait_for(measure_cold_start(), timeout=30))
    except Exception as e:
        results["cold_start_error"] = str(e)

    print("[2/6] Import times...")
    try:
        results.update(await asyncio.wait_for(measure_import_times(), timeout=60))
    except Exception as e:
        results["import_times_error"] = str(e)

    print("[3/6] Provider discovery...")
    try:
        results.update(await asyncio.wait_for(measure_provider_discovery(), timeout=30))
    except Exception as e:
        results["provider_discovery_error"] = str(e)

    print("[4/6] Demo...")
    try:
        results["demo"] = measure_demo()
    except Exception as e:
        results["demo_error"] = str(e)

    print("[5/6] Server startup...")
    try:
        results["server"] = await asyncio.wait_for(measure_server_startup(), timeout=90)
    except Exception as e:
        results["server_error"] = str(e)

    print("[6/6] Memory...")
    try:
        results["memory"] = measure_memory()
    except Exception as e:
        results["memory_error"] = str(e)

    return results


def write_report(results: dict):
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = _REPORTS_DIR / "performance.json"
    json_path.write_text(json.dumps(results, indent=2))
    md_path = _REPORTS_DIR / "performance_baseline.md"
    lines = [
        "# Performance Baseline\n",
        f"**Date:** {results['timestamp']}  ",
        f"**JARVIS version:** {results['jarvis_version']}  ",
        f"**Platform:** {results['hardware']['platform']}  ",
        f"**Python:** {results['hardware']['python_version']}  ",
        f"**CPU:** {results['hardware']['cpu_count']}× {results['hardware']['processor']}  ",
        f"**RAM:** {results['hardware']['ram_gb']} GB  ",
        f"**GPU:** {results['hardware'].get('gpus', [])}\n",
        "## Results\n",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Cold start | {results.get('cold_start_seconds', 'N/A')}s |",
    ]
    for mod, sec in results.get("import_times", {}).items():
        lines.append(f"| Import `{mod}` | {sec}s |")
    lines.append(f"| Provider discovery | {results.get('provider_discovery_seconds', 'N/A')}s |")
    demo = results.get("demo", {})
    lines.append(f"| Demo duration | {demo.get('demo_duration_seconds', 'N/A')}s |")
    server = results.get("server", {})
    lines.append(f"| Server startup | {server.get('server_startup_seconds', 'N/A')}s |")
    lines.append(f"| Server ready | {server.get('ready', False)} |")
    mem = results.get("memory", {})
    lines.append(f"| RSS memory | {mem.get('rss_mb', 'N/A')} MB |")
    lines.append(f"| VMS memory | {mem.get('vms_mb', 'N/A')} MB |")
    lines.append(f"| CPU idle | {mem.get('cpu_percent', 'N/A')}% |")
    lines.append("")
    md_path.write_text("\n".join(lines))
    print(f"\nReport: {md_path}")
    print(f"JSON:   {json_path}")


def main():
    results = asyncio.run(run_all())
    write_report(results)
    return 0
