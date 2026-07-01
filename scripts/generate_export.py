# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Generate the 6 markdown export files from the current codebase.
"""

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

BASE = Path("C:/Users/peter/Desktop/jarvis")
OUT = Path("C:/Users/peter/Desktop/jarvis_export")

EXCLUDE_DIRS = {
    ".git", "__pycache__", ".venv", ".venv_prod", "venv",
    ".pytest_cache", ".ruff_cache", ".hypothesis",
    "node_modules", ".next", "out", "dist", "build", ".turbo",
    "jarvis_ai.egg-info", "jarvis_launcher.egg-info",
    "jarvis_plugin_sdk.egg-info",
    "logs", "data", ".vscode", ".idea",
}

BINARY_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dll", ".pyd", ".exe",
    ".dylib", ".obj", ".o", ".a", ".lib", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".wav", ".mp4", ".avi", ".mov",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ico", ".icns",
    ".onnx", ".pt", ".pth", ".bin", ".safetensors",
}

def should_exclude(path: Path) -> bool:
    str_path = str(path).replace("\\", "/")
    # Check each directory segment
    parts = str_path.split("/")
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
    # Exclude hidden files/dirs
    if any(part.startswith(".") for part in parts if part):
        return True
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    return False

def get_tree(path: Path, prefix: str = "") -> list[str]:
    lines = []
    entries = sorted(
        [e for e in path.iterdir() if not should_exclude(e)],
        key=lambda e: (not e.is_dir(), e.name.lower()),
    )
    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{entry.name}")
        if entry.is_dir():
            extension = "    " if is_last else "│   "
            lines.extend(get_tree(entry, prefix + extension))
    return lines

# ---- Category mapping ----

CATEGORIES = {
    "01_structure_and_config": {
        "desc": "Directory tree, README, LICENSE, setup.py, pyproject.toml, requirements, git config, CI/CD",
        "paths": [
            BASE,
        ],
        "root_only": True,  # only root-level files for "paths"
    },
    "02_core_foundation": {
        "desc": "Core module: auth, config, database, lifespan, models, embeddings, memory, plugin system",
        "paths": [BASE / "core"],
    },
    "03_tools_and_execution": {
        "desc": "Tools, execution, agent prompts, helpers",
        "paths": [BASE / "core" / "tools"],
    },
    "04_ai_and_intelligence": {
        "desc": "AI, brain, reasoning, memory, cognitive patterns",
        "paths": [BASE / "brain", BASE / "memory"],
    },
    "05_routes_and_api": {
        "desc": "Routes, API endpoints, MCP servers, web",
        "paths": [BASE / "core" / "routes", BASE / "api", BASE / "mcp"],
    },
    "06_applications_and_skills": {
        "desc": "Applications, skills, plugins, assistant, channels, tools, CLI, TUI, tests",
        "paths": [
            BASE / "assistant",
            BASE / "channels",
            BASE / "plugins",
            BASE / "skills",
            BASE / "tools",
            BASE / "monitors",
            BASE / "governance",
            BASE / "services",
            BASE / "orchestrator",
            BASE / "network",
            BASE / "automation",
            BASE / "pc_agent",
            BASE / "vision",
            BASE / "media",
            BASE / "utils",
            BASE / "scripts",
            BASE / "notifications",
            BASE / "reminders",
            BASE / "notes",
            BASE / "cookbook",
            BASE / "ai_os",
            BASE / "jarvis_os",
            BASE / "learning",
            BASE / "eval",
            BASE / "train",
            BASE / "daemon",
            BASE / "demo",
            BASE / "models",
            BASE / "routers",
            BASE / "experimental",
            BASE / "jarvis_tui",
            BASE / "web",
            BASE / "static",
            BASE / "docs",
            BASE / "docs_test",
            BASE / "docs_user",
            BASE / "tests",
        ],
    },
}

def get_root_files() -> list[Path]:
    """Get root-level files (not dirs) for file 01."""
    files = []
    for entry in sorted(BASE.iterdir(), key=lambda e: e.name.lower()):
        if entry.is_file() and not should_exclude(entry):
            files.append(entry)
    return files

def is_binary(path: Path) -> bool:
    """Check if a file is likely binary."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            f.read(1024)
        return False
    except (UnicodeDecodeError, Exception):
        return True

def get_file_lang(path: Path) -> str:
    ext = path.suffix.lower()
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "markdown",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".sh": "bash",
        ".bat": "bat",
        ".ps1": "powershell",
        ".toml": "toml",
        ".cfg": "ini",
        ".ini": "ini",
        ".env": "env",
        ".gitignore": "gitignore",
        ".dockerfile": "docker",
        "dockerfile": "docker",
        ".sql": "sql",
        ".txt": "text",
        ".cfg": "cfg",
        ".conf": "conf",
        ".xml": "xml",
        ".svg": "svg",
        ".lock": "text",
    }
    name_lower = path.name.lower()
    if name_lower == "dockerfile":
        return "docker"
    if name_lower == "makefile":
        return "makefile"
    return mapping.get(ext, "text")

