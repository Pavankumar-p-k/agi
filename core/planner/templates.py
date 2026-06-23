"""Deterministic workflow templates for the Planner layer."""

from core.planner.models import PlannerTemplate

TEMPLATES: dict[str, PlannerTemplate] = {}


def _register(t: PlannerTemplate) -> PlannerTemplate:
    TEMPLATES[t.template_id] = t
    return t


_research_build_validate_email = _register(PlannerTemplate(
    template_id="research_build_validate_email",
    name="Research -> Build -> Validate -> Email",
    description="Research a topic, build a project, run tests, validate runtime, and email the results.",
    required_steps=["research", "build", "test", "validate", "email"],
    success_conditions=[{"key": "email_sent", "value": True}],
))

_android_app_build = _register(PlannerTemplate(
    template_id="android_app_build",
    name="Android App Build -> APK Delivery",
    description="Research app UI trends, build an Android project, test, package APK, and email the artifact.",
    required_steps=["research", "build", "test", "apk", "email"],
    success_conditions=[{"key": "apk_produced", "value": True}, {"key": "email_sent", "value": True}],
))

_research_build_email = _register(PlannerTemplate(
    template_id="research_build_email",
    name="Research -> Build -> Email",
    description="Research, build a project, and email the output without full validation suite.",
    required_steps=["research", "build", "email"],
    success_conditions=[{"key": "email_sent", "value": True}],
))

_build_validate_notify = _register(PlannerTemplate(
    template_id="build_validate_notify",
    name="Build -> Validate -> Notify",
    description="Build a project, run validation, and notify the user of the outcome.",
    required_steps=["build", "test", "validate", "notify"],
    success_conditions=[{"key": "build_passed", "value": True}],
))


def get_template(template_id: str) -> PlannerTemplate | None:
    return TEMPLATES.get(template_id)


def list_templates() -> list[PlannerTemplate]:
    return list(TEMPLATES.values())


# Mapping from concrete tool names to abstract step names.
# Used by match_required_tools and record_step to normalize.
TOOL_TO_STEP: dict[str, str] = {
    "browser_navigate": "research",
    "browser_snapshot": "research",
    "browser_search": "research",
    "web_fetch": "research",
    "build_project": "build",
    "repair_project": "build",
    "run_tests": "test",
    "runtime_validate": "validate",
    "send_email": "email",
}


# Reverse mapping: abstract step name → primary concrete tool name.
# The planner uses this to decide WHICH tool to execute for a required step.
STEP_TO_PRIMARY_TOOL: dict[str, str] = {
    "research": "browser_navigate",
    "build":    "build_project",
    "test":     "run_tests",
    "validate": "runtime_validate",
    "email":    "send_email",
    "apk":      "build_project",
    "notify":   "send_email",
}


# Some tools satisfy multiple abstract step types.
# e.g. build_project satisfies both "build" and "apk".
TOOL_STEP_ALIASES: dict[str, set[str]] = {
    "build_project": {"apk"},
}


def normalize_tool_names(tool_names: list[str]) -> set[str]:
    """Convert concrete tool names to abstract step names.

    Expands tool aliases so a single tool can satisfy multiple step types.
    """
    result: set[str] = set()
    for t in tool_names:
        step = TOOL_TO_STEP.get(t, t)
        result.add(step)
        if t in TOOL_STEP_ALIASES:
            result.update(TOOL_STEP_ALIASES[t])
    return result


def match_required_tools(template_id: str, completed_tool_names: list[str]) -> list[str]:
    """Return required step names not yet completed.

    Converts concrete tool names (e.g. browser_navigate) to abstract step
    names (e.g. research) before comparing against required steps.
    """
    t = get_template(template_id)
    if not t:
        return []
    completed_set = normalize_tool_names(completed_tool_names)
    return [s for s in t.required_steps if s not in completed_set]
