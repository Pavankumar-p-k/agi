"""Semantic native-control actions built on the shared discovery service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import difflib

from core.desktop.discovery import DesktopDiscovery, ControlInfo


@dataclass(frozen=True)
class ControlMatch:
    control: ControlInfo
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "control": self.control.to_dict()}


class SemanticControlService:
    """Resolve controls conservatively, then delegate execution to an adapter."""

    def __init__(
        self,
        discovery: DesktopDiscovery,
        executor: Callable[[str, ControlInfo, str], dict[str, Any]] | None = None,
        min_score: float = 0.86,
    ):
        if not 0 < min_score <= 1:
            raise ValueError("min_score must be between 0 and 1")
        self.discovery = discovery
        self.executor = executor
        self.min_score = min_score

    def find(self, title: str, name: str, control_type: str | None = None) -> list[ControlMatch]:
        snapshot = self.discovery.discover_window(title)
        if snapshot is None:
            return []
        requested = name.strip().lower()
        matches = []
        for control in snapshot.controls:
            if control_type and control.control_type.lower() != control_type.lower():
                continue
            score = max(
                self._score(requested, control.name),
                self._score(requested, control.automation_id),
            )
            if score >= self.min_score:
                matches.append(ControlMatch(control, score))
        return sorted(matches, key=lambda item: item.score, reverse=True)

    def invoke(self, title: str, name: str, control_type: str | None = None) -> dict[str, Any]:
        matches = self.find(title, name, control_type)
        if len(matches) != 1:
            return {
                "success": False,
                "verified": False,
                "error": f"Expected exactly one semantic control, found {len(matches)}",
                "matches": [match.to_dict() for match in matches[:5]],
            }
        if self.executor is None:
            return {
                "success": False,
                "verified": False,
                "error": "No native control executor is configured",
                "control": matches[0].control.to_dict(),
            }
        result = self.executor(title, matches[0].control, "invoke")
        return {**result, "control": matches[0].control.to_dict()}

    @staticmethod
    def _score(requested: str, candidate: str) -> float:
        if not candidate:
            return 0.0
        value = candidate.strip().lower()
        if value == requested:
            return 1.0
        return difflib.SequenceMatcher(None, requested, value).ratio()
