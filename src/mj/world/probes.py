"""Real probes for machine facts — no invented answers.

Each probe returns observed data plus honest provenance (which API produced
it) and a TTL for how long the observation stays fresh. Anything a probe
cannot observe is reported as unobserved, never guessed (plan section 12).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from . import model
from .model import Fact

# TTLs (seconds): short for volatile facts, generous for slow-changing ones.
TTL_DISK = 30
TTL_PROCESSES = 10
TTL_APPS = 4 * 3600
TTL_TOOLS = 30 * 60

MAX_SAMPLE_NAMES = 100

try:
    import psutil

    _PSUTIL_ERR: str | None = None
except Exception as exc:  # pragma: no cover - only hit on broken installs
    psutil = None
    _PSUTIL_ERR = f"psutil unavailable: {exc}"


# -- probes: each returns a list of Fact (not yet persisted) ----------------


def probe_disk() -> list[Fact]:
    """Free space per unique drive touched by the working dir and home dir."""
    facts: list[Fact] = []
    seen_anchors: set[str] = set()
    for p in (Path(os.getcwd()), Path.home()):
        anchor = p.anchor or str(Path(p).resolve().anchor) or "/"
        if anchor in seen_anchors:
            continue
        seen_anchors.add(anchor)
        usage = shutil.disk_usage(p)
        facts.append(
            model.Fact(
                scope="disk",
                key=f"free_bytes:{anchor}",
                value={"path": anchor, "free": usage.free, "total": usage.total},
                source="shutil.disk_usage",
                ttl_seconds=TTL_DISK,
                label="verified",
            )
        )
    return facts


def probe_processes() -> list[Fact]:
    """Running process summary + a per-name registry used by 'is X running'."""
    if psutil is None:
        return [
            model.Fact(
                scope="processes",
                key="summary",
                value={"error": _PSUTIL_ERR},
                source="psutil",
                ttl_seconds=TTL_PROCESSES,
                label="stale",
            )
        ]
    names: dict[str, int] = {}
    count = 0
    for proc in psutil.process_iter(["name"]):
        try:
            name = (proc.info["name"] or "").lower()
            if name:
                names[name] = names.get(name, 0) + 1
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    top = sorted(names.items(), key=lambda kv: -kv[1])[:MAX_SAMPLE_NAMES]
    return [
        model.Fact(
            scope="processes",
            key="summary",
            value={"count": count, "distinct_names": len(names), "top": top},
            source="psutil.process_iter",
            ttl_seconds=TTL_PROCESSES,
            label="verified",
        )
    ]


def probe_installed_apps() -> list[Fact]:
    """Installed applications, per-OS, with the enumeration source recorded.

    Windows: Uninstall registry keys (HKLM+HKCU). Others: the standard
    application directories (/Applications, /usr/share/applications).
    """
    apps: list[str] = []
    source: str
    if sys.platform == "win32":
        import winreg

        source = "winreg:UninstallKeys"
        paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, sub in paths:
            try:
                k = winreg.OpenKey(hive, sub)
            except OSError:
                continue
            with k:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    try:
                        subk = winreg.OpenKey(k, winreg.EnumKey(k, i))
                    except OSError:
                        continue
                    with subk:
                        try:
                            name, _ = winreg.QueryValueEx(subk, "DisplayName")
                        except OSError:
                            continue
                        if name:
                            apps.append(name)
    elif sys.platform == "darwin":
        source = "path:/Applications"
        try:
            apps = [d.stem for d in Path("/Applications").glob("*.app")]
        except OSError:
            apps = []
    else:
        source = "path:/usr/share/applications"
        try:
            apps = [d.stem for d in Path("/usr/share/applications").glob("*.desktop")]
        except OSError:
            apps = []
    names = sorted(set(apps))
    return [
        model.Fact(
            scope="apps",
            key="installed",
            value={"count": len(names), "names": names[:MAX_SAMPLE_NAMES]},
            source=source,
            ttl_seconds=TTL_APPS,
            label="verified",
        )
    ]


def probe_tools() -> list[Fact]:
    """Versions of the interpreter and common build tools."""
    value: dict[str, Any] = {"python": platform.python_version()}
    for tool, argv, regexp in (
        ("git", ["git", "--version"], None),
        ("uv", ["uv", "--version"], None),
    ):
        try:
            out = subprocess.run(argv, capture_output=True, text=True, timeout=10)
            value[tool] = (out.stdout or out.stderr).strip() if out.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            value[tool] = None
    return [
        model.Fact(
            scope="tools",
            key="versions",
            value=value,
            source="subprocess --version",
            ttl_seconds=TTL_TOOLS,
            label="verified",
        )
    ]


PROBES: dict[str, Callable[[], list[Fact]]] = {
    "disk": probe_disk,
    "processes": probe_processes,
    "apps": probe_installed_apps,
    "tools": probe_tools,
}


def run_probes(store, scopes: list[str] | None = None) -> list[Fact]:
    """Run the selected (default: all) probes and persist their facts."""
    chosen = {k: v for k, v in PROBES.items() if scopes is None or k in scopes}
    facts: list[Fact] = []
    for name in sorted(chosen):
        facts.extend(chosen[name]())
    model.refresh(store, facts, actor=f"probe:{','.join(sorted(chosen)) or 'none'}")
    return facts
