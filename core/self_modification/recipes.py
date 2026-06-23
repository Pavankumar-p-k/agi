"""Self-Modification Engine (Phase 18.0) — predefined transformation recipes.

Each recipe is a registered function that transforms source code in a
known, safe, deterministic way. No arbitrary code generation.

Recipe contract:
  - Input: target + optional parameters
  - Output: list[CodePatch] (or empty for registry-only changes)
  - Must NOT write files directly — returns patches for the executor
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.self_modification.models import ModificationRecipe, ModificationTarget

logger = logging.getLogger(__name__)

# ── Recipe Registry ───────────────────────────────────────────────────
# Maps recipe enum -> (apply_fn, description, applicability_fn)

_RECIPE_REGISTRY: dict[str, dict[str, Any]] = {}

AWAY = object()


def register_recipe(
    recipe: ModificationRecipe,
    description: str,
    config_schema: dict[str, type] | None = None,
):
    """Decorator to register a recipe function."""

    def decorator(fn):
        _RECIPE_REGISTRY[recipe.value] = {
            "fn": fn,
            "description": description,
            "recipe": recipe,
            "config_schema": config_schema or {},
        }
        return fn

    return decorator


def get_registered_recipes() -> dict[str, dict[str, Any]]:
    return dict(_RECIPE_REGISTRY)


def get_recipe(recipe: ModificationRecipe) -> dict[str, Any] | None:
    return _RECIPE_REGISTRY.get(recipe.value)


def apply_recipe(
    recipe: ModificationRecipe,
    target: ModificationTarget,
) -> list[dict[str, Any]]:
    """Apply a named recipe and return CodePatch-compatible dicts.

    Each dict has keys: file, old_content, new_content, patch_type, description.
    """
    entry = _RECIPE_REGISTRY.get(recipe.value)
    if entry is None:
        raise ValueError(f"Unknown recipe: {recipe.value}")
    return entry["fn"](target)


# ── Individual Recipe Implementations ─────────────────────────────────

_RETRY_TEMPLATE = """
    max_attempts = {retry_count}
    for attempt in range(max_attempts):
        try:
            return _original_impl({params})
        except Exception as _mod_err:
            if attempt == max_attempts - 1:
                raise
            logger.warning("Retry %s (%d/%d): %s", {name_repr!r}, attempt + 1, max_attempts, _mod_err)
