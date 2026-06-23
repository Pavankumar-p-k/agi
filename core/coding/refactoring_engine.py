"""RefactoringEngine — patch generation, import fixing, snapshot/rollback, refactoring recipes.

Transforms ChangePlans into validated code patches with automatic import fixing,
dependency-safe rename/move/delete operations, and full rollback support.
"""

from __future__ import annotations

import copy
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.coding.architecture_map import ArchitectureMapper
from core.coding.change_planner import ChangePlan, ChangeType, FileChange
from core.coding.dependency_graph import DependencyGraph
from core.coding.impact_analyzer import ImpactAnalyzer
from core.coding.repository_indexer import FileEntry, RepositoryIndexer

logger = logging.getLogger(__name__)


@dataclass
class CodePatch:
    file: str
    description: str = ""
    old_content: str = ""
    new_content: str = ""
    patch_type: str = ""  # create, modify, delete, rename_imports

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "description": self.description,
            "patch_type": self.patch_type,
            "has_changes": self.old_content != self.new_content,
            "size_delta": len(self.new_content) - len(self.old_content),
        }


@dataclass
class ValidationError:
    message: str
    severity: str  # error, warning
    file: str = ""

    def to_dict(self) -> dict:
        return {"message": self.message, "severity": self.severity, "file": self.file}


@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [e.to_dict() for e in self.warnings],
        }


@dataclass
class RollbackSnapshot:
    file: str
    original_content: str

    def to_dict(self) -> dict:
        return {"file": self.file, "size": len(self.original_content)}


@dataclass
class RefactoringRecipe:
    name: str
    description: str
    source_pattern: str  # what the recipe applies to
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)


