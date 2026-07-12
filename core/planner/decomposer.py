"""GoalDecomposer — breaks complex user goals into a tree of sub-goals.

Each leaf sub-goal maps to either a workflow template or a direct tool step.
The planner owns the decomposition; the model never touches structure.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from core.planner.classifier import classify, extract_parameters
from core.planner.templates import STEP_TO_PRIMARY_TOOL
from core.planner.models import SubGoal

logger = logging.getLogger(__name__)

# ── Sub-goal detection rules ────────────────────────────────────────────────
# Each rule is (label, keywords, template_id, step_name)
# template_id takes priority over step_name if both are set.

_SUBGOAL_RULES: list[tuple[str, list[str], str | None, str | None]] = [
    # Research / browse
    ("research competitors", ["research", "competitor", "market"], None, "research"),
    ("research ui trends",    ["ui trend", "design trend", "ux"], None, "research"),
    ("research features",    ["feature research", "what features"], None, "research"),

    # Build
    ("build project",        ["build", "create", "develop", "make"], None, "build"),

    # Test
    ("run tests",            ["test", "testing", "qa"], None, "test"),

    # Validate
    ("validate build",       ["validate", "verify", "check"], None, "validate"),

    # Email / notify
    ("email results",        ["email", "mail", "send"], None, "email"),
    ("notify user",          ["notify", "report"], None, "notify"),

    # Code generation (→ ForgeAdapter)
    ("codegen",              ["implement", "codegen", "generate code", "refactor"], None, "codegen"),
    ("security audit",       ["security", "audit", "vulnerability", "threat"], None, "security"),
    ("documentation",        ["documentation", "readme", "changelog", "docs"], None, "docs"),
    ("data analysis",        ["data analysis", "visualization"], None, "analytics"),
    ("insight synthesis",    ["synthesize", "intelligence brief", "intelligence"], None, "synthesize"),
    ("system monitoring",    ["monitor metrics", "diagnose", "system health"], None, "monitor"),
    ("planning",             ["plan", "estimate", "decompose", "prioritize"], None, "planning"),
    ("web extraction",       ["extract page", "scrape url", "monitor page"], None, "extraction"),
]


def _normalize_feature_name(name: str) -> str:
    """Normalize a feature name for use as an agent parameter.
    "admin dashboard" -> "admin_dashboard"
    "ui" -> "ui"
    """
    name = name.strip().lower()
    name = re.sub(r'\s+', '_', name)
    name = re.sub(r'[^a-z0-9_]', '', name)
    return name


def _find_features(goal_lower: str) -> list[str]:
    """Extract feature/specification items from a goal.

    Handles patterns like:
      "with animations, payments, and loyalty rewards"
      "with animations and payments"
      "with animations, payments, loyalty rewards, admin dashboard"
      "including payments, loyalty, analytics"
      "featuring dark mode, push notifications"
      "with: payments, loyalty"
      "for: payments, loyalty"
    """
    first_sentence = goal_lower.split('.')[0]
    # Multiple trigger patterns tried in order
    trigger_patterns = [
        # 1. "with X, Y, Z"  (most common)
        r'\bwith\s+(.+?)(?:\s+(?:and\s+)?email|\s+and\s+(?:build|create|make)|\s*$)',
        # 2. "including X, Y, Z"
        r'\bincluding\s+(.+?)(?:\s+(?:and\s+)?email|\s+and\s+(?:build|create|make)|\s*$)',
        # 3. "featuring X, Y, Z"
        r'\bfeaturing\s+(.+?)(?:\s+(?:and\s+)?email|\s+and\s+(?:build|create|make)|\s*$)',
        # 4. "with: X, Y, Z"
        r'\bwith\s*:\s*(.+?)(?:\s+(?:and\s+)?email|\s+and\s+(?:build|create|make)|\s*$)',
        # 5. "for: X, Y, Z"
        r'\bfor\s*:\s*(.+?)(?:\s+(?:and\s+)?email|\s+and\s+(?:build|create|make)|\s*$)',
    ]

    raw = None
    for pat in trigger_patterns:
        m = re.search(pat, first_sentence)
        if m:
            raw = m.group(1)
            break

    if not raw:
        return []

    parts_by_comma = re.split(r'\s*,\s*', raw)
    result = []
    for part in parts_by_comma:
        part = part.strip()
        if not part:
            continue
        if part.lower().startswith('and '):
            part = part[4:].strip()
            if not part:
                continue
        for sp in re.split(r'\s+and\s+', part):
            sp = sp.strip().rstrip('.')
            if sp:
                result.append(sp)
    return result


def _find_phases(goal_lower: str) -> list[dict[str, Any]]:
    """Detect explicit multi-phase structure in the goal.

    Returns list of phase dicts with 'label' and 'text' keys.
    Example: "Research X, then build Y, then email Z"
    """
    phases = []
    # Split on phase markers
    parts = re.split(
        r'\s*[,;]\s*(?:then|next|after\s+that|finally)\s+',
        goal_lower,
    )
    if len(parts) > 1:
        for i, p in enumerate(parts):
            phases.append({"label": f"phase_{i}", "text": p.strip()})
    return phases


def _split_top_level_commas(text: str) -> list[str]:
    """Split on commas but NOT inside parentheses."""
    parts = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current).strip())
    return [p for p in parts if p]


def _parse_parenthetical(name: str) -> tuple[str, list[str]]:
    """Extract 'Name (child1, child2)' → ('Name', ['child1', 'child2'])."""
    m = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', name.strip())
    if m:
        parent = m.group(1).strip()
        children = [c.strip().rstrip('.') for c in m.group(2).split(',') if c.strip()]
        return parent, children
    return name.strip(), []


def _find_project_components(goal_lower: str) -> list[dict] | None:
    """Extract hierarchical project components from a structured goal.

    Detects:
      1. 'Requirements:' / 'Components:' / 'Modules:' sections with parenthetical groups
      2. Sentence-list: each sentence describes a component ('Android app with X. Analytics.')
      3. 'consisting of' / 'comprising' formal patterns

    Returns list of dicts with keys: name, children (list[str]), or None if no structure found.
    """
    components: list[dict] = []
    goal_clean = goal_lower.strip().rstrip('.')

    # ── Pattern 1: "Requirements:" / "Components:" / "Modules:" / "Features:" ──
    m = re.search(
        r'\b(?:requirements|components|modules|features|comprising|consisting\s+of)\s*[:;]\s*(.+?)$',
        goal_clean,
        re.DOTALL,
    )
    if m:
        section_text = m.group(1).strip()
        items = _split_top_level_commas(section_text)
        for item in items:
            parent, children = _parse_parenthetical(item)
            if parent:
                components.append({"name": parent, "children": children})
        if components:
            return components

    # ── Pattern 2: "X with Y" patterns (group features under a lead noun) ──
    # e.g. "Android app with UI, payments, and loyalty"
    # Captures everything up to a period or end of string (NOT using "and"
    # as a terminator — that breaks the capture of "and" as content).
    pat2 = re.compile(
        r'\b((?:\w+\s+)?(?:app|dashboard|module|system|platform|service|solution))\s+with\s+(.+?)(?:\.\s*|$)',
        re.IGNORECASE,
    )
    for m in pat2.finditer(goal_clean):
        category = m.group(1).strip()
        raw_children = m.group(2).strip()
        children = []
        for pc in re.split(r'\s*,\s*', raw_children):
            pc = pc.strip()
            if pc.lower().startswith('and '):
                pc = pc[4:].strip()
            if not pc:
                continue
            for sp in re.split(r'\s+and\s+', pc):
                sp = sp.strip().rstrip('.')
                if sp:
                    children.append(sp)
        components.append({"name": category.title(), "children": children})

    # ── Pattern 3: Sentence-list — each sentence after the first is a component ──
    seen_names = {c["name"].lower() for c in components}
    sentences = [s.strip().rstrip('.') for s in goal_clean.split('.') if s.strip()]
    if len(sentences) >= 3:
        # First sentence is the action statement; subsequent sentences are components
        is_component = False
        for s in sentences[1:]:
            # Skip if it's a phase marker or sub-goal keyword
            if any(kw in s for kw in ["then ", "next ", "finally ", "after that"]):
                continue
            # Check if it looks like a component
            parent, raw_children = _parse_parenthetical(s)
            # Check for "X with Y" inline pattern
            with_m = re.match(r'(.+?)\s+with\s+(.+?)$', parent)
            if with_m:
                parent = with_m.group(1).strip()
                raw_ch = with_m.group(2)
                children = []
                for pc in re.split(r'\s*,\s*', raw_ch):
                    pc = pc.strip()
                    if pc.lower().startswith('and '):
                        pc = pc[4:].strip()
                    if not pc:
                        continue
                    for sc in re.split(r'\s+and\s+', pc):
                        sc = sc.strip().rstrip('.')
                        if sc:
                            children.append(sc)
            else:
                children = list(raw_children)
            if parent and parent.lower() not in seen_names:
                components.append({"name": parent, "children": children})
                seen_names.add(parent.lower())
            is_component = True
        if is_component:
            return components

    return components if components else None


class GoalDecomposer:
    """Deterministic goal decomposer with optional LLM fallback.

    Breaks a natural-language goal into a tree of SubGoals using keyword
    patterns and grammar heuristics. If heuristic decomposition produces
    fewer than 2 sub-goals, attempts LLM-based decomposition for novel tasks.
    Each leaf sub-goal maps to either a workflow template (via classify)
    or a direct tool step.
    """

    def __init__(self):
        self._subgoal_counter = 0

    async def _llm_decompose(self, goal: str) -> SubGoal | None:
        """LLM-based decomposition fallback for novel/unrecognized goals."""
        try:
            from core.llm_router import complete

            prompt = (
                "You are a goal decomposition assistant. Decompose the following user goal "
                "into a JSON array of sub-tasks. Each sub-task must have a 'description' (short phrase), "
                "a 'step_name' (one of: research, build, test, validate, email, notify, codegen, "
                "security, docs, analytics, synthesize, monitor, planning, extraction), "
                "and an optional 'parameters' dict.\n\n"
                f"Goal: {goal}\n\n"
                "Return ONLY a valid JSON array — no markdown, no explanation:\n"
                '[{"description": "...", "step_name": "...", "parameters": {}}]'
            )
            result = await complete("smart", [{"role": "user", "content": prompt}], timeout=30)
            if not result or result.is_err():
                logger.debug("LLM decompose: no result for %r", goal[:60])
                return None
            text = result.unwrap().strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            tasks = json.loads(text)
            if not isinstance(tasks, list) or len(tasks) < 2:
                return None
            children = []
            for t in tasks:
                desc = t.get("description", "")
                step = t.get("step_name", "build")
                params = t.get("parameters", {})
                children.append(SubGoal(
                    id=self._next_id(),
                    description=desc[:120],
                    step_name=step,
                    parameters=params,
                ))
            if not children:
                return None
            logger.info("Decomposer: LLM fallback produced %d sub-goals for %r",
                        len(children), goal[:60])
            return SubGoal(id=self._next_id(), description=goal[:120], children=children)
        except Exception as e:
            logger.debug("LLM decompose failed for %r: %s", goal[:60], e)
            return None

    async def async_decompose(self, goal: str) -> SubGoal:
        """Async decomposition with LLM fallback for novel tasks.

        Uses keyword heuristics first; if fewer than 2 sub-goals are found,
        falls back to LLM-based decomposition.
        """
        root = self.decompose(goal)
        if len(root.children) >= 2:
            return root
        llm_root = await self._llm_decompose(goal)
        if llm_root and llm_root.children:
            return llm_root
        return root

    def _next_id(self) -> str:
        self._subgoal_counter += 1
        return f"sg_{self._subgoal_counter}"

    def decompose(self, goal: str) -> SubGoal:
        """Decompose a user goal into a tree of sub-goals.

        Returns a root SubGoal whose children represent the decomposition.
        If decomposition yields no children, returns a single leaf mapped
        to the template (if classified) or a generic step.
        """
        goal_lower = goal.lower().strip()
        children: list[SubGoal] = []

        # 1. Extract features from the full goal FIRST (before phases).
        features = _find_features(goal_lower)
        template_id = classify(goal)

        # 2. Try hierarchical project decomposition first
        #    (captures "Requirements:" sections, "X with Y" patterns, sentence-list goals)
        project_comps = _find_project_components(goal_lower)
        if project_comps and len(project_comps) >= 2:
            for comp in project_comps:
                children.append(self._component_text_to_subgoal(comp["name"], comp.get("children")))
            # Also check for standalone sub-goals (research, email, etc.)
            extra = self._extract_standalone_subgoals(goal_lower, children)
            for sg in extra:
                if sg.description not in {c.description for c in children}:
                    children.append(sg)
            root = SubGoal(id=self._next_id(), description=goal[:120], children=children)
            logger.info("Decomposer: goal=%r -> %d project components",
                         goal[:60], len(project_comps))
            return root

        # 3. Detect multi-phase structure
        phases = _find_phases(goal_lower)
        if phases:
            for ph in phases:
                child = self._decompose_single(ph["text"], ph["label"])
                if child:
                    children.append(child)
            # If features found, replace any generic build sub-goal with
            # per-feature build leaves for parallel execution.
            if features:
                has_build = any(c.step_name == "build" for c in children)
                if has_build:
                    # Remove the generic build sub-goal
                    children = [c for c in children if c.step_name != "build"]
                for feat in features:
                    normalized = _normalize_feature_name(feat)
                    children.append(SubGoal(
                        id=self._next_id(),
                        description=f"Implement: {feat}",
                        step_name="build",
                        parameters={"feature": normalized},
                    ))
            # Standalone sub-goals not yet captured (email, notify, etc.)
            extra = self._extract_standalone_subgoals(goal_lower, children)
            for sg in extra:
                if sg.description not in {c.description for c in children}:
                    children.append(sg)
        else:
            # 2. Single-phase: decompose features under primary intent
            template_id = classify(goal)
            features = _find_features(goal_lower)

            # Build per-feature sub-goals when features exist
            if features:
                for feat in features:
                    normalized = _normalize_feature_name(feat)
                    children.append(SubGoal(
                        id=self._next_id(),
                        description=f"Implement: {feat}",
                        step_name="build",
                        parameters={"feature": normalized},
                    ))
            else:
                # Single primary sub-goal (no features to parallelize)
                primary = self._decompose_single(goal_lower, "primary")
                if primary:
                    children.append(primary)

            # 3. Check for additional standalone sub-goals (research + email, etc.)
            extra = self._extract_standalone_subgoals(goal_lower, children)
            for sg in extra:
                if sg.description not in {c.description for c in children}:
                    children.append(sg)

        # If no decomposition found, create a single leaf from classification
        if not children:
            template_id = classify(goal)
            params = extract_parameters(goal, template_id) if template_id else {}
            children.append(SubGoal(
                id=self._next_id(),
                description=goal[:80],
                template_id=template_id,
                step_name=STEP_TO_PRIMARY_TOOL.get(sorted(STEP_TO_PRIMARY_TOOL.keys())[0]),
                parameters=params,
            ))

        root = SubGoal(
            id=self._next_id(),
            description=goal[:120],
            children=children,
        )
        logger.info("Decomposer: goal=%r -> %d sub-goals, flat=%d",
                     goal[:60], len(children), len(root.flatten()))
        return root

    def _decompose_single(self, text: str, label: str) -> SubGoal | None:
        """Build a single SubGoal from a text fragment using keyword rules."""
        text_lower = text.strip().lower()
        if not text_lower:
            return None

        # Try keyword rules first
        for rule_label, keywords, template_id, step_name in _SUBGOAL_RULES:
            if any(kw in text_lower for kw in keywords):
                params = extract_parameters(text, template_id) if template_id else {}
                return SubGoal(
                    id=self._next_id(),
                    description=f"{label}: {rule_label}",
                    template_id=template_id,
                    step_name=step_name,
                    parameters=params,
                )

        # Fall back to classifier
        template_id = classify(text)
        if template_id:
            params = extract_parameters(text, template_id)
            return SubGoal(
                id=self._next_id(),
                description=f"{label}: template={template_id}",
                template_id=template_id,
                parameters=params,
            )

        # Last resort: generic step
        return SubGoal(
            id=self._next_id(),
            description=f"{label}: {text[:60]}",
            step_name="build",
            parameters={"topic": text[:60]},
        )

    def _component_text_to_subgoal(self, name: str, children_text: list[str] | None = None) -> SubGoal:
        """Convert a parsed component name + optional children into a SubGoal tree."""
        name_lower = name.lower().strip()
        # Detect delivery/email component
        if any(kw in name_lower for kw in ["email", "mail", "deliver", "deploy"]):
            return SubGoal(id=self._next_id(), description=f"Delivery: {name}",
                           step_name="email", parameters={})
        # Detect tool by keyword
        for rule_label, keywords, template_id, step_name in _SUBGOAL_RULES:
            if any(kw in name_lower for kw in keywords):
                sg = SubGoal(id=self._next_id(), description=f"{step_name}: {name}",
                             step_name=step_name, template_id=template_id)
                if children_text:
                    sg.children = [SubGoal(id=self._next_id(), description=f"  - {c.strip()}",
                                           step_name=step_name) for c in children_text]
                return sg
        # Default: build step
        cleaned = name.replace("_", " ").strip().title()
        sg = SubGoal(id=self._next_id(), description=cleaned,
                     step_name="build", parameters={"component": name.strip()})
        if children_text:
            sg.children = [SubGoal(id=self._next_id(), description=f"  - {c.strip()}",
                                   step_name="build") for c in children_text]
        return sg

    def _extract_standalone_subgoals(
        self, goal_lower: str, existing: list[SubGoal],
    ) -> list[SubGoal]:
        """Find sub-goals not yet captured by the primary decomposition."""
        extras: list[SubGoal] = []
        seen_labels = {c.description.split(":")[0].strip() for c in existing}
        seen_step_names = {c.step_name for c in existing if c.step_name}

        # Research sub-goal present?
        has_research = any("research" in v for v in seen_labels) or "research" in seen_step_names
        if not has_research and any(kw in goal_lower for kw in ["research", "trend", "competitor"]):
            extras.append(SubGoal(
                id=self._next_id(),
                description="research: web research",
                step_name="research",
                parameters={},
            ))

        # Email sub-goal present?
        has_email = any("email" in v for v in seen_labels) or "email" in seen_step_names
        if not has_email and any(kw in goal_lower for kw in ["email", "mail", "send", "deliver"]):
            recipient = ""
            m = re.search(r'to\s+([\w.@+-]+)', goal_lower)
            if m:
                recipient = m.group(1)
            extras.append(SubGoal(
                id=self._next_id(),
                description="email: send results",
                step_name="email",
                parameters={"recipient": recipient} if recipient else {},
            ))

        return extras