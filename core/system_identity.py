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
"""core/system_identity.py
Phase 4 (D5): System Identity.
JARVIS knows its own capabilities, limitations, and communicates them.
Provides a self-description the system uses to inform decisions.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SystemIdentity:
    name: str = "JARVIS"
    version: str = "4.0.0"
    capabilities: list = field(default_factory=lambda: [
        "autonomous_build", "web_search", "browser_automation", "voice_interaction",
        "privacy_routing", "memory", "template_generation", "vision_understanding",
        "android_automation", "multi_run", "quality_scoring", "interrupt_override",
        "checkpoints", "decision_logging", "plan_evolution", "memory_decisions",
        "template_intelligence",
    ])
    limitations: list = field(default_factory=lambda: [
        "no_direct_llm_code_generation", "ollama_offline_fallback",
        "no_section_composition_runtime", "no_multi_user",
    ])
    models: dict = field(default_factory=lambda: {
        "orchestrator": "llama3.1:8b",
        "coder": "qwen2.5-coder:3b",
        "vision": "gemma4:e4b",
        "embedding": "nomic-embed-text",
    })
    tools: dict = field(default_factory=lambda: {
        "search": "SearXNG",
        "browser": "Playwright",
        "pc_control": "Open-Interpreter",
        "stt": "Faster-Whisper",
        "tts": "Kokoro",
    })
    build_system: dict = field(default_factory=lambda: {
        "max_parallel_tasks": 2,
        "max_retries": 5,
        "max_runtime_s": 600,
        "templates_available": 131,
    })
    phases_implemented: list = field(default_factory=lambda: [
        "Phase 1: Voice & Privacy",
        "Phase 2: Web & Memory",
        "Phase 3: Mobile & PC Control",
        "Phase 4: Intelligence (Governor, Evolution, Memory, Templates, Identity)",
        "Tier 1 Phase 1: Survival (Budget, Classifier, Conflict, Diagnosis)",
        "Tier 1 Phase 2: Quality (Scoring, Multi-Run, Partial Success)",
        "Tier 1 Phase 3: Control (Interrupt, Determinism, Checkpoints)",
        "Tier 1 Phase 4: Intelligence (Governor, Evolution, Memory, Templates, Identity)",
    ])
    created: str = ""
    last_updated: str = ""

    def __post_init__(self):
        if not self.created:
            self.created = datetime.now().isoformat()
        self.last_updated = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "capabilities": self.capabilities,
            "limitations": self.limitations,
            "models": self.models,
            "tools": self.tools,
            "build_system": self.build_system,
            "phases_implemented": self.phases_implemented,
            "created": self.created,
            "last_updated": self.last_updated,
        }


class SystemIdentityManager:
    def __init__(self):
        self.path = Path.home() / ".jarvis" / "identity.json"
        self._identity: SystemIdentity | None = None
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._identity = SystemIdentity(**data)
            except Exception as e:
                logger.warning(f"[IDENTITY] Load error: {e}")
        if not self._identity:
            self._identity = SystemIdentity()
            self._save()

    def _save(self):
        self._identity.last_updated = datetime.now().isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._identity.to_dict(), indent=2), encoding="utf-8")

    @property
    def identity(self) -> SystemIdentity:
        return self._identity or SystemIdentity()

    def get(self) -> SystemIdentity:
        return self.identity

    def can(self, capability: str) -> bool:
        return capability in self.identity.capabilities

    def has_tool(self, tool: str) -> bool:
        return tool in self.identity.tools.values()

    def get_summary(self) -> str:
        i = self.identity
        caps = ", ".join(i.capabilities[:6]) + (f" +{len(i.capabilities) - 6} more" if len(i.capabilities) > 6 else "")
        return (
            f"{i.name} v{i.version} — {len(i.capabilities)} capabilities, {len(i.tools)} tools.\n"
            f"  Key: {caps}\n"
            f"  Models: {json.dumps(i.models)}"
        )

    def register_capability(self, cap: str):
        if cap not in self._identity.capabilities:
            self._identity.capabilities.append(cap)
            self._save()

    def register_limitation(self, lim: str):
        if lim not in self._identity.limitations:
            self._identity.limitations.append(lim)
            self._save()


system_identity = SystemIdentityManager()