def collect_files() -> dict[str, list[Path]]:
    result = {}

    # File 01: root config files + tree
    root_files = get_root_files()
    result["01_structure_and_config"] = sorted(root_files, key=lambda p: p.name.lower())

    # File 02: core/ (excluding core/tools/, core/routes/)
    core_exclude = {BASE / "core" / "tools", BASE / "core" / "routes"}
    core_files = []
    for f in sorted(BASE.rglob("core/**/*")):
        if f.is_file() and not should_exclude(f):
            parent = f.parent
            if not any(parent == exc or str(parent).startswith(str(exc)) for exc in core_exclude):
                core_files.append(f)
    result["02_core_foundation"] = sorted(core_files, key=lambda p: str(p.relative_to(BASE)))

    # File 03: core/tools/
    tool_files = []
    for f in sorted((BASE / "core" / "tools").rglob("*")):
        if f.is_file() and not should_exclude(f):
            tool_files.append(f)
    result["03_tools_and_execution"] = sorted(tool_files, key=lambda p: str(p.relative_to(BASE)))

    # File 04: brain/, memory/
    brain_memory = []
    for d in [BASE / "brain", BASE / "memory"]:
        if d.exists():
            for f in sorted(d.rglob("*")):
                if f.is_file() and not should_exclude(f):
                    brain_memory.append(f)
    result["04_ai_and_intelligence"] = sorted(brain_memory, key=lambda p: str(p.relative_to(BASE)))

    # File 05: core/routes/, api/, mcp/
    routes_api = []
    for d in [BASE / "core" / "routes", BASE / "api", BASE / "mcp"]:
        if d.exists():
            for f in sorted(d.rglob("*")):
                if f.is_file() and not should_exclude(f):
                    routes_api.append(f)
    result["05_routes_and_api"] = sorted(routes_api, key=lambda p: str(p.relative_to(BASE)))

    # File 06: everything else
    other = []
    other_dirs = [
        "assistant", "channels", "plugins", "skills",
        "tools", "monitors", "governance", "services",
        "orchestrator", "network", "automation", "pc_agent",
        "vision", "media", "utils", "scripts",
        "notifications", "reminders", "notes", "cookbook",
        "ai_os", "jarvis_os", "learning", "eval", "train",
        "daemon", "demo", "models", "routers",
        "experimental", "jarvis_tui", "web", "static",
        "docs", "docs_test", "docs_user", "tests",
        ".github",
    ]
    for dname in other_dirs:
        d = BASE / dname
        if d.exists():
            for f in sorted(d.rglob("*")):
                if f.is_file() and not should_exclude(f):
                    other.append(f)
    result["06_applications_and_skills"] = sorted(other, key=lambda p: str(p.relative_to(BASE)))

    return result

def read_file_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("[scripts.generate_export] read file safe failed for %s: %s", path.name, e)
        return f"[Binary or unreadable file: {path.name}]"

def write_export(name: str, desc: str, files: list[Path], tree_section: str = ""):
    out_path = OUT / f"{name}.md"
    print(f"Generating {out_path.name} ({len(files)} files)...")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# ======================================================================\n")
        f.write(f"# JARVIS EXPORT — {name}\n")
        f.write(f"# {desc}\n")
        f.write(f"# Total files in this segment: {len(files)}\n")
        f.write(f"# ======================================================================\n\n")

        if tree_section:
            f.write(tree_section)
            f.write("\n\n")

        for filepath in files:
            try:
                rel = filepath.relative_to(BASE)
            except ValueError:
                rel = filepath

            content = read_file_safe(filepath)
            lang = get_file_lang(filepath)

            f.write(f"## 📄 {rel.as_posix()}\n")
            f.write(f"```{lang}\n")
            f.write(content)
            if not content.endswith("\n"):
                f.write("\n")
            f.write("```\n\n")

def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # Generate directory tree
    tree_lines = get_tree(BASE)
    tree_str = "## DIRECTORY STRUCTURE\n```\n" + "\n".join(tree_lines) + "\n```"

    files = collect_files()

    # File 01: root config files + tree
    write_export(
        "01_structure_and_config",
        "Directory tree, README, LICENSE, setup.py, pyproject.toml, requirements, git config, CI/CD",
        files["01_structure_and_config"],
        tree_section=tree_str,
    )

    # File 02: core/ (excluding tools and routes)
    write_export(
        "02_core_foundation",
        "Core module: auth, config, database, lifespan, models, embeddings, memory, plugin system",
        files["02_core_foundation"],
    )

    # File 03: core/tools/
    write_export(
        "03_tools_and_execution",
        "Tools, execution, agent prompts, helpers",
        files["03_tools_and_execution"],
    )

    # File 04: brain/ + memory/
    write_export(
        "04_ai_and_intelligence",
        "AI, brain, reasoning, memory, cognitive patterns",
        files["04_ai_and_intelligence"],
    )

    # File 05: core/routes/ + api/ + mcp/
    write_export(
        "05_routes_and_api",
        "Routes, API endpoints, MCP servers, web",
        files["05_routes_and_api"],
    )

    # File 06: everything else
    write_export(
        "06_applications_and_skills",
        "Applications, skills, plugins, assistant, channels, tools, CLI, TUI, tests",
        files["06_applications_and_skills"],
    )

    print("\nDone! All 6 export files regenerated.")

if __name__ == "__main__":
    main()
