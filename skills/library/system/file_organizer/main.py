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

import os
import shutil
from pathlib import Path
from skills.utils import success_response, error_response

FILE_CATEGORIES = {
    "images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico"],
    "documents": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".csv"],
    "audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"],
    "video": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"],
    "archives": [".zip", ".tar", ".gz", ".rar", ".7z", ".bz2"],
    "code": [".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c", ".h", ".go", ".rs", ".rb", ".php"],
    "executables": [".exe", ".msi", ".bat", ".cmd", ".ps1", ".sh"],
    "torrents": [".torrent"],
}

async def file_organizer(params: dict) -> dict:
    """Organize files in a directory into categorized subfolders."""
    directory = params.get("directory", params.get("path", os.getcwd()))
    dry_run = params.get("dry_run", params.get("preview", False))
    recursive = params.get("recursive", False)
    sort_by_date = params.get("sort_by_date", False)
    
    target_dir = Path(directory).expanduser().resolve()
    if not target_dir.exists():
        return error_response(f"Directory not found: {directory}")
    
    organized = {}
    skipped = []
    errors = []
    
    pattern = "**/*" if recursive else "*"
    for item in target_dir.glob(pattern):
        if not item.is_file():
            continue
        if item.parent == target_dir:
            ext = item.suffix.lower()
            category = None
            for cat, exts in FILE_CATEGORIES.items():
                if ext in exts:
                    category = cat
                    break
            if not category:
                category = "other"
            
            if sort_by_date:
                from datetime import datetime
                mtime = datetime.fromtimestamp(item.stat().st_mtime)
                category = f"{category}/{mtime.strftime('%Y-%m')}"
            
            dest_dir = target_dir / category
            if dry_run:
                organized.setdefault(category, []).append(item.name)
            else:
                try:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest = dest_dir / item.name
                    if dest.exists():
                        base = item.stem
                        dest = dest_dir / f"{base}_{item.stat().st_mtime:.0f}{ext}"
                    shutil.move(str(item), str(dest))
                    organized.setdefault(category, []).append(item.name)
                except Exception as e:
                    errors.append(f"{item.name}: {e}")
    
    result = {
        "directory": str(target_dir),
        "categories": {k: len(v) for k, v in organized.items()},
        "total_files": sum(len(v) for v in organized.values()),
        "dry_run": dry_run,
    }
    if errors:
        result["errors"] = errors
    
    action = "Preview" if dry_run else "Organized"
    return success_response(result, f"{action} {result['total_files']} files in {target_dir.name}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    
    async def on_load(self):
        pass
