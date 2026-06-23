"""Repair chaining: iterative fix → rebuild → detect → fix → ... → success.

Architecture:
    ┌──────────────┐
    │ Build/Rebuild│
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │ Parse Errors │
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │ 0 errors?    │───Yes──→ Success
    └──────┬───────┘
           │ No
           ▼
    ┌──────────────────┐
    │ Safety Checks:   │
    │ • max_iterations │───Fail──→ Stop
    │ • loop detected  │───Fail──→ Stop
    │ • no progress    │───Fail──→ Stop
    └──────┬───────────┘
           │ Pass
           ▼
    ┌──────────────┐
    │ Snapshot      │
    │ affected files│
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │ Apply Fix #1 │
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │ Rebuild      │
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │ Errors ↓?    │───No──→ Rollback
    │              │        │
    │ New errors?  │        ▼
    └──────┬───────┘    Record Failure
           │ Yes              │
           ▼                  ▼
    Record Success       Try Next Fix
           │
           ▼
        Repeat
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from brain.compiler_repair_engine import (
    CATEGORY_REPAIR_MAP,
    CompilerRepairEngine,
    RepairAction,
    JavacError,
)

logger = logging.getLogger(__name__)


# ── Data Classes ─────────────────────────────────────────────────────


@dataclass
class ChainMetrics:
    """Aggregate metrics across all chain iterations."""
    iterations: int = 0
    errors_fixed: int = 0
    errors_introduced: int = 0
    rollbacks: int = 0
    builds_run: int = 0
    loop_detections: int = 0
    no_progress_detections: int = 0
    deterministic_repairs: int = 0
    memory_repairs: int = 0
    llm_repairs: int = 0
    total_duration_ms: float = 0.0
    start_time: str = ""
    end_time: str = ""
    per_iteration: list[IterationSnapshot] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "iterations": self.iterations,
            "errors_fixed": self.errors_fixed,
            "errors_introduced": self.errors_introduced,
            "rollbacks": self.rollbacks,
            "builds_run": self.builds_run,
            "loop_detections": self.loop_detections,
            "no_progress_detections": self.no_progress_detections,
            "deterministic_repairs": self.deterministic_repairs,
            "memory_repairs": self.memory_repairs,
            "llm_repairs": self.llm_repairs,
            "total_duration_ms": round(self.total_duration_ms, 1),
        }


@dataclass
class IterationSnapshot:
    """State at a single chain iteration."""
    iteration: int
    error_count: int
    categories: list[str]
    fix_applied: str | None = None
    fix_category: str | None = None
    fix_success: bool = False
    rolled_back: bool = False
    duration_ms: float = 0.0
    error_delta: int = 0  # positive = more errors after fix


@dataclass
class ChainResult:
    """Final result of a repair chain run."""
    success: bool
    total_iterations: int
    total_fixes_applied: int
    final_error_count: int
    final_errors: list[JavacError]
    metrics: ChainMetrics = field(default_factory=ChainMetrics)
    stop_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "total_iterations": self.total_iterations,
            "total_fixes_applied": self.total_fixes_applied,
            "final_error_count": self.final_error_count,
            "stop_reason": self.stop_reason,
            "metrics": self.metrics.to_dict(),
        }


# ── File Snapshot / Rollback ────────────────────────────────────────


class FileSnapshot:
    """Snapshot and rollback files modified during a repair."""

    def __init__(self):
        self._backups: dict[str, str] = {}

    def snapshot(self, filepath: str) -> None:
        """Save a backup copy of the file."""
        if not os.path.isfile(filepath):
            return
        with open(filepath, "rb") as f:
            content = f.read()
        self._backups[filepath] = content

    def snapshot_directory(self, directory: str, pattern: str = ".java") -> None:
        """Snapshot all files matching pattern in directory."""
        if not os.path.isdir(directory):
            return
        for root, _dirs, files in os.walk(directory):
            for f in files:
                if f.endswith(pattern):
                    self.snapshot(os.path.join(root, f))

    def rollback(self) -> list[str]:
        """Restore all snapped files. Returns list of restored paths."""
        restored = []
        for filepath, content in self._backups.items():
            try:
                with open(filepath, "wb") as f:
                    f.write(content)
                restored.append(filepath)
            except Exception as e:
                logger.warning("Rollback failed for %s: %s", filepath, e)
        return restored

    def get_changed_files(self) -> list[str]:
        """Return list of files that differ from their snapshots."""
        changed = []
        for filepath, original in self._backups.items():
            if not os.path.isfile(filepath):
                changed.append(filepath)
                continue
            with open(filepath, "rb") as f:
                if f.read() != original:
                    changed.append(filepath)
        return changed


# ── Error Signature for Loop Detection ──────────────────────────────


def error_signature(errors: list[JavacError]) -> str:
    """Create a stable hash of error file+line+category for loop detection."""
    sig_parts = sorted(f"{e.file}:{e.line}:{e.category}" for e in errors)
    return hashlib.md5("|".join(sig_parts).encode()).hexdigest()


# ── Priority Ordering ──────────────────────────────────────────────


REPAIR_PRIORITY: list[str] = [
    # Syntax errors first (cause cascading failures)
    "syntax_semicolon", "syntax_paren", "syntax_string", "lambda_syntax",
    # Imports (cheap, unambiguous)
    "missing_import", "missing_package",
    "missing_nav_import", "missing_recyclerview_import",
    "missing_livedata_import", "missing_viewmodel_import",
    "missing_viewmodel_provider", "missing_material_import",
    "missing_gson_import", "missing_image_loader_import",
    # Build configuration
    "missing_gradle_plugin", "gradle_syntax", "missing_dependency",
    "kotlin_jvm_target", "d8_duplicate_class", "d8_desugar_error",
    # Resources (may unblock other errors)
    "missing_layout", "missing_drawable", "missing_string",
    "missing_color", "missing_mipmap", "missing_view_id",
    "missing_resource", "missing_theme",
    "aapt2_error", "resource_not_found", "resource_linking",
    # Structure
    "class_file_mismatch", "package_mismatch",
    "duplicate_override", "invalid_override", "type_mismatch",
    # Class/symbol
    "missing_symbol", "missing_class", "missing_method",
    "missing_databinding",
    # Room (annotation processing, usually last)
    "room_entity", "room_field", "room_primary_key",
    "room_schema", "room_query",
    # Manifest
    "missing_activity", "missing_permission",
    # Fallback
    "ndk_build_error",
]

_CATEGORY_RANK = {cat: i for i, cat in enumerate(REPAIR_PRIORITY)}


def pick_best_error(errors: list[JavacError]) -> JavacError | None:
    """Pick the highest-priority error to fix first.
    
    Priority: syntax → imports → build config → resources → structure → symbols
    Within same priority: prefers error with file:line, then earliest file:line wins.
    """
    if not errors:
        return None
    best = None
    best_rank = 999
    for err in errors:
        rank = _CATEGORY_RANK.get(err.category, 999)
        # Prefer errors with a valid file path
        has_file = bool(err.file)
        if best is None:
            best = err
            best_rank = rank
            continue
        if has_file and not best.file:
            best = err
            best_rank = rank
        elif not has_file and best.file:
            continue
        elif rank < best_rank:
            best = err
            best_rank = rank
        elif rank == best_rank:
            if (err.file, err.line) < (best.file, best.line):
                best = err
    return best


# ── Repair Chain ─────────────────────────────────────────────────────


class RepairChain:
    """Iterative repair chaining.
    
    Usage:
        engine = CompilerRepairEngine(project_root, pattern_memory)
        chain = RepairChain(engine, project_root)
        result = await chain.run(build_output, build_command=["cmd", "/c", "gradlew.bat", "assembleDebug"])
    """

    def __init__(
        self,
        engine: CompilerRepairEngine,
        project_root: str,
        max_iterations: int = 25,
        max_no_progress_count: int = 2,
    ):
        self.engine = engine
        self.project_root = project_root
        self.max_iterations = max_iterations
        self.max_no_progress_count = max_no_progress_count
        self.metrics = ChainMetrics()

    async def run(
        self,
        build_output: str | None = None,
        build_command: list[str] | None = None,
        rebuild_fn: Callable[[], tuple[bool, str]] | None = None,
    ) -> ChainResult:
        """Run the repair chain.
        
        Args:
            build_output: Initial build output. If None, runs build_command.
            build_command: Shell command to rebuild the project.
            rebuild_fn: Alternative to build_command — a callable that returns
                       (success_bool, output_string). Used for testing.
        """
        self.metrics.start_time = datetime.now().isoformat()
        start_total = time.time()

        # Initial build
        current_output = build_output or ""
        if not current_output and build_command:
            current_output = self._run_build(build_command)
        elif not current_output and rebuild_fn:
            _, current_output = rebuild_fn()

        seen_signatures: list[str] = []
        no_progress_count = 0
        prev_error_count = 0

        for iteration in range(1, self.max_iterations + 1):
            iter_start = time.time()

            # Parse
            errors = self.engine.parse_errors(current_output)
            current_error_count = len(errors)

            snapshot = IterationSnapshot(
                iteration=iteration,
                error_count=current_error_count,
                categories=list(set(e.category for e in errors)),
            )

            # SUCCESS: no errors
            if current_error_count == 0:
                snapshot.duration_ms = (time.time() - iter_start) * 1000
                self.metrics.per_iteration.append(snapshot)
                self.metrics.end_time = datetime.now().isoformat()
                self.metrics.total_duration_ms = (time.time() - start_total) * 1000
                return ChainResult(
                    success=True,
                    total_iterations=iteration,
                    total_fixes_applied=sum(
                        1 for s in self.metrics.per_iteration if s.fix_success
                    ),
                    final_error_count=0,
                    final_errors=[],
                    metrics=self.metrics,
                    stop_reason="all_errors_resolved",
                )

            # Pick best error
            error = pick_best_error(errors)
            if error is None:
                snapshot.duration_ms = (time.time() - iter_start) * 1000
                self.metrics.per_iteration.append(snapshot)
                break

            # SAFETY: loop detection
            sig = error_signature(errors)
            if sig in seen_signatures[-3:]:
                self.metrics.loop_detections += 1
                self.metrics.end_time = datetime.now().isoformat()
                self.metrics.total_duration_ms = (time.time() - start_total) * 1000
                return ChainResult(
                    success=False,
                    total_iterations=iteration,
                    total_fixes_applied=0,
                    final_error_count=current_error_count,
                    final_errors=errors,
                    metrics=self.metrics,
                    stop_reason=f"loop_detected: same error set seen 3+ times (category={error.category})",
                )
            seen_signatures.append(sig)

            # SAFETY: no progress
            if current_error_count >= prev_error_count and iteration > 1:
                no_progress_count += 1
            else:
                no_progress_count = 0
            prev_error_count = current_error_count

            if no_progress_count >= self.max_no_progress_count:
                self.metrics.no_progress_detections += 1
                self.metrics.end_time = datetime.now().isoformat()
                self.metrics.total_duration_ms = (time.time() - start_total) * 1000
                return ChainResult(
                    success=False,
                    total_iterations=iteration,
                    total_fixes_applied=sum(
                        1 for s in self.metrics.per_iteration if s.fix_success
                    ),
                    final_error_count=current_error_count,
                    final_errors=errors,
                    metrics=self.metrics,
                    stop_reason=f"no_progress: error count not decreasing ({current_error_count} >= {prev_error_count})",
                )

            # Apply fix with rollback
            rollback_snapshot = FileSnapshot()
            rollback_snapshot.snapshot_directory(self.project_root, ".java")
            rollback_snapshot.snapshot_directory(self.project_root, ".xml")
            rollback_snapshot.snapshot_directory(self.project_root, ".gradle")

            # Fix one error
            action = await self.engine._repair_one(error, self.project_root, "")
            snapshot.fix_applied = action.action
            snapshot.fix_category = error.category
            snapshot.fix_success = action.success
            logger.debug("iter %d: fix %s on %s (file=%s, line=%d) success=%s",
                         iteration, action.action, error.category,
                         error.file, error.line, str(action.success))

            if action.success:
                self.metrics.deterministic_repairs += 1
                self.metrics.errors_fixed += 1

            # Rebuild (always run, even on failure — gives simulation a chance to advance)
            if build_command:
                rebuild_ok, new_output = self._run_build(build_command)
                new_output_str = new_output if isinstance(new_output, str) else (new_output[1] if isinstance(new_output, tuple) else "")
            elif rebuild_fn:
                rebuild_ok, new_output_str = rebuild_fn()
            else:
                rebuild_ok, new_output_str = False, ""

            if new_output_str:
                self.metrics.builds_run += 1
                new_errors = self.engine.parse_errors(new_output_str)
                new_count = len(new_errors)
                snapshot.error_delta = new_count - current_error_count

                # ROLLBACK: if errors increased and fix claimed success
                if action.success and new_count >= current_error_count and iteration > 1:
                    restored = rollback_snapshot.rollback()
                    self.metrics.rollbacks += 1
                    snapshot.rolled_back = True
                    self.metrics.errors_introduced += max(0, new_count - current_error_count)
                    logger.info(
                        "Rollback: errors %d→%d after %s fix on %s. Restored %d files.",
                        current_error_count, new_count, action.action,
                        error.category, len(restored),
                    )
                    # Rebuild after rollback
                    if build_command:
                        _, current_output = self._run_build(build_command)
                    elif rebuild_fn:
                        _, current_output = rebuild_fn()
                    else:
                        current_output = new_output_str
                else:
                    # Fix accepted (or fix failed — advance simulation anyway)
                    current_output = new_output_str
                    if action.success and self.engine._pattern_memory:
                        self.engine._pattern_memory.record_success(
                            error.message,
                            f"{action.action}:{error.category}",
                        )

            if not action.success and self.engine._pattern_memory:
                self.engine._pattern_memory.record_failure(
                    error.message,
                    f"{action.action}:{error.category}",
                )

            snapshot.duration_ms = (time.time() - iter_start) * 1000
            self.metrics.per_iteration.append(snapshot)

        # Exhausted iterations
        final_errors = self.engine.parse_errors(current_output)
        self.metrics.end_time = datetime.now().isoformat()
        self.metrics.total_duration_ms = (time.time() - start_total) * 1000
        return ChainResult(
            success=False,
            total_iterations=self.max_iterations,
            total_fixes_applied=sum(
                1 for s in self.metrics.per_iteration if s.fix_success
            ),
            final_error_count=len(final_errors),
            final_errors=final_errors,
            metrics=self.metrics,
            stop_reason=f"max_iterations_reached ({self.max_iterations})",
        )

    def _run_build(self, command: list[str]) -> tuple[bool, str]:
        """Run a build command and capture output."""
        import subprocess
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=300,
            )
            output = result.stdout + "\n" + result.stderr
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "BUILD TIMEOUT"
        except Exception as e:
            return False, f"BUILD ERROR: {e}"
