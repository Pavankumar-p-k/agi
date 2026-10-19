"""Policy gate: allow / ask / deny — decided outside the model.

Invariant 2 of the plan: policy lives outside the model; the reasoner cannot
edit these rules. The default rule file ships inside the package (read-only to
the agent); an operator can point MJ_POLICY at a reviewed replacement file.
Rules are evaluated in order; the first match wins; no match -> default_action.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from importlib import resources
from typing import Any

from .store import Store, canonical_json
from . import audit

ALLOW = "allow"
ASK = "ask"
DENY = "deny"

RISK_CLASSES = ("R0", "R1", "R2", "R3", "R4")
TRUST_LEVELS = ("local-terminal", "chat-connector", "external")

# Risk classes that always require an approval prompt even when a rule says allow,
# per plan section 7 step 6 (R3/R4 always ask unless a standing rule exists).
ALWAYS_ASK_CLASSES = {"R3", "R4"}


class PolicyError(ValueError):
    """Raised when the policy file is malformed."""


@dataclass(frozen=True)
class Rule:
    risk_class: str
    trust_types: list[str]  # list of trust levels, or ["any"]
    action: str
    comment: str = ""


@dataclass(frozen=True)
class Decision:
    action: str  # allow | ask | deny
    rule: Rule | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "rule": None if self.rule is None else {
                "risk_class": self.rule.risk_class,
                "trust_types": self.rule.trust_types,
                "action": self.rule.action,
            },
        }


DEFAULT_POLICY = "policy.json"


def _load_rules_from_dict(data: dict[str, Any], origin: str) -> list[Rule]:
    if not isinstance(data, dict):
        raise PolicyError(f"{origin}: top-level policy must be an object")
    rules_raw = data.get("rules", [])
    if not isinstance(rules_raw, list):
        raise PolicyError(f"{origin}: 'rules' must be a list")
    rules: list[Rule] = []
    for i, raw in enumerate(rules_raw):
        if not isinstance(raw, dict) or "risk_class" not in raw or "action" not in raw:
            raise PolicyError(f"{origin}: rule #{i} missing risk_class/action")
        if raw["risk_class"] not in RISK_CLASSES:
            raise PolicyError(f"{origin}: rule #{i} bad risk_class {raw['risk_class']!r}")
        if raw["action"] not in (ALLOW, ASK, DENY):
            raise PolicyError(f"{origin}: rule #{i} bad action {raw['action']!r}")
        trusts = raw.get("trust_types", ["any"])
        if not isinstance(trusts, list) or not all(isinstance(t, str) for t in trusts):
            raise PolicyError(f"{origin}: rule #{i} trust_types must be a list of strings")
        rules.append(
            Rule(
                risk_class=raw["risk_class"],
                trust_types=trusts,
                action=raw["action"],
                comment=str(raw.get("comment", "")),
            )
        )
    return rules


def load_rules() -> tuple[list[Rule], str]:
    """Load rules from MJ_POLICY if set, else the packaged default."""
    env = os.environ.get("MJ_POLICY")
    if env:
        with open(env, encoding="utf-8") as fh:
            return _load_rules_from_dict(json.load(fh), env)
    text = resources.files("mj.policies").joinpath(DEFAULT_POLICY).read_text(encoding="utf-8")
    return _load_rules_from_dict(json.loads(text), f"package:{DEFAULT_POLICY}")


class PolicyGate:
    def __init__(self, rules: list[Rule], default_action: str = DENY) -> None:
        self.rules = rules
        self.default_action = default_action

    @classmethod
    def load(cls) -> "PolicyGate":
        rules = load_rules()
        return cls(rules)

    def decide(
        self,
        store: Store,
        actor: str,
        risk_class: str,
        trust_level: str,
    ) -> Decision:
        if risk_class not in RISK_CLASSES:
            raise PolicyError(f"unknown risk class {risk_class!r}")
        if trust_level not in TRUST_LEVELS:
            raise PolicyError(f"unknown trust level {trust_level!r}")
        picked: Decision | None = None
        for rule in self.rules:
            if rule.risk_class != risk_class:
                continue
            if "any" not in rule.trust_types and trust_level not in rule.trust_types:
                continue
            picked = Decision(
                action=rule.action,
                rule=rule,
                reason=f"matched rule {rule.risk_class} for trust {trust_level}: {rule.comment}".strip(),
            )
            break
        if picked is None:
            picked = Decision(
                action=self.default_action,
                rule=None,
                reason=f"no rule matched risk {risk_class} at trust {trust_level}; default {self.default_action}",
            )
        # Plan invariant: R3/R4 never run silently. Escalate an allow to ask.
        if picked.action == ALLOW and risk_class in ALWAYS_ASK_CLASSES:
            picked = Decision(
                action=ASK,
                rule=picked.rule,
                reason=f"{risk_class} always asks regardless of matched rule",
            )
        audit.append(store, actor or "policy", "policy.decision", {
            "risk_class": risk_class,
            "trust_level": trust_level,
            "decision": picked.action,
            "reason": picked.reason,
        })
        return picked


def default_policy() -> PolicyGate:
    return PolicyGate.load()
