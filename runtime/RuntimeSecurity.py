from __future__ import annotations

from typing import Any, Dict

SENSITIVE_PROMPT_PATTERNS: dict[str, tuple[str, ...]] = {
    "privacy_critical": ("private", "sensitive", "confidential", "secret"),
    "financial_critical": ("financial", "bank account", "credit card", "routing number", "account number", "ssn", "social security", "tax", "loan", "investment", "payroll"),
    "medical_critical": ("medical", "health record", "diagnosis", "treatment", "prescription", "patient", "lab result", "mental health", "therapy", "clinic"),
    "legal_critical": ("legal", "lawyer", "attorney", "lawsuit", "contract", "nda", "compliance", "court", "settlement"),
    "identity_critical": ("password", "pin", "otp", "passport", "id number", "credentials", "social security", "ssn"),
}

OFFLINE_FIRST_LABELS = {"privacy_critical", "financial_critical", "medical_critical", "legal_critical", "identity_critical"}


def classify_prompt_sensitivity(prompt: str) -> dict[str, Any]:
    normalized = (prompt or "").lower()
    profile: dict[str, Any] = {
        "privacy_sensitive": False,
        "cost_sensitive": bool("cheap" in normalized or "budget" in normalized),
        "task_type": "chat",
        "privacy_class": "public",
        "offline_first": False,
    }

    for label, keywords in SENSITIVE_PROMPT_PATTERNS.items():
        if any(keyword in normalized for keyword in keywords):
            profile["privacy_sensitive"] = True
            profile["task_type"] = label
            profile["privacy_class"] = label
            profile["offline_first"] = True
            profile["cost_sensitive"] = True
            break

    if not profile["privacy_sensitive"] and any(token in normalized for token in ("private", "sensitive", "confidential", "secret")):
        profile.update({
            "privacy_sensitive": True,
            "task_type": "privacy_critical",
            "privacy_class": "privacy_critical",
            "offline_first": True,
            "cost_sensitive": True,
        })

    if any(token in normalized for token in ("quick", "fast", "cheap", "low cost")):
        profile["cost_sensitive"] = True
    if any(token in normalized for token in ("reason", "analysis", "strategy", "deep")):
        profile["task_type"] = profile["task_type"] if profile["privacy_sensitive"] else "deep_reasoning"
    if any(token in normalized for token in ("code", "program", "script", "developer", "execute")):
        if not profile["privacy_sensitive"]:
            profile["task_type"] = "coding"
        profile["coding_strength"] = 0.95
        profile["reasoning_depth"] = max(profile.get("reasoning_depth", 0.4), 0.7)
    return profile


def is_network_sensitive(prompt: str) -> bool:
    return classify_prompt_sensitivity(prompt).get("offline_first", False)


def serialize_policy_profile(prompt: str) -> dict[str, Any]:
    profile = classify_prompt_sensitivity(prompt)
    return {
        "privacy_sensitive": profile["privacy_sensitive"],
        "privacy_class": profile["privacy_class"],
        "offline_first": profile["offline_first"],
        "task_type": profile["task_type"],
    }
