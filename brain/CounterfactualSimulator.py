from __future__ import annotations

from typing import Any

from jarvis_os.runtime.exceptions import GovernanceViolation


class CounterfactualAnalyzer:
    """
    Computes bounded counterfactual alternatives from explicit assumptions.
    """

    def evaluate(self, assumptions: list[str], action: str) -> dict[str, Any]:
        if not action or not action.strip():
            raise GovernanceViolation("Counterfactual analysis requires a concrete action.")
        alternatives = [f"If '{assumption}' changes, revise action '{action}'." for assumption in assumptions[:5]]
        return {"action": action, "alternatives": alternatives, "count": len(alternatives)}


# Alias for brain.__init__ import
CounterfactualSimulator = CounterfactualAnalyzer
