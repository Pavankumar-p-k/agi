"""core/feature_registry.py
Runtime feature registry for JARVIS.
Every feature declares status: stable, beta, experimental, broken, planned.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class FeatureStatus(Enum):
    STABLE = "stable"
    BETA = "beta"
    EXPERIMENTAL = "experimental"
    BROKEN = "broken"
    PLANNED = "planned"


@dataclass
class Feature:
    name: str
    status: FeatureStatus
    description: str = ""
    category: str = ""
    health_check_fn: str = ""
    config_key: str = ""
    enabled_by_default: bool = True
    dependencies: list[str] = field(default_factory=list)
    docs_path: str = ""
    tests_path: str = ""


FEATURES: dict[str, Feature] = {
    "model_providers": Feature(
        name="Model Providers (Ollama, OpenAI, Anthropic, Gemini, Groq, OpenRouter)",
        status=FeatureStatus.STABLE,
        description="Unified ModelProvider architecture with task-based routing",
        category="models",
        health_check_fn="core.model_providers.base:health_check_all",
        config_key="llm.chat_model",
        docs_path="MODEL_GUIDE.md",
        tests_path="tests/unit/",
    ),
    "model_router": Feature(
        name="Model Router (task-based routing)",
        status=FeatureStatus.STABLE,
        description="Routes requests to optimal model based on task type, latency, cost, availability",
        category="models",
        config_key="role_models.default",
    ),
    "integration_manager": Feature(
        name="Integration Manager (Gmail, Telegram, WhatsApp, Discord, Slack, GitHub, Drive)",
        status=FeatureStatus.BETA,
        description="Unified account connection system with OAuth and encrypted credential storage",
        category="integrations",
        health_check_fn="core.integration_manager:health_check_all",
        config_key="integrations",
    ),
    "channels": Feature(
        name="Messaging Channels (Discord, Slack, Telegram, Matrix, IRC, Email)",
        status=FeatureStatus.STABLE,
        description="Plugin-based messaging channel system with ACL and pairing",
        category="integrations",
        enabled_by_default=True,
    ),
    "whatsapp": Feature(
        name="WhatsApp (Meta Cloud API)",
        status=FeatureStatus.BETA,
        description="WhatsApp messaging via Meta Cloud API webhook",
        category="integrations",
        config_key="whatsapp",
    ),
    "gmail_monitor": Feature(
        name="Gmail Monitor",
        status=FeatureStatus.BETA,
        description="Gmail API poller with urgency detection",
        category="integrations",
        config_key="gmail",
    ),
    "github": Feature(
        name="GitHub Integration",
        status=FeatureStatus.BETA,
        description="GitHub API client for issues, PRs, repos, with OAuth",
        category="integrations",
        config_key="github",
        enabled_by_default=True,
    ),
    "google_drive": Feature(
        name="Google Drive Integration",
        status=FeatureStatus.PLANNED,
        description="Google Drive read/write/list",
        category="integrations",
        config_key="google_drive",
        enabled_by_default=False,
    ),
    "voice_assistant": Feature(
        name="Voice Assistant (Wake Word + STT + TTS + Emotion)",
        status=FeatureStatus.BETA,
        description="Wake word detection, speech-to-text, text-to-speech, emotion analysis",
        category="voice",
        health_check_fn="assistant.voice_pipeline:health_check",
        config_key="voice",
        docs_path="VOICE_GUIDE.md",
    ),
    "stt": Feature(
        name="Speech-to-Text (Faster-Whisper, Deepgram, Azure)",
        status=FeatureStatus.STABLE,
        description="STT provider registry with local and cloud providers",
        category="voice",
        config_key="voice.stt_provider",
    ),
    "tts": Feature(
        name="Text-to-Speech (Kokoro, EdgeTTS)",
        status=FeatureStatus.BETA,
        description="TTS provider abstraction with local and cloud options",
        category="voice",
        config_key="voice.tts_provider",
    ),
    "wake_word": Feature(
        name="Wake Word Detection",
        status=FeatureStatus.STABLE,
        description="Two-stage wake word detection with VAD + Whisper confirmation",
        category="voice",
        config_key="voice.wake_word_enabled",
    ),
    "plugin_system": Feature(
        name="Plugin System",
        status=FeatureStatus.STABLE,
        description="Plugin framework with lifecycle, hooks, hot-reload, sandbox, marketplace",
        category="plugins",
        docs_path="PLUGIN_GUIDE.md",
    ),
    "skill_system": Feature(
        name="Skill System",
        status=FeatureStatus.BETA,
        description="Trigger-based skills with hot-reload and registry-based learned procedures",
        category="skills",
        docs_path="SKILL_GUIDE.md",
    ),
    "android_builder": Feature(
        name="Android Builder",
        status=FeatureStatus.BETA,
        description="Autonomous Android build loop with deterministic error repair",
        category="build",
        health_check_fn="brain.automation.loop:health_check",
        docs_path="ANDROID_GUIDE.md",
    ),
    "webhook_system": Feature(
        name="Webhook System",
        status=FeatureStatus.BETA,
        description="Webhook dispatch engine with event-based triggering",
        category="integrations",
        config_key="webhooks",
    ),
    "oauth_login": Feature(
        name="OAuth Login (Google, GitHub, Discord)",
        status=FeatureStatus.STABLE,
        description="User authentication via OAuth2 providers",
        category="integrations",
    ),
    "cli_tool": Feature(
        name="CLI Tool",
        status=FeatureStatus.STABLE,
        description="Command-line interface with 45+ subcommands and slash commands",
        category="core",
        docs_path="docs/README.md",
    ),
    "server_api": Feature(
        name="FastAPI Server",
        status=FeatureStatus.STABLE,
        description="HTTP REST API + WebSocket backend",
        category="core",
        config_key="server",
    ),
    "diagnostics": Feature(
        name="Diagnostics & Doctor",
        status=FeatureStatus.STABLE,
        description="Diagnostic reporting, health monitoring, environment checks",
        category="core",
        health_check_fn="core.diagnostics:build_diagnostic_report",
    ),
    "memory_system": Feature(
        name="Memory System (RAG, Vector, Episodic, Semantic)",
        status=FeatureStatus.STABLE,
        description="Multi-tier memory with RAG, vector search, and persistent storage",
        category="core",
        config_key="memory",
    ),
    "web_search": Feature(
        name="Web Search & Fetch",
        status=FeatureStatus.STABLE,
        description="Web search and content fetching with fallbacks",
        category="core",
        config_key="web_search",
    ),
}

_FEATURE_OVERRIDES: dict[str, FeatureStatus] = {}


def get_status(name: str) -> FeatureStatus:
    if name in _FEATURE_OVERRIDES:
        return _FEATURE_OVERRIDES[name]
    feature = FEATURES.get(name)
    if feature:
        return feature.status
    return FeatureStatus.PLANNED


def set_status(name: str, status: FeatureStatus):
    _FEATURE_OVERRIDES[name] = status


def is_enabled(name: str) -> bool:
    feature = FEATURES.get(name)
    if not feature:
        return False
    if name in _FEATURE_OVERRIDES:
        return _FEATURE_OVERRIDES[name] != FeatureStatus.BROKEN
    try:
        from core.config_registry import config as _cfg
        if feature.config_key:
            stored = _cfg.get(f"feature.{name}.enabled", None)
            if stored is not None:
                return stored
    except KeyError:
        pass
    return feature.enabled_by_default and feature.status not in (FeatureStatus.BROKEN, FeatureStatus.PLANNED)


def get_all_features() -> list[dict[str, Any]]:
    result = []
    for name, feature in sorted(FEATURES.items()):
        result.append({
            "name": feature.name,
            "slug": name,
            "status": get_status(name).value,
            "enabled": is_enabled(name),
            "category": feature.category,
            "description": feature.description,
            "config_key": feature.config_key,
            "dependencies": feature.dependencies,
            "docs_path": feature.docs_path,
        })
    return result


def get_features_by_category(category: str) -> list[dict[str, Any]]:
    return [f for f in get_all_features() if f["category"] == category]


def get_features_by_status(status: FeatureStatus) -> list[dict[str, Any]]:
    return [f for f in get_all_features() if f["status"] == status.value]


def get_feature_report() -> dict[str, Any]:
    features = get_all_features()
    enabled = [f for f in features if f["enabled"]]
    disabled = [f for f in features if not f["enabled"]]
    stable = [f for f in features if f["status"] == "stable"]
    broken = [f for f in features if f["status"] == "broken"]
    beta_features = [f for f in features if f["status"] == "beta"]
    experimental = [f for f in features if f["status"] == "experimental"]
    planned = [f for f in features if f["status"] == "planned"]

    return {
        "total": len(features),
        "enabled": len(enabled),
        "disabled": len(disabled),
        "stable": len(stable),
        "beta": len(beta_features),
        "experimental": len(experimental),
        "broken": len(broken),
        "planned": len(planned),
        "features": features,
        "timestamp": datetime.now().isoformat(),
    }