""".lstrip()


@register_recipe(
    ModificationRecipe.ADD_RETRY_LOOP,
    description="Wrap a tool function body in a retry loop (max 3 attempts). "
    "Adds retry logic with logging. Requires the function to have a "
    "simple 'return func(args)' pattern as its last statement.",
    config_schema={"retry_count": int},
)
def _apply_add_retry_loop(target: ModificationTarget) -> list[dict[str, Any]]:
    """Wrap the last return statement of the target function in a retry loop.

    Transforms:
        def my_tool(args):
            setup()
            return do_work(args)

    Into:
        def my_tool(args):
            setup()
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    return do_work(args)
                except Exception as _mod_err:
                    if attempt == max_attempts - 1:
                        raise
                    logger.warning(...)
    """
    retry_count = target.extra_params.get("retry_count", 3)
    fn_name = target.target_function
    if not fn_name:
        raise ValueError("add_retry_loop requires target_function")

    return _wrap_last_return(
        target_file=target.target_file,
        function_name=fn_name,
        wrapper=lambda params, name_repr: _RETRY_TEMPLATE.format(
            retry_count=retry_count, params=params, name_repr=name_repr
        ),
        anchor_text=target.anchor_text,
    )


@register_recipe(
    ModificationRecipe.ADD_VERIFICATION_STEP,
    description="Add a post-execution verification call after the primary "
    "operation. Checks the result and logs/raises if invalid.",
)
def _apply_add_verification_step(target: ModificationTarget) -> list[dict[str, Any]]:
    """Add `_verify_result(result)` after the main return.

    The target file must have the verification function or it will be
    skipped. This recipe only inserts the call — it does not create
    the verification function.
    """
    fn_name = target.target_function
    if not fn_name:
        raise ValueError("add_verification_step requires target_function")

    return _wrap_last_return(
        target_file=target.target_file,
        function_name=fn_name,
        wrapper=lambda params, name_repr: (
            f"    result = _original_impl({params})\n"
            f'    if not _verify_result(result):\n'
            f'        logger.warning("Verification failed for {name_repr}")\n'
            f"    return result\n"
        ),
        anchor_text=target.anchor_text,
    )


@register_recipe(
    ModificationRecipe.INCREASE_TIMEOUT,
    description="Increase timeout constants/parameters in a module. "
    "Finds 'TIMEOUT = N' or 'timeout=N' patterns and increases the value.",
    config_schema={"multiplier": float, "min_value": float},
)
def _apply_increase_timeout(target: ModificationTarget) -> list[dict[str, Any]]:
    """Find and increase timeout values in the target file."""
    multiplier = target.extra_params.get("multiplier", 2.0)
    min_value = target.extra_params.get("min_value", 30.0)

    file_content = _read_file(target.target_file)

    patches: list[dict[str, Any]] = []

    # Pattern 1: TIMEOUT = <number> or TIMEOUT: int = <number>
    pattern1 = re.compile(r"(TIMEOUT\s*[=:]\s*)(\d+(?:\.\d+)?)")
    new_content, count1 = pattern1.subn(
        lambda m: m.group(1) + str(int(max(float(m.group(2)) * multiplier, min_value))),
        file_content,
    )
    if count1 > 0:
        patches.append(_make_patch(
            target.target_file,
            file_content,
            new_content,
            f"Increase TIMEOUT constant (×{multiplier})",
        ))

    # Pattern 2: timeout=<number> in function calls
    pattern2 = re.compile(r"(timeout\s*=\s*)(\d+(?:\.\d+)?)")
    new_content2, count2 = pattern2.subn(
        lambda m: m.group(1) + str(int(max(float(m.group(2)) * multiplier, min_value))),
        new_content if count1 > 0 else file_content,
    )

    if count2 > 0:
        patches.append(_make_patch(
            target.target_file,
            file_content,
            new_content2,
            f"Increase timeout= arguments (×{multiplier})",
        ))

    return patches


@register_recipe(
    ModificationRecipe.ENABLE_FAILURE_MEMORY,
    description="Wire PatternFailureMemory recording into a tool handler. "
    "Adds import and record_failure/record_success calls on error/success paths.",
)
def _apply_enable_failure_memory(target: ModificationTarget) -> list[dict[str, Any]]:
    """Add PatternFailureMemory recording to a function.

    Inserts:
      from core.pattern_failure_memory import PatternFailureMemory
    at the top of the file, and wraps the function to record outcomes.
    """
    fn_name = target.target_function
    if not fn_name:
        raise ValueError("enable_failure_memory requires target_function")

    file_content = _read_file(target.target_file)
    patches: list[dict[str, Any]] = []

    # Add import if not present
    import_line = "from core.pattern_failure_memory import PatternFailureMemory\n"
    if import_line.strip() not in file_content:
        # Insert after the last existing import
        import_match = re.search(r"^(import |from )", file_content, re.MULTILINE)
        if import_match:
            # Find the last import line
            lines = file_content.split("\n")
            last_import_idx = -1
            for i, line in enumerate(lines):
                if line.startswith(("import ", "from ")):
                    last_import_idx = i
            if last_import_idx >= 0:
                lines.insert(last_import_idx + 1, import_line.rstrip())
                new_content = "\n".join(lines)
                patches.append(_make_patch(
                    target.target_file,
                    file_content,
                    new_content,
                    f"Add PatternFailureMemory import to {target.target_file}",
                ))
                file_content = new_content

    # Wrap function to record outcomes
    # Find the function definition
    fn_pattern = re.compile(
        r"(def\s+" + re.escape(fn_name) + r"\s*\([^)]*\)\s*:\s*\n)"
        r"((?:(?!^\s*def\s).*\n?)*)",
        re.MULTILINE,
    )
    fn_match = fn_pattern.search(file_content)
    if fn_match:
        old_body = fn_match.group(0)
        indent = " " * 4

        recording_wrapper = (
            f"{indent}_memory = PatternFailureMemory()\n"
            f"{indent}_key = {fn_name!r}\n"
            f"{indent}try:\n"
        )

        # Indent the original body and wrap
        lines = old_body.split("\n")
        new_lines = [lines[0]]  # def line
        for line in lines[1:]:
            new_lines.append(f"{indent}{indent}{line.strip()}" if line.strip() else "")

        # Close the try with success recording
        new_lines.append(f"{indent}{indent}_memory.record_success(_key)")
        new_lines.append(f"{indent}    return result")
        new_lines.append(f"{indent}except Exception:")
        new_lines.append(f"{indent}    _memory.record_failure(_key)")
        new_lines.append(f"{indent}    raise")

        new_body = "\n".join(new_lines)
        patches.append(_make_patch(
            target.target_file,
            file_content,
            file_content.replace(old_body, new_body, 1),
            f"Add PatternFailureMemory recording to {fn_name}",
        ))

    return patches


@register_recipe(
    ModificationRecipe.ADD_CALIBRATION_HOOK,
    description="Add prediction accuracy tracking hook to a tool or strategy. "
    "Records predicted vs actual outcomes for future calibration.",
    config_schema={"hook_type": str},
)
def _apply_add_calibration_hook(target: ModificationTarget) -> list[dict[str, Any]]:
    """Add a calibration logging call at the end of the target function.

    Adds import and a structured logging call that records the function's
    inputs and outputs for future prediction accuracy analysis.
    """
    fn_name = target.target_function
    if not fn_name:
        raise ValueError("add_calibration_hook requires target_function")

    file_content = _read_file(target.target_file)
    patches: list[dict[str, Any]] = []

    # Add import
    import_line = "import json\n"
    if "import json" not in file_content and "from json" not in file_content:
        last_import_idx = -1
        lines = file_content.split("\n")
        for i, line in enumerate(lines):
            if line.startswith(("import ", "from ")):
                last_import_idx = i
        if last_import_idx >= 0:
            lines.insert(last_import_idx + 1, import_line.rstrip())
            new_content = "\n".join(lines)
            patches.append(_make_patch(
                target.target_file,
                file_content,
                new_content,
                f"Add json import for calibration hook in {target.target_file}",
            ))
            file_content = new_content

    # Add hook comment + log call before each return statement
    # Pattern: return <value>
    hook_text = (
        f"        logger.info(\"calibration_hook|{fn_name}|%s\", "
        f"json.dumps({{"
        f"\"function\": \"{fn_name}\", "
        f"\"status\": \"completed\""
        f"}}))\n"
    )

    new_content2 = re.sub(
        r"(?<!\w)(return\s+)",
        hook_text + r"\1",
        file_content,
    )

    if new_content2 != file_content:
        patches.append(_make_patch(
            target.target_file,
            file_content,
            new_content2,
            f"Add calibration logging hook to {fn_name}",
        ))

    return patches


@register_recipe(
    ModificationRecipe.PROMOTE_PROPERTY,
    description="Set a structural property to True in the registry. "
    "No source code change — only metadata update.",
    config_schema={"property_name": str},
)
def _apply_promote_property(target: ModificationTarget) -> list[dict[str, Any]]:
    """Property promotion requires no code patches — handled by caller.

    Returns empty list. The executor will call registry.set_property()
    separately.
    """
    return []


# ── Shared Helpers ────────────────────────────────────────────────────


def _read_file(file_path: str) -> str:
    """Read a file from the project root."""
    import os
    full_path = file_path if os.path.isabs(file_path) else os.path.join(os.getcwd(), file_path)
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


def _make_patch(
    file: str,
    old_content: str,
    new_content: str,
    description: str,
) -> dict[str, Any]:
    """Build a CodePatch-compatible dict."""
    return {
        "file": file,
        "old_content": old_content,
        "new_content": new_content,
        "patch_type": "modify",
        "description": description,
    }


def _wrap_last_return(
    target_file: str,
    function_name: str,
    wrapper: callable,
    anchor_text: str = "",
) -> list[dict[str, Any]]:
    """Generic helper — wraps the last return statement in a function.

    Finds the function by name, identifies the last `return <expr>`
    statement, and replaces it with a wrapper that captures the expression
    as `result = _original_impl(params)` and then applies the wrapper
    template.
    """
    file_content = _read_file(target_file)

    # Find the function body
    fn_pattern = re.compile(
        r"(def\s+" + re.escape(function_name) + r"\s*\([^)]*\)\s*:\s*\n)"
        r"((?:(?!^\s*def\s).*\n?)*)",
        re.MULTILINE,
    )
    fn_match = fn_pattern.search(file_content)
    if not fn_match:
        raise ValueError(
            f"Function '{function_name}' not found in {target_file}"
        )

    old_function = fn_match.group(0)
    body = fn_match.group(2)

    # Find the last return statement with a value
    return_pattern = re.compile(r"^(\s*)return\s+(.+)$", re.MULTILINE)
    return_matches = list(return_pattern.finditer(body))
    if not return_matches:
        raise ValueError(
            f"No return statement found in function '{function_name}'"
        )

    last_return = return_matches[-1]
    indent = last_return.group(1)
    return_expr = last_return.group(2).rstrip()
    params_placeholder = return_expr

    # Build replacement
    wrapper_code = wrapper(params=params_placeholder, name_repr=function_name)
    # Ensure proper indentation
    wrapper_lines = wrapper_code.split("\n")
    indented_wrapper = "\n".join(
        f"{indent}{line}" if line.strip() else ""
        for line in wrapper_lines
    )

    old_return_line = last_return.group(0)
    new_body = body.replace(old_return_line, indented_wrapper, 1)
    new_function = old_function.replace(body, new_body, 1)

    return [_make_patch(
        file=target_file,
        old_content=file_content,
        new_content=file_content.replace(old_function, new_function, 1),
        description=f"Add retry loop to {function_name}",
    )]
