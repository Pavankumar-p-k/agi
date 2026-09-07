#!/usr/bin/env python3
"""JARVIS one-line installer — clone, venv, deps, DB, PATH.

Usage:
    curl -sSL https://raw.githubusercontent.com/anomalyco/jarvis/main/install.py | python3
    irm https://raw.githubusercontent.com/anomalyco/jarvis/main/install.py | python
"""

import os
import subprocess
import sys
import shutil
import platform
from pathlib import Path

REPO = "https://github.com/anomalyco/jarvis.git"
BRANCH = "main"
VENV_DIR = "venv"
EXTRAS = "browser,voice,vision,firebase,dev"


def run(cmd, cwd=None, check=True) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=check)


def main():
    print("=" * 60)
    print("  JARVIS — One-Line Installer")
    print("=" * 60)

    # 1. Python check
    if sys.version_info < (3, 10):
        print("ERROR: Python 3.10+ required")
        sys.exit(1)
    print(f"  Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    # 2. Git check
    if not shutil.which("git"):
        print("ERROR: git not found — install git first")
        sys.exit(1)

    # 3. Clone / pull
    target = Path.cwd() / "jarvis"
    if target.exists():
        print(f"  Repo exists at {target} — pulling latest...")
        run(["git", "pull"], cwd=str(target))
    else:
        print(f"  Cloning {REPO}...")
        run(["git", "clone", "--depth", "1", "-b", BRANCH, REPO, str(target)])

    os.chdir(str(target))

    # 4. Create venv
    venv_path = target / VENV_DIR
    if not (venv_path / "pyvenv.cfg").exists():
        print(f"  Creating virtualenv at {VENV_DIR}...")
        run([sys.executable, "-m", "venv", str(venv_path)])
    else:
        print(f"  Virtualenv already exists at {VENV_DIR}")

    # 5. Detect python/pip inside venv
    is_win = platform.system() == "Windows"
    scripts = venv_path / ("Scripts" if is_win else "bin")
    pip_exe = str(scripts / "pip")
    python_exe = str(scripts / "python")

    # 6. Upgrade pip + install with all extras
    print("  Upgrading pip...")
    run([pip_exe, "install", "--upgrade", "pip"])
    print(f"  Installing JARVIS with extras [{EXTRAS}]...")
    run([pip_exe, "install", "-e", f".[{EXTRAS}]"])
    run([pip_exe, "install", "playwright"])
    print("  Installing Playwright browsers...")
    run([python_exe, "-m", "playwright", "install", "chromium"])

    # 7. Init database
    print("  Initializing database...")
    run([python_exe, "-c", "from core.database import init_db; import asyncio; asyncio.run(init_db())"])

    # 8. Create launcher in PATH
    if is_win:
        bat_dir = Path.home() / "AppData" / "Local" / "Microsoft" / "WindowsApps"
        if not bat_dir.exists():
            bat_dir = Path(os.environ.get("USERPROFILE", "."))
        launcher = bat_dir / "jarvis.bat"
        with open(str(launcher), "w") as f:
            f.write(f'@{python_exe} {target / "jarvis.py"} %*\r\n')
        print(f"  Created launcher: {launcher}")
    else:
        launcher = Path.home() / ".local" / "bin" / "jarvis"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        shebang = f"#!{python_exe}\n"
        with open(str(launcher), "w") as f:
            f.write(shebang)
            f.write(f"import sys; sys.path.insert(0, r'{target}'); from jarvis import main; main()\n")
        launcher.chmod(0o755)
        print(f"  Created launcher: {launcher}")
        print(f"  Ensure {launcher.parent} is in your PATH")

    # 9. Done
    print()
    print("=" * 60)
    print("  JARVIS INSTALLED SUCCESSFULLY")
    print("=" * 60)
    print(f"  Location: {target}")
    print(f"  Venv:     {VENV_DIR}")
    print()
    print("  Run:  jarvis              (interactive CLI)")
    print("        jarvis web          (web UI)")
    print("        jarvis chat         (chat mode)")
    print("        jarvis doctor       (health check)")
    print()
    print("  Start with local Ollama:")
    print(f"    cd {target}")
    print(f"    {scripts / 'python'} jarvis.py")


if __name__ == "__main__":
    main()
