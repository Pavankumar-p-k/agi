"""StructuralTransformationEngine — type-mismatch, parameter, and API contract repair.

Pipeline:
  Compiler Error
       ↓
  Type Analysis (source_type, target_type, context)
       ↓
  Transformation Rule (parseInt, valueOf, cast...)
       ↓
  Patch (line-level source edit)
       ↓
  Rebuild

Works with the existing CompilerRepairEngine and RepairChain.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Callable

logger = logging.getLogger(__name__)

# ── Type Conversion Rules ───────────────────────────────────────────
# Maps (source_type, target_type) → (wrapper_expr_template, needs_import, import_line)

ConversionRule = tuple[str, bool, str]  # (expression_template, needs_import, import_line)

_TYPE_CONVERSIONS: dict[tuple[str, str], ConversionRule] = {
    # String → numeric
    ("String", "int"):     ('Integer.parseInt({expr})', True, 'import java.lang.Integer;'),
    ("String", "Integer"): ('Integer.parseInt({expr})', True, ''),
    ("String", "long"):    ('Long.parseLong({expr})', True, ''),
    ("String", "Long"):    ('Long.parseLong({expr})', True, ''),
    ("String", "float"):   ('Float.parseFloat({expr})', True, ''),
    ("String", "Float"):   ('Float.parseFloat({expr})', True, ''),
    ("String", "double"):  ('Double.parseDouble({expr})', True, ''),
    ("String", "Double"):  ('Double.parseDouble({expr})', True, ''),
    ("String", "boolean"): ('Boolean.parseBoolean({expr})', False, ''),
    ("String", "Boolean"): ('Boolean.parseBoolean({expr})', False, ''),
    # Primitive → String
    ("int", "String"):     ('String.valueOf({expr})', False, ''),
    ("long", "String"):    ('String.valueOf({expr})', False, ''),
    ("float", "String"):   ('String.valueOf({expr})', False, ''),
    ("double", "String"):  ('String.valueOf({expr})', False, ''),
    ("boolean", "String"): ('String.valueOf({expr})', False, ''),
    ("int", "int"):        ('({expr})', False, ''),  # same type, no change
    # Numeric widening/narrowing
    ("int", "long"):       ('(long) {expr}', False, ''),
    ("long", "int"):       ('(int) {expr}', False, ''),
    ("int", "double"):     ('(double) {expr}', False, ''),
    ("double", "int"):     ('(int) {expr}', False, ''),
    ("int", "float"):      ('(float) {expr}', False, ''),
    ("float", "int"):      ('(int) {expr}', False, ''),
    ("long", "double"):    ('(double) {expr}', False, ''),
    ("double", "long"):    ('(long) {expr}', False, ''),
    ("float", "double"):   ('(double) {expr}', False, ''),
    ("double", "float"):   ('(float) {expr}', False, ''),
    # Object → String
    ("Object", "String"):  ('String.valueOf({expr})', False, ''),
}

# Type normalization: map common alternative type spellings
_TYPE_ALIASES: dict[str, str] = {
    "java.lang.String": "String",
    "java.lang.Integer": "Integer",
    "java.lang.Boolean": "Boolean",
    "java.lang.Long": "Long",
    "java.lang.Float": "Float",
    "java.lang.Double": "Double",
    "java.lang.Object": "Object",
}


def normalize_type(t: str) -> str:
    t = t.strip()
    # Strip generics
    t = re.sub(r"<.*>", "", t)
    # Strip array brackets
    t = t.replace("[]", "")
    return _TYPE_ALIASES.get(t, t)


# ── Context Detection ──────────────────────────────────────────────

class TypeMismatchContext:
    """Classifies the context of a type mismatch error on a source line."""
    def __init__(self, line: str, error_line: int, lines: list[str]):
        self.line = line
        self.error_line = error_line
        self.lines = lines
        self.context_type = self._detect()

    def _detect(self) -> str:
        """Detect context: assignment, method_arg, return_stmt, parameter, other."""
        stripped = self.line.strip()
        if stripped.startswith("return "):
            return "return_stmt"
        if "=" in stripped and not stripped.strip().startswith("//"):
            return "assignment"
        if self._is_method_arg():
            return "method_arg"
        # Check if this line contains a method call (like foo(x))
        if re.search(r'\w+\s*\(', stripped):
            return "method_arg"
        return "other"

    def _is_method_arg(self) -> bool:
        """Check if the error is in a method argument position."""
        stripped = self.line.strip()
        return bool(re.search(r'\(\s*\w+', stripped))


def detect_context(line: str, error_line: int, lines: list[str]) -> str:
    return TypeMismatchContext(line, error_line, lines).context_type


# ── Expression Extraction ──────────────────────────────────────────

def extract_expression(line: str, context: str, source_type: str, target_type: str) -> str | None:
    """Extract the expression that needs conversion from the source line."""
    stripped = line.strip()

    if context == "return_stmt":
        m = re.search(r"return\s+(.+);", stripped)
        return m.group(1).strip() if m else None

    if context == "assignment":
        parts = stripped.split("=", 1)
        if len(parts) == 2:
            rhs = parts[1].strip().rstrip(";")
            return rhs
        return None

    if context == "method_arg":
        # Find the argument that likely needs conversion.
        # Prefer simple variable names over dotted references or literals.
        m = re.search(r'\(\s*([^)]+)\s*\)', stripped)
        if m:
            args = [a.strip() for a in m.group(1).split(",")]
            # Score each arg: prefer simple names (no dots, not literals)
            def _is_simple_var(a: str) -> bool:
                return bool(re.match(r'^[a-z_]\w*$', a)) and a not in ('new', 'null', 'true', 'false')
            for arg in args:
                if _is_simple_var(arg):
                    return arg
            # Fallback: return first non-constant arg
            for arg in args:
                if '.' not in arg and not re.match(r'^[\d"\']', arg):
                    return arg
            # Last resort: first arg
            return args[0] if args else None
        return None

    # Fallback: try to find any expression matching the source type pattern
    return stripped.rstrip(";").strip()


def extract_line_content(line: str) -> tuple[str, str]:
    """Split a source line into (indent, content)."""
    indent = line[:len(line) - len(line.lstrip())]
    return indent, line.strip()


# ── Patch Builder ──────────────────────────────────────────────────

def build_patch(line: str, expr: str, transformed: str, context: str) -> str | None:
    """Replace the original expression with the transformed one on the line."""
    if not expr or expr == transformed:
        return None
    if expr not in line:
        return None
    new_line = line.replace(expr, transformed, 1)
    return new_line if new_line != line else None


# ── Transformation Engine ──────────────────────────────────────────

class StructuralTransformationEngine:
    """Applies type-safe conversions to fix compilation errors.

    Handles:
      - Type mismatches (String→int via Integer.parseInt, etc.)
      - Parameter contract changes (int→String parameter type reversal)
      - Return type mismatches (wrapping return values)
    """

    def __init__(self):
        self._stats = {"attempted": 0, "succeeded": 0, "failed": 0}
        from brain.repair_modules.fix_imports import KNOWN_ANDROID_IMPORTS
        self._imports = KNOWN_ANDROID_IMPORTS

    def convert_type(self, source_type: str, target_type: str, expr: str) -> str | None:
        """Apply a type conversion rule to an expression.

        Args:
            source_type: The actual type (e.g., 'String')
            target_type: The expected type (e.g., 'int')
            expr: The expression string to wrap

        Returns:
            The transformed expression string, or None if no rule applies
        """
        normalized_src = normalize_type(source_type)
        normalized_tgt = normalize_type(target_type)

        rule = _TYPE_CONVERSIONS.get((normalized_src, normalized_tgt))
        if not rule:
            # Try reverse map (parameter/return context where types swap)
            rule = _TYPE_CONVERSIONS.get((normalized_tgt, normalized_src))

        if not rule:
            return None

        template, _, _ = rule
        return template.format(expr=expr)

    def fix_type_mismatch(self, error, root: str) -> bool:
        """Fix a type mismatch error by applying a type conversion."""
        self._stats["attempted"] += 1

        # Extract source and target types from error message
        m = re.search(r"incompatible types:\s*(\S+)\s*cannot be converted to\s*(\S+)",
                       error.message, re.I)
        if not m:
            self._stats["failed"] += 1
            return False

        source_type, target_type = m.group(1), m.group(2)

        # Find the source file
        if not error.file:
            self._stats["failed"] += 1
            return False

        full = os.path.join(root, error.file)
        if not os.path.exists(full):
            self._stats["failed"] += 1
            return False

        try:
            with open(full, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            self._stats["failed"] += 1
            return False

        if error.line < 1 or error.line > len(lines):
            self._stats["failed"] += 1
            return False

        line = lines[error.line - 1]
        indent, content = extract_line_content(line)

        # Detect context (assignment, method_arg, return, etc.)
        context = detect_context(line, error.line, lines)

        # Extract the expression that needs conversion
        expr = extract_expression(line, context, source_type, target_type)
        if not expr:
            self._stats["failed"] += 1
            return False

        # Try the conversion
        transformed = self.convert_type(source_type, target_type, expr)
        if not transformed:
            # Try swapping: maybe the error message had them reversed
            transformed = self.convert_type(target_type, source_type, expr)

        if not transformed:
            self._stats["failed"] += 1
            return False

        # Build and apply the patch
        new_line = build_patch(line, expr, transformed, context)
        if not new_line:
            self._stats["failed"] += 1
            return False

        try:
            lines[error.line - 1] = new_line
            with open(full, "w", encoding="utf-8") as f:
                f.writelines(lines)
            self._stats["succeeded"] += 1
            logger.info("[StructuralTransform] Fixed %s→%s conversion on %s:%d",
                        source_type, target_type, error.file or "", error.line)
            return True
        except Exception as e:
            logger.warning("[StructuralTransform] Failed to write fix: %s", e)
            self._stats["failed"] += 1
            return False

    def fix_return_type(self, error, root: str) -> bool:
        """Fix a return type mismatch."""
        return self.fix_type_mismatch(error, root)

    def fix_parameter_type(self, error, root: str) -> bool:
        """Fix a parameter type mismatch by adjusting the call site or declaration."""
        return self.fix_type_mismatch(error, root)

    def get_stats(self) -> dict:
        return dict(self._stats)
