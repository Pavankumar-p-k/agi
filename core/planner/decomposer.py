"""GoalDecomposer — turns a natural-language goal into a SubGoal tree.

Patterns handled:
  "build app with X, Y and Z"  -> one build leaf per feature (+ email if asked)
  "Research A, then build B"   -> research/build/... phase leaves
  "Build X. Component A. B."   -> sentence-list component leaves
"""
from __future__ import annotations

import re
from typing import Optional

# Words that terminate a feature list (the next clause is a new step).
_STOP_WORDS = {"email", "build", "then", "research", "test", "send", "deploy"}


def _find_features(goal: str) -> list[str]:
    """Extract 'with/including/featuring/for: X, Y and Z' feature lists."""
    text = goal or ""
    match = re.search(
        r"\b(?:with|including|featuring|for)\s*:?\s*(.+?)(?=$|\.|;|\bthen\b)",
        text, re.IGNORECASE,
    )
    if not match:
        return []
    raw = match.group(1)
    # Split on commas and 'and', then prune at stop-word boundaries.
    parts = re.split(r",|\band\b", raw, flags=re.IGNORECASE)
    features: list[str] = []
    for part in parts:
        part = part.strip().strip(".")
        words = part.split()
        pruned: list[str] = []
        for w in words:
            if w.lower().rstrip(".,!?:") in _STOP_WORDS:
                break
            pruned.append(w)
        name = " ".join(pruned).strip()
        if name:
            features.append(name)
    return features


def _normalize_feature_name(name: str) -> str:
    """'Admin Dashboard v2!' -> 'admin_dashboard_v2'."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", (name or "").strip()).lower()
    return cleaned.strip("_")


_SENTENCE_SPLIT = re.compile(r"(?<=[.!;])\s+")


class GoalDecomposer:
    """Decomposes goals into phase-ordered SubGoal trees."""

    def __init__(self, **kwargs):
        self._templates = {
            "research_build_email": ["research", "build", "email"],
            "android_app_build": ["research", "build", "test", "email"],
        }

    def decompose(self, goal: str) -> Optional["SubGoalTree"]:
        text = (goal or "").strip()
        if not text:
            return None

        root = _SubGoalNode(id="root", description=text, template_id=self._match_template(text))
        lower = text.lower()

        features = _find_features(text)
        steps = self._phase_steps(lower)

        # Feature-based build leaves
        for feature in features:
            norm = _normalize_feature_name(feature)
            root.children.append(_SubGoalNode(
                id=f"build_{norm}",
                description=f"Implement: {feature}",
                step_name="build",
                parameters={"feature": norm},
            ))
        # Sentence-list / "Requirements: X, Y, Z" component leaves
        req_match = re.search(r"requirements\s*:\s*(.+?)(?:\.|$)", lower)
        if req_match:
            req_items = [
                s.strip() for s in re.split(r",|\band\b", req_match.group(1))
                if s.strip()
            ]
            for i, comp in enumerate(req_items):
                root.children.append(_SubGoalNode(
                    id=f"build_req_{i}",
                    description=f"Implement: {comp}",
                    step_name="build",
                    parameters={"feature": _normalize_feature_name(comp)},
                ))
        elif not features and "." in text:
            components = [
                s.strip() for s in _SENTENCE_SPLIT.split(text)
                if s.strip() and len(s.strip()) > 3
            ]
            if len(components) >= 2:
                for i, comp in enumerate(components):
                    root.children.append(_SubGoalNode(
                        id=f"build_{i}",
                        description=f"Implement: {comp}",
                        step_name="build",
                        parameters={"feature": _normalize_feature_name(comp)},
                    ))

        # Phase steps not already covered by feature leaves
        covered_steps = {c.step_name for c in root.children}
        for step in steps:
            if step in covered_steps and step == "build":
                continue  # feature leaves already cover build
            root.children.append(_SubGoalNode(
                id=f"{step}_leaf", description=text, step_name=step,
            ))

        if not root.children:
            root.children.append(_SubGoalNode(id="build_leaf", description=text,
                                              step_name="build"))
        return SubGoalTree(root)

    def _match_template(self, text: str) -> str:
        lower = text.lower()
        if "email" in lower and "build" in lower:
            return "research_build_email"
        if "app" in lower or "android" in lower:
            return "android_app_build"
        return ""

    def _phase_steps(self, lower: str) -> list[str]:
        steps: list[str] = []
        if "research" in lower:
            steps.append("research")
        if "build" in lower or "app" in lower or "apk" in lower:
            steps.append("build")
        if "test" in lower:
            steps.append("test")
        if "email" in lower or "send" in lower:
            steps.append("email")
        return steps


class _SubGoalNode:
    """Internal mutable SubGoal node (avoids dataclass default sharing)."""

    def __init__(self, id: str, description: str, step_name: str = "",
                 template_id: str = "", parameters: Optional[dict] = None):
        self.id = id
        self.description = description
        self.step_name = step_name
        self.template_id = template_id
        self.parameters = parameters or {}
        self.children: list[_SubGoalNode] = []

    def flatten(self) -> list:
        if not self.children:
            from core.planner.models import SubGoal as _SG
            return [_SG(id=self.id, description=self.description,
                        step_name=self.step_name, template_id=self.template_id,
                        parameters=dict(self.parameters))]
        leaves: list = []
        for child in self.children:
            leaves.extend(child.flatten())
        return leaves


class SubGoalTree:
    """Wrapper exposing .flatten() and .root over the decomposition."""

    def __init__(self, root: _SubGoalNode):
        self.root = root

    def flatten(self) -> list:
        return self.root.flatten()