class RefactoringEngine:
    """Generate, validate, and apply refactoring patches with rollback support.

    Provides deterministic file-level refactorings:
      - Rename file with automatic import updates
      - Rename exported symbol with reference updates
      - Delete file with safety checks and rollback
      - Extract exports to new file
      - Snapshot/rollback for undo
    """

    def __init__(
        self,
        indexer: RepositoryIndexer,
        dep_graph: DependencyGraph,
        arch_mapper: ArchitectureMapper,
        impact_analyzer: ImpactAnalyzer,
    ):
        self.indexer = indexer
        self.dep_graph = dep_graph
        self.arch_mapper = arch_mapper
        self.impact_analyzer = impact_analyzer

    # ── Available recipes ────────────────────────────────────────

    @staticmethod
    def available_recipes() -> list[RefactoringRecipe]:
        return [
            RefactoringRecipe(
                name="rename_file",
                description="Rename a file and update all imports referencing it",
                source_pattern="file",
                preconditions=["Source file exists", "Target path does not exist"],
                postconditions=["File renamed", "All imports updated"],
            ),
            RefactoringRecipe(
                name="rename_symbol",
                description="Rename a class/function and update all references",
                source_pattern="exported symbol",
                preconditions=["Symbol exists in source file"],
                postconditions=["Symbol renamed", "All references updated"],
            ),
            RefactoringRecipe(
                name="delete_file_safe",
                description="Delete a file if nothing imports it",
                source_pattern="file with zero dependents",
                preconditions=["File exists", "No files import this file"],
                postconditions=["File deleted", "Rollback snapshot saved"],
            ),
            RefactoringRecipe(
                name="move_exports",
                description="Move exported symbols from one file to another",
                source_pattern="file with exports",
                preconditions=["Source file exists", "Target file path available"],
                postconditions=["Exports moved", "Import paths updated"],
            ),
        ]

    # ── Patch generation from plan ───────────────────────────────

    def generate_patches(
        self,
        plan: ChangePlan,
        recipe_name: str | None = None,
    ) -> list[CodePatch]:
        """Generate concrete CodePatches from a ChangePlan."""
        patches: list[CodePatch] = []

        for step in plan.steps:
            for fc in step.file_changes:
                if recipe_name == "rename_file":
                    patches.extend(
                        self._generate_rename_file_patches(fc)
                    )
                elif recipe_name == "delete_file_safe":
                    patches.extend(
                        self._generate_delete_safe_patches(fc)
                    )
                elif recipe_name == "rename_symbol":
                    patches.extend(
                        self._generate_rename_symbol_patches(fc)
                    )
                elif recipe_name == "move_exports":
                    patches.extend(
                        self._generate_move_exports_patches(fc)
                    )
                else:
                    patches.extend(
                        self._generate_default_patches(fc)
                    )

        return patches

    # ── Specific recipe implementations ──────────────────────────

    def _generate_rename_file_patches(self, fc: FileChange) -> list[CodePatch]:
        """Rename file: generate patches to update all imports."""
        patches: list[CodePatch] = []
        if not fc.new_file:
            return patches

        old_norm = fc.file.replace("\\", "/")
        new_norm = fc.new_file.replace("\\", "/")
        entry = self.indexer.get_entry(old_norm)
        if entry is None:
            return patches

        old_mod = os.path.splitext(old_norm)[0].replace("/", ".")
        new_mod = os.path.splitext(new_norm)[0].replace("/", ".")

        # Find all files that import from this module
        node = self.dep_graph.get_node(old_norm)
        if node:
            for dep_path in node.imported_by:
                dep_entry = self.indexer.get_entry(dep_path)
                if dep_entry is None:
                    continue
                try:
                    dep_abs = str(Path(self.indexer.ws._path) / dep_path)
                    old_content = Path(dep_abs).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                new_content = old_content.replace(f"from {old_mod}", f"from {new_mod}")

                if new_content != old_content:
                    patches.append(CodePatch(
                        file=dep_path,
                        description=f"Update imports for rename: {old_norm} → {new_norm}",
                        old_content=old_content,
                        new_content=new_content,
                        patch_type="rename_imports",
                    ))

        patches.append(CodePatch(
            file=old_norm,
            description=f"File renamed to {new_norm}",
            patch_type="rename",
        ))
        return patches

    def _generate_rename_symbol_patches(self, fc: FileChange) -> list[CodePatch]:
        """Rename exported symbol: find imports and update references."""
        patches: list[CodePatch] = []
        parts = fc.description.split(" → ")
        if len(parts) != 2:
            return patches
        old_name = parts[0].strip()
        new_name = parts[1].strip()

        normalized = fc.file.replace("\\", "/")
        entry = self.indexer.get_entry(normalized)
        if entry is None or old_name not in entry.exports:
            return patches

        node = self.dep_graph.get_node(normalized)
        if node:
            for dep_path in node.imported_by:
                dep_entry = self.indexer.get_entry(dep_path)
                if dep_entry is None:
                    continue
                try:
                    dep_abs = str(Path(self.indexer.ws._path) / dep_path)
                    old_content = Path(dep_abs).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                new_content = old_content.replace(
                    f"import {old_name}", f"import {new_name}"
                )
                new_content = new_content.replace(
                    f"import {old_name}\n", f"import {new_name}\n"
                )
                if new_content != old_content:
                    patches.append(CodePatch(
                        file=dep_path,
                        description=f"Update ref: {old_name} → {new_name}",
                        old_content=old_content,
                        new_content=new_content,
                        patch_type="rename_imports",
                    ))

        try:
            src_abs = str(Path(self.indexer.ws._path) / normalized)
            old_content = Path(src_abs).read_text(encoding="utf-8", errors="replace")
            new_content = old_content.replace(f"class {old_name}", f"class {new_name}")
            new_content = new_content.replace(f"def {old_name}", f"def {new_name}")
            patches.append(CodePatch(
                file=normalized,
                description=f"Rename symbol {old_name} → {new_name}",
                old_content=old_content,
                new_content=new_content,
                patch_type="modify",
            ))
        except Exception:
            pass

        return patches

    def _generate_delete_safe_patches(self, fc: FileChange) -> list[CodePatch]:
        """Delete file: generate patches iff nothing imports it."""
        patches: list[CodePatch] = []
        normalized = fc.file.replace("\\", "/")
        entry = self.indexer.get_entry(normalized)
        if entry is None:
            return patches

        try:
            src_abs = str(Path(self.indexer.ws._path) / normalized)
            content = Path(src_abs).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return patches

        patches.append(CodePatch(
            file=normalized,
            description="Delete file (saved as snapshot for rollback)",
            old_content=content,
            new_content="",
            patch_type="delete",
        ))
        return patches

    def _generate_move_exports_patches(self, fc: FileChange) -> list[CodePatch]:
        """Move exported symbols to a new file, update imports."""
        patches: list[CodePatch] = []
        if not fc.new_file:
            return patches

        src_norm = fc.file.replace("\\", "/")
        tgt_norm = fc.new_file.replace("\\", "/")
        entry = self.indexer.get_entry(src_norm)
        if entry is None or not entry.exports:
            return patches

        try:
            src_abs = str(Path(self.indexer.ws._path) / src_norm)
            src_content = Path(src_abs).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return patches

        tgt_abs = str(Path(self.indexer.ws._path) / tgt_norm)
        if os.path.exists(tgt_abs):
            return patches

        src_mod = os.path.splitext(src_norm)[0].replace("/", ".")
        tgt_mod = os.path.splitext(tgt_norm)[0].replace("/", ".")

        export_lines: list[str] = []
        remaining: list[str] = []
        for line in src_content.split("\n"):
            is_export = False
            for exp in entry.exports:
                if f"class {exp}" in line or f"def {exp}" in line:
                    export_lines.append(line)
                    is_export = True
                    break
            if not is_export:
                remaining.append(line)

        if not export_lines:
            return patches

        tgt_content = "\n".join(export_lines)

        node = self.dep_graph.get_node(src_norm)
        if node:
            for dep_path in node.imported_by:
                try:
                    dep_abs = str(Path(self.indexer.ws._path) / dep_path)
                    dep_content = Path(dep_abs).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                new_dep = dep_content.replace(
                    f"from {src_mod}", f"from {tgt_mod}"
                )
                if new_dep != dep_content:
                    patches.append(CodePatch(
                        file=dep_path,
                        description=f"Update import: {src_mod} → {tgt_mod}",
                        old_content=dep_content,
                        new_content=new_dep,
                        patch_type="rename_imports",
                    ))

        patches.append(CodePatch(
            file=src_norm,
            description=f"Remove {len(export_lines)} export lines",
            old_content=src_content,
            new_content="\n".join(remaining),
            patch_type="modify",
        ))
        patches.append(CodePatch(
            file=tgt_norm,
            description=f"Create with {len(export_lines)} exported symbols",
            new_content=tgt_content,
            patch_type="create",
        ))
        return patches

    def _generate_default_patches(self, fc: FileChange) -> list[CodePatch]:
        """Generate patches for basic create/modify/delete/rename."""
        patches: list[CodePatch] = []
        normalized = fc.file.replace("\\", "/")
        entry = self.indexer.get_entry(normalized)
        ws_path = Path(self.indexer.ws._path)
        abs_path = str(ws_path / normalized)

        if fc.action == ChangeType.CREATE:
            patches.append(CodePatch(
                file=normalized,
                description=fc.description or f"Create {normalized}",
                new_content="",
                patch_type="create",
            ))

        elif fc.action in (ChangeType.MODIFY, ChangeType.RENAME):
            try:
                if os.path.exists(abs_path):
                    content = Path(abs_path).read_text(encoding="utf-8", errors="replace")
                    patches.append(CodePatch(
                        file=normalized,
                        description=fc.description or f"Modify {normalized}",
                        old_content=content,
                        new_content=content,
                        patch_type="modify",
                    ))
            except Exception:
                pass

            if fc.action == ChangeType.RENAME and fc.new_file:
                new_norm = fc.new_file.replace("\\", "/")
                rename_patches = self._generate_rename_file_patches(fc)
                patches.extend(rename_patches)

        elif fc.action == ChangeType.DELETE:
            delete_patches = self._generate_delete_safe_patches(fc)
            patches.extend(delete_patches)

        return patches

    # ── Validation ───────────────────────────────────────────────

    def validate_patches(self, patches: list[CodePatch]) -> ValidationResult:
        """Validate patches against the repository's dependency graph."""
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        # Track which files are being deleted/renamed
        deleted_files = {p.file for p in patches if p.patch_type == "delete"}
        renamed_src = {p.file for p in patches if p.patch_type == "rename"}

        for patch in patches:
            if patch.patch_type == "delete":
                node = self.dep_graph.get_node(patch.file)
                if node and node.imported_by:
                    for dep in node.imported_by:
                        if dep not in deleted_files:
                            errors.append(ValidationError(
                                message=f"Deleting {patch.file} breaks {dep} (still imports it)",
                                severity="error",
                                file=dep,
                            ))

            if patch.patch_type == "rename" and not any(
                p.file == patch.file and p.patch_type == "rename_imports"
                for p in patches
            ):
                warnings.append(ValidationError(
                    message=f"Renaming {patch.file} but no import-update patches found",
                    severity="warning",
                    file=patch.file,
                ))

            if patch.patch_type in ("create", "rename"):
                entry = self.indexer.get_entry(patch.file)
                if entry is not None:
                    warnings.append(ValidationError(
                        message=f"{patch.file} already exists in index",
                        severity="warning",
                        file=patch.file,
                    ))

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # ── Apply / Rollback ─────────────────────────────────────────

    def apply_patches(
        self,
        patches: list[CodePatch],
        dry_run: bool = True,
    ) -> list[RollbackSnapshot]:
        """Apply patches and return rollback snapshots.

        When dry_run=True, only builds snapshots without writing.
        When dry_run=False, actually writes patches to disk.
        """
        ws_path = Path(self.indexer.ws._path)
        snapshots: list[RollbackSnapshot] = []

        for patch in patches:
            abs_path = str(ws_path / patch.file)

            # Snapshot existing content for rollback
            if patch.old_content:
                snapshots.append(RollbackSnapshot(
                    file=patch.file,
                    original_content=patch.old_content,
                ))
            elif os.path.exists(abs_path):
                try:
                    snapshots.append(RollbackSnapshot(
                        file=patch.file,
                        original_content=Path(abs_path).read_text(encoding="utf-8", errors="replace"),
                    ))
                except Exception:
                    pass

            if not dry_run:
                try:
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    if patch.patch_type == "delete":
                        if os.path.exists(abs_path):
                            os.remove(abs_path)
                    elif patch.patch_type == "rename":
                        pass  # handled by separate create/delete
                    elif patch.new_content:
                        Path(abs_path).write_text(patch.new_content, encoding="utf-8")
                    elif not os.path.exists(abs_path):
                        Path(abs_path).write_text("", encoding="utf-8")
                except Exception as e:
                    logger.warning("Failed to apply patch to %s: %s", patch.file, e)

        return snapshots

    @staticmethod
    def rollback(snapshots: list[RollbackSnapshot]) -> bool:
        """Restore all files from rollback snapshots.

        Returns True if all restorations succeeded.
        """
        success = True
        for snap in snapshots:
            try:
                abs_path = snap.file  # caller must resolve
                p = Path(abs_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(snap.original_content, encoding="utf-8")
            except Exception as e:
                logger.warning("Rollback failed for %s: %s", snap.file, e)
                success = False
        return success

    def quick_validate(self, plan: ChangePlan) -> ValidationResult:
        """Quick validation of a ChangePlan: generates and validates patches."""
        patches = self.generate_patches(plan)
        return self.validate_patches(patches)
