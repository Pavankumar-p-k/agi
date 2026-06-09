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
"""tools/file_search.py
Searches the local filesystem for user files by name or type.
Searches Documents, Desktop, Downloads, and the JARVIS project root.
"""

import os
import glob
from pathlib import Path
from typing import List, Dict

USER_HOME = Path.home()
SEARCH_DIRS = [
    USER_HOME / "Documents",
    USER_HOME / "Desktop",
    USER_HOME / "Downloads",
    USER_HOME,
]

TYPE_MAP = {
    "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"],
    "document": [".pdf", ".docx", ".doc", ".txt", ".md", ".rtf", ".odt"],
    "code": [".py", ".js", ".ts", ".dart", ".java", ".cpp", ".h", ".cs", ".go", ".rs", ".rb", ".php"],
    "spreadsheet": [".xlsx", ".xls", ".csv"],
    "presentation": [".pptx", ".ppt"],
    "archive": [".zip", ".tar", ".gz", ".rar", ".7z"],
    "video": [".mp4", ".avi", ".mkv", ".mov", ".wmv"],
    "audio": [".mp3", ".wav", ".flac", ".aac", ".ogg"],
}

ALL_EXTENSIONS = [ext for exts in TYPE_MAP.values() for ext in exts]


def find_files(query: str, max_results: int = 5) -> List[Dict]:
    """Search for files matching a query string. Returns list of file info dicts."""
    query_lower = query.lower().strip()
    results = []

    for search_dir in SEARCH_DIRS:
        if not search_dir.exists():
            continue

        try:
            for entry in search_dir.iterdir():
                if not entry.is_file():
                    continue

                name_lower = entry.name.lower()
                score = _match_score(query_lower, name_lower, entry.suffix.lower())

                if score > 0:
                    results.append({
                        "name": entry.name,
                        "path": str(entry.resolve()),
                        "size": entry.stat().st_size,
                        "modified": entry.stat().st_mtime,
                        "score": score,
                        "extension": entry.suffix.lower(),
                    })
        except PermissionError:
            continue

    results.sort(key=lambda x: (-x["score"], -x["modified"]))
    return results[:max_results]


def find_by_type(file_type: str, max_results: int = 5) -> List[Dict]:
    """Find files by type category (image, document, code, etc.)."""
    extensions = TYPE_MAP.get(file_type.lower(), [])
    if not extensions:
        return []

    results = []

    for search_dir in SEARCH_DIRS:
        if not search_dir.exists():
            continue

        try:
            for entry in search_dir.iterdir():
                if not entry.is_file():
                    continue
                if entry.suffix.lower() in extensions:
                    results.append({
                        "name": entry.name,
                        "path": str(entry.resolve()),
                        "size": entry.stat().st_size,
                        "modified": entry.stat().st_mtime,
                        "score": 1,
                        "extension": entry.suffix.lower(),
                    })
        except PermissionError:
            continue

    results.sort(key=lambda x: -x["modified"])
    return results[:max_results]


def _match_score(query: str, filename: str, ext: str) -> int:
    """Score how well a filename matches a query (0 = no match)."""
    if query in filename:
        return 10
    words = query.split()
    match_count = sum(1 for w in words if w in filename)
    if match_count > 0:
        return match_count * 5
    return 0
