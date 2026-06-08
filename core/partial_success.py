"""core/partial_success.py
Tracks build progress as a percentage, preserves usable sub-outputs,
and enables partial completion even when some pages/steps fail.
"""
import logging
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PageStatus:
    name: str
    status: str = "pending"  # pending | building | done | failed
    file_path: str = ""


@dataclass
class ProgressSnapshot:
    total_pages: int = 0
    completed_pages: int = 0
    failed_pages: int = 0
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0

    @property
    def page_progress(self) -> float:
        if self.total_pages == 0:
            return 0.0
        return (self.completed_pages / self.total_pages) * 100.0

    @property
    def step_progress(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return (self.completed_steps / self.total_steps) * 100.0

    @property
    def overall(self) -> float:
        return (self.page_progress + self.step_progress) / 2.0

    def to_dict(self) -> dict:
        return {
            "total_pages": self.total_pages,
            "completed_pages": self.completed_pages,
            "failed_pages": self.failed_pages,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "page_progress": round(self.page_progress, 1),
            "step_progress": round(self.step_progress, 1),
            "overall": round(self.overall, 1),
        }


@dataclass
class PartialResult:
    pages: list[PageStatus] = field(default_factory=list)
    usable_outputs: dict[str, str] = field(default_factory=dict)
    failing_steps: list[str] = field(default_factory=list)
    progress: ProgressSnapshot = field(default_factory=ProgressSnapshot)
    usable: bool = False

    def add_page(self, name: str, status: str, file_path: str = ""):
        self.pages.append(PageStatus(name=name, status=status, file_path=file_path))
        if status == "done":
            self.progress.completed_pages += 1
            if file_path:
                self.usable_outputs[name] = file_path
        elif status == "failed":
            self.progress.failed_pages += 1
        self.progress.total_pages = len(self.pages)

    def add_step_result(self, step_id: str, success: bool, output: str = ""):
        self.progress.total_steps += 1
        if success:
            self.progress.completed_steps += 1
            self.usable_outputs[step_id] = output
        else:
            self.progress.failed_steps += 1
            self.failing_steps.append(step_id)

    def is_usable(self) -> bool:
        return self.progress.completed_pages > 0 or self.progress.completed_steps > 0


class PartialSuccessTracker:
    def __init__(self):
        self.results: dict[str, PartialResult] = {}

    def init_project(self, project: str, pages: list[str] = None):
        pr = PartialResult()
        if pages:
            for p in pages:
                pr.add_page(p, "pending")
        self.results[project] = pr

    def get(self, project: str) -> Optional[PartialResult]:
        return self.results.get(project)

    def mark_page(self, project: str, page: str, status: str, file_path: str = ""):
        pr = self.results.setdefault(project, PartialResult())
        existing = next((p for p in pr.pages if p.name == page), None)
        if existing:
            old_status = existing.status
            existing.status = status
            existing.file_path = file_path or existing.file_path
            if old_status != status:
                if old_status == "done":
                    pr.progress.completed_pages = max(0, pr.progress.completed_pages - 1)
                elif old_status == "failed":
                    pr.progress.failed_pages = max(0, pr.progress.failed_pages - 1)
                if status == "done":
                    pr.progress.completed_pages += 1
                elif status == "failed":
                    pr.progress.failed_pages += 1
        else:
            pr.add_page(page, status, file_path)

    def mark_step(self, project: str, step_id: str, success: bool, output: str = ""):
        pr = self.results.setdefault(project, PartialResult())
        pr.add_step_result(step_id, success, output)

    def snapshot(self, project: str) -> Optional[ProgressSnapshot]:
        pr = self.results.get(project)
        return pr.progress if pr else None

    def get_usable(self, project: str) -> dict[str, str]:
        pr = self.results.get(project)
        return pr.usable_outputs if pr else {}

    def sum_usable_pages(self, workspace: Path) -> list[str]:
        usable = []
        for fp in workspace.rglob("*.html"):
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                size = len(content)
                if size > 500 and not re.search(r'\bLorem\s*ipsum\b', content, re.IGNORECASE):
                    usable.append(str(fp))
            except Exception as e:
                logger.exception("[PARTIAL] read error: %s", e)
        return usable


partial_tracker = PartialSuccessTracker()
