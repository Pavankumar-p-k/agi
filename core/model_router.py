# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""core/model_router.py — BACKWARD-COMPAT SHIM

All data and low-level helpers have moved to core/llm_router.py.
This file re-exports them and keeps the higher-level routing orchestration.
New code should import from core.llm_router directly.
"""

from core.llm_router import (  # noqa: F401
    _ollama_url,
    resolve_model,
    _parse_model_endpoints,
    _load_endpoints,
    model_endpoints,
    is_multi_instance,
    get_ollama_url,
    group_for_role,
    model_for_role,
    get_fallbacks,
    get_router_model,
    DEFAULT_MODEL_ENDPOINTS,
    MODEL_ALIASES,
    ROLE_TO_GROUP,
    ROLE_TO_ROUTER_GROUP,
    ROLE_MODELS,
    MODEL_FALLBACKS,
)

from core.config_registry import config as _jarvis_config
from core.privacy_classifier import PrivacyTier, privacy_classifier

import os


def route_role_for_text(text: str) -> str:
    """Lightweight heuristic router for text-only tasks."""
    t = (text or "").lower()
    if any(k in t for k in ("deep research", "thorough analysis", "comprehensive", "deep dive", "expert analysis", "in-depth")):
        return "deep"
    if any(k in t for k in ("code", "bug", "stack trace", "exception", "compile", "syntax")):
        return "code"
    if any(k in t for k in ("analyze", "analysis", "compare", "pros and cons", "decision")):
        return "analysis"
    if any(k in t for k in ("write", "rewrite", "story", "poem", "script", "lyrics", "email")):
        return "creative"
    if any(k in t for k in ("plan", "steps", "schedule", "roadmap", "automate", "workflow")):
        return "reasoning"
    return "chat"


_health_checker: callable = lambda: True


def set_health_checker(fn: callable):
    """Inject health-monitor callback (set during server startup)."""
    global _health_checker
    _health_checker = fn


def route_request(query: str, context: dict = None, force_tier: str = None):
    """
    Route request based on privacy classifier.
    Auto-fails over to cloud if Ollama is down and cloud keys are available.
    
    Returns (router_group, privacy_tier, processed_query).
    """
    if force_tier == "cloud":
        return "cloud", PrivacyTier.CLOUD, query
    if force_tier == "local":
        tier = privacy_classifier.classify(query, context)
        processed_query = query
        if tier == PrivacyTier.HYBRID:
            processed_query = privacy_classifier.sanitize(query, tier=PrivacyTier.HYBRID)
        role = route_role_for_text(processed_query)
        return group_for_role(role), PrivacyTier.LOCAL, processed_query

    if os.getenv("FORCE_CLOUD", "").lower() in ("1", "true", "yes"):
        return "cloud", PrivacyTier.CLOUD, query

    if not _health_checker():
        if os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY"):
            return "cloud", PrivacyTier.CLOUD, query

    tier = privacy_classifier.classify(query, context)
    processed_query = query

    if tier == PrivacyTier.HYBRID:
        processed_query = privacy_classifier.sanitize(query, tier=PrivacyTier.HYBRID)

    role = route_role_for_text(processed_query)
    return group_for_role(role), tier, processed_query
