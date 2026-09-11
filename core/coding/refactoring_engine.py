"""Safe refactoring primitives used by Coding AI."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.coding.change_planner import ChangePlan, ChangeType, FileChange


@dataclass
class RefactoringRecipe:
    name: str
    description: str
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodePatch:
    file: str
    description: str = ""
    old_content: str | None = None
    new_content: str | None = None
    patch_type: str = "modify"

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "description": self.description,
            "patch_type": self.patch_type,
            "has_changes": self.old_content != self.new_content,
        }


@dataclass
class ValidationError:
    message: str
    severity: str = "error"
    file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [error.to_dict() for error in self.errors],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass
class RollbackSnapshot:
    file: str
    original_content: str | None = None
    existed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "size": len(self.original_content or ""), "existed": self.existed}


class RefactoringEngine:
    def __init__(self, indexer, dependency_graph, architecture, impact_analyzer):
        self.indexer = indexer
        self.dependency_graph = dependency_graph
        self.architecture = architecture
        self.impact_analyzer = impact_analyzer

    @staticmethod
    def available_recipes() -> list[RefactoringRecipe]:
        return [
            RefactoringRecipe("rename_file", "Rename a file and update direct Python imports", ["source exists", "new path set"], ["imports updated"]),
            RefactoringRecipe("delete_file_safe", "Delete a file with dependency warnings", ["source exists"], ["snapshot captured"]),
            RefactoringRecipe("move_exports", "Move exports between files when possible", ["source and destination known"], ["imports reviewed"]),
            RefactoringRecipe("rename_symbol", "Rename a symbol inside a file", ["symbol found"], ["references reviewed"]),
        ]

    def _read(self, file: str) -> str | None:
        path = self.indexer.root / file
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8", errors="ignore")

    def _module_name(self, file: str) -> str:
        value = file[:-3] if file.endswith(".py") else file
        return value.replace("/", ".")

    def generate_patches(self, plan: ChangePlan, recipe_name: str | None = None) -> list[CodePatch]:
        patches: list[CodePatch] = []
        for change in plan.changes:
            if recipe_name == "rename_file" or change.change_type == ChangeType.RENAME:
                patches.extend(self._generate_rename_file_patches(change))
            elif recipe_name == "delete_file_safe" or change.change_type == ChangeType.DELETE:
                old = self._read(change.file)
                if old is not None:
                    patches.append(CodePatch(change.file, change.description, old, "", "delete"))
            elif change.change_type == ChangeType.CREATE:
                patches.append(CodePatch(change.file, change.description, None, "# TODO: implement\n", "create"))
            else:
                old = self._read(change.file)
                if old is not None:
                    patches.append(CodePatch(change.file, change.description, old, old + "\n# TODO: " + change.description + "\n", "modify"))
        return patches

    def _generate_rename_file_patches(self, change: FileChange) -> list[CodePatch]:
        if not change.new_file:
            return []
        old = self._read(change.file)
        if old is None:
            return []
        patches = [CodePatch(change.file, change.description, old, None, "rename")]
        old_module = self._module_name(change.file)
        new_module = self._module_name(change.new_file)
        for dependent in self.dependency_graph.impact_set([change.file]):
            content = self._read(dependent)
            if content and old_module in content:
                patches.append(CodePatch(dependent, f"Update imports for {change.file}", content, content.replace(old_module, new_module), "rename_imports"))
        return patches

    def validate_patches(self, patches: list[CodePatch]) -> ValidationResult:
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []
        for patch in patches:
            exists = (self.indexer.root / patch.file).exists()
            if patch.patch_type in {"modify", "delete", "rename"} and not exists:
                errors.append(ValidationError("target file does not exist", "error", patch.file))
            if patch.patch_type == "create" and exists:
                warnings.append(ValidationError("create would overwrite existing file", "warning", patch.file))
            if patch.patch_type == "delete" and self.dependency_graph.impact_set([patch.file]):
                warnings.append(ValidationError("delete affects dependent files", "warning", patch.file))
        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def apply_patches(self, patches: list[CodePatch], dry_run: bool = True) -> list[RollbackSnapshot]:
        snapshots: list[RollbackSnapshot] = []
        for patch in patches:
            path = self.indexer.root / patch.file
            original = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else None
            snapshots.append(RollbackSnapshot(patch.file, original, path.exists()))
            if dry_run:
                continue
            if patch.patch_type == "delete":
                if path.exists():
                    path.unlink()
            elif patch.new_content is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(patch.new_content, encoding="utf-8")
        return snapshots
