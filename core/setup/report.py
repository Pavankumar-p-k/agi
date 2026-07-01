from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ComponentStatus(Enum):
    OK = "ok"
    MISSING = "missing"
    ERROR = "error"
    SKIPPED = "skipped"


class SetupPhase(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class CheckResult:
    name: str
    status: ComponentStatus
    detail: str = ""
    suggestion: str = ""


@dataclass
class HardwareInfo:
    ram_gb: float = 0
    free_ram_gb: float = 0
    disk_free_gb: float = 0
    cpu: str = ""
    cpu_cores: int = 0
    os: str = ""
    gpu_name: str = ""
    gpu_vram_gb: float = 0
    gpu_type: str = "none"


@dataclass
class ModelRecommendation:
    model_id: str = ""
    name: str = ""
    size_gb: float = 0
    min_ram_gb: float = 0
    reason: str = ""


@dataclass
class SetupReport:
    is_first_run: bool = True

    python: CheckResult = field(default_factory=lambda: CheckResult("Python", ComponentStatus.SKIPPED))
    git: CheckResult = field(default_factory=lambda: CheckResult("Git", ComponentStatus.SKIPPED))
    ollama_installed: CheckResult = field(default_factory=lambda: CheckResult("Ollama", ComponentStatus.SKIPPED))
    ollama_running: CheckResult = field(default_factory=lambda: CheckResult("Ollama service", ComponentStatus.SKIPPED))
    models: CheckResult = field(default_factory=lambda: CheckResult("AI Models", ComponentStatus.SKIPPED))
    playwright: CheckResult = field(default_factory=lambda: CheckResult("Playwright", ComponentStatus.SKIPPED))
    docker: CheckResult = field(default_factory=lambda: CheckResult("Docker", ComponentStatus.SKIPPED))
    config: CheckResult = field(default_factory=lambda: CheckResult("Configuration", ComponentStatus.SKIPPED))
    api_keys: CheckResult = field(default_factory=lambda: CheckResult("API Keys", ComponentStatus.SKIPPED))
    server: CheckResult = field(default_factory=lambda: CheckResult("Server", ComponentStatus.SKIPPED))

    hardware: HardwareInfo = field(default_factory=HardwareInfo)
    installed_models: list[str] = field(default_factory=list)
    recommended_model: ModelRecommendation = field(default_factory=ModelRecommendation)
    has_api_keys: bool = False

    def checks(self) -> list[CheckResult]:
        return [self.python, self.git, self.ollama_installed, self.ollama_running,
                self.models, self.playwright, self.docker, self.config, self.api_keys, self.server]

    def ready_count(self) -> int:
        return sum(1 for c in self.checks() if c.status == ComponentStatus.OK)

    def total_checks(self) -> int:
        return sum(1 for c in self.checks() if c.status != ComponentStatus.SKIPPED)

    def local_ready(self) -> bool:
        """Core local features work without cloud or extra installs."""
        return (self.python.status == ComponentStatus.OK
                and self.ollama_running.status == ComponentStatus.OK
                and self.models.status == ComponentStatus.OK)


@dataclass
class InstallResult:
    component: str
    success: bool
    detail: str = ""


@dataclass
class ValidationResult:
    component: str
    status: ComponentStatus
    detail: str = ""


@dataclass
class DemoResult:
    success: bool
    duration_ms: int = 0
    artifact_path: str = ""
    detail: str = ""


@dataclass
class SetupState:
    """Persistent record of what setup has completed."""
    phase: SetupPhase = SetupPhase.NOT_STARTED
    has_been_run: bool = False
    installed_models: list[str] = field(default_factory=list)
    configured_ollama: bool = False
    configured_playwright: bool = False
    demo_ran: bool = False

    @property
    def completed(self) -> bool:
        return self.phase == SetupPhase.COMPLETE
