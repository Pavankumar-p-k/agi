"""StructuralTransformer — repairs Java type mismatches structurally.

The old repair strategy cast the value (``(int) hour``), which is invalid for
``String`` → ``int``. This engine instead parses the compiler message, detects
the expression context (return / assignment / method argument) and rewrites the
expression with the correct real conversion (``Integer.parseInt(hour)``).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Type conversions ─────────────────────────────────────────────────────
# ``{expr}`` is substituted with the offending expression.
_TYPE_CONVERSIONS: dict[tuple[str, str], str] = {
    ("String", "int"): "Integer.parseInt({expr})",
    ("String", "long"): "Long.parseLong({expr})",
    ("String", "double"): "Double.parseDouble({expr})",
    ("String", "float"): "Float.parseFloat({expr})",
    ("String", "boolean"): "Boolean.parseBoolean({expr})",
    ("String", "short"): "Short.parseShort({expr})",
    ("String", "byte"): "Byte.parseByte({expr})",
    ("int", "String"): "String.valueOf({expr})",
    ("long", "String"): "String.valueOf({expr})",
    ("double", "String"): "String.valueOf({expr})",
    ("float", "String"): "String.valueOf({expr})",
    ("boolean", "String"): "String.valueOf({expr})",
    ("char", "String"): "String.valueOf({expr})",
    ("Object", "String"): "String.valueOf({expr})",
    ("int", "long"): "(long) {expr}",
    ("int", "double"): "(double) {expr}",
    ("int", "float"): "(float) {expr}",
    ("long", "int"): "(int) {expr}",
    ("double", "int"): "(int) {expr}",
    ("float", "int"): "(int) {expr}",
}

# Boxed types behave like their primitive counterparts.
_PRIMITIVE_ALIAS: dict[str, str] = {
    "Integer": "int",
    "Long": "long",
    "Double": "double",
    "Float": "float",
    "Boolean": "boolean",
    "Character": "char",
    "Short": "short",
    "Byte": "byte",
}

_TYPE_MESSAGE_RE = re.compile(
    r"incompatible types:\s*([^\s]+)\s+cannot be converted to\s+([^\s.]+)")
_RETURN_RE = re.compile(r"return\s+(.+?);\s*$")
_ASSIGNMENT_RE = re.compile(r"^[\w][\w\s<>\[\],\.]*?\s*=(?!=)")


def normalize_type(type_name: str) -> str:
    """Strip ``java.lang.``, generic parameters and array brackets."""
    value = str(type_name or "").strip()
    if not value:
        return ""
    while value.endswith("[]"):
        value = value[:-2].strip()
    generic = value.find("<")
    if generic != -1:
        value = value[:generic]
    if value.startswith("java.lang."):
        value = value[len("java.lang."):]
    return value.strip()


def detect_context(line: str, lineno: int, lines: list) -> str:
    """Classify the statement type of *line*: return/assignment/method_arg/other."""
    stripped = (line or "").strip()
    if not stripped:
        return "other"
    if stripped.startswith("return") and ";" in stripped:
        return "return_stmt"
    if _ASSIGNMENT_RE.match(stripped) and not stripped.startswith(
            ("if", "while", "for", "switch", "assert")):
        return "assignment"
    if "(" in stripped and ")" in stripped and stripped.endswith(";"):
        return "method_arg"
    return "other"


def _split_args(stripped: str) -> list:
    """Split the argument list of a call, respecting nesting and strings."""
    start = stripped.find("(")
    end = stripped.rfind(")")
    if start == -1 or end == -1 or end < start:
        return []
    inner = stripped[start + 1:end]
    if not inner.strip():
        return []
    parts: list[str] = []
    depth = 0
    current = ""
    in_string = False
    escaped = False
    for char in inner:
        if in_string:
            current += char
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            current += char
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
            continue
        current += char
    if current.strip():
        parts.append(current.strip())
    return parts


def extract_expression(line: str, context: str, src_type: str,
                       tgt_type: str) -> Optional[str]:
    """Extract the expression to convert from *line* for the given context."""
    stripped = (line or "").strip()
    if context == "return_stmt":
        match = _RETURN_RE.search(stripped)
        return match.group(1).strip() if match else None
    if context == "assignment":
        if "=" not in stripped:
            return None
        rhs = stripped.split("=", 1)[1].strip().rstrip(";").strip()
        return rhs or None
    if context == "method_arg":
        args = _split_args(stripped)
        if not args:
            return None
        if normalize_type(src_type) == "String":
            for arg in args:
                if arg.startswith('"') and arg.endswith('"'):
                    return arg
        return args[0]
    return stripped.rstrip(";") or None


def build_patch(line: str, old_expr: str, new_expr: str, context: str) -> Optional[str]:
    """Rewrite *line* replacing *old_expr* with *new_expr* (or None if no-op)."""
    if not old_expr or not line:
        return None
    if not new_expr or new_expr == old_expr:
        return None
    if old_expr not in line:
        return None
    return line.replace(old_expr, new_expr, 1)


class StructuralTransformationEngine:
    """Applies structural rewrites to fix Java compiler type mismatches."""

    def __init__(self) -> None:
        self._stats = {"attempted": 0, "succeeded": 0, "failed": 0}

    # ── stats ────────────────────────────────────────────────────────
    def get_stats(self) -> dict:
        return dict(self._stats)

    # ── type conversion ──────────────────────────────────────────────
    def convert_type(self, src: str, tgt: str, expr: str) -> Optional[str]:
        """Return *expr* converted from *src* to *tgt*, or None if unsupported."""
        source = normalize_type(src)
        target = normalize_type(tgt)
        if not source or not target:
            return None
        template = _TYPE_CONVERSIONS.get((source, target))
        if template is None:
            source = _PRIMITIVE_ALIAS.get(source, source)
            target = _PRIMITIVE_ALIAS.get(target, target)
            template = _TYPE_CONVERSIONS.get((source, target))
        if template is None:
            if source == target:
                template = "({expr})"
            else:
                return None
        return template.format(expr=expr)

    # ── repair ───────────────────────────────────────────────────────
    def fix_type_mismatch(self, error: Any, project_root: str = ".") -> bool:
        """Fix one ``type_mismatch`` error in place; returns True on success."""
        self._stats["attempted"] += 1
        try:
            applied = self._apply(error, project_root)
        except Exception as exc:  # noqa: BLE001 — repair must never raise
            logger.debug("[transformer] fix failed: %s", exc)
            applied = False
        self._stats["succeeded" if applied else "failed"] += 1
        return applied

    def _apply(self, error: Any, project_root: str) -> bool:
        path = str(getattr(error, "file", "") or "")
        if not path:
            return False
        if not os.path.isabs(path):
            path = os.path.join(project_root or ".", path)
        if not os.path.isfile(path):
            return False

        message = str(getattr(error, "message", "") or "")
        match = _TYPE_MESSAGE_RE.search(message)
        if not match:
            return False
        src_type, tgt_type = match.group(1), match.group(2)

        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()

        line_no = int(getattr(error, "line", 0) or 0)
        if line_no < 1 or line_no > len(lines):
            return False
        index = line_no - 1
        line = lines[index]

        context = detect_context(line, line_no, lines)
        expr = self._extract_expr(error, line, context, src_type, tgt_type)
        if not expr:
            return False

        new_expr = self.convert_type(src_type, tgt_type, expr)
        if new_expr is None:
            return False

        patched = build_patch(line, expr, new_expr, context)
        if patched is None or patched == line:
            return False

        lines[index] = patched
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        logger.info("[transformer] fixed %s:%s (%s → %s)",
                    path, line_no, src_type, tgt_type)
        return True

    @staticmethod
    def _extract_expr(error: Any, line: str, context: str,
                      src_type: str, tgt_type: str) -> Optional[str]:
        symbol = str(getattr(error, "symbol", "") or "")
        if context == "method_arg" and symbol:
            for arg in _split_args(line.strip()):
                if arg == symbol:
                    return symbol
            # The symbol may be the method name; the offending argument is then
            # whichever argument actually holds the source-typed value.
        return extract_expression(line, context, src_type, tgt_type)


structural_transformer = StructuralTransformationEngine()


__all__ = [
    "StructuralTransformationEngine",
    "structural_transformer",
    "normalize_type",
    "detect_context",
    "extract_expression",
    "build_patch",
    "_TYPE_CONVERSIONS",
]
