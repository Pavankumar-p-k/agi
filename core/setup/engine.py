"""SetupEngine — orchestrates first-run setup.

Usage:
    engine = SetupEngine()
    report = engine.detect()          # detect everything
    engine.install_playwright()       # install missing component
    engine.pull_model("llama3.2:3b")  # download model
    engine.configure(model_id=..., api_keys=...)
    engine.validate()                 # verify everything
    engine.run_demo()                 # 20-second "hello.html"
    engine.complete()                 # mark setup done
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable

from core.setup.detector import detect_all, is_first_run
from core.setup.installer import (
    ensure_ollama_running,
    install_playwright,
    pull_ollama_model,
)
from core.setup.configurator import (
    configure_api_keys,
    load_settings,
    load_setup_state,
    mark_setup_complete,
    mark_setup_failed,
    mark_setup_in_progress,
    save_settings,
    save_setup_state,
    set_default_model,
)
from core.setup.report import (
    DemoResult,
    InstallResult,
    SetupPhase,
    SetupReport,
    SetupState,
    ValidationResult,
)
from core.setup.validator import validate_all, validate_server

logger = logging.getLogger(__name__)


class SetupEngine:
    """Orchestrates JARVIS first-run setup.

    Callbacks allow CLI/Web/TUI to handle user interaction while
    the engine stays pure logic.
    """

    def __init__(self) -> None:
        self.state: SetupState = load_setup_state()
        self._report: SetupReport | None = None

    # ── Detection ──

    def detect(self) -> SetupReport:
        """Detect all components and return a full report."""
        self._report = detect_all()
        return self._report

    def needs_setup(self) -> bool:
        """True if setup has never been started."""
        return is_first_run()

    def resume_needed(self) -> bool:
        """True if setup was interrupted (IN_PROGRESS or FAILED)."""
        return self.state.phase in (SetupPhase.IN_PROGRESS, SetupPhase.FAILED)

    def status(self) -> dict[str, Any]:
        """Return a JSON-serializable status snapshot."""
        report = self.detect()
        return {
            "phase": self.state.phase.value,
            "has_been_run": self.state.has_been_run,
            "demo_ran": self.state.demo_ran,
            "installed_models": self.state.installed_models,
            "configured_ollama": self.state.configured_ollama,
            "configured_playwright": self.state.configured_playwright,
            "hardware": {
                "ram_gb": report.hardware.ram_gb,
                "gpu_type": report.hardware.gpu_type,
                "gpu_name": report.hardware.gpu_name,
                "os": report.hardware.os,
            },
            "checks": {
                "python": report.python.status.value,
                "git": report.git.status.value,
                "ollama_installed": report.ollama_installed.status.value,
                "ollama_running": report.ollama_running.status.value,
                "models": report.models.status.value,
                "playwright": report.playwright.status.value,
                "docker": report.docker.status.value,
                "config": report.config.status.value,
                "api_keys": report.api_keys.status.value,
            },
            "recommended_model": {
                "id": report.recommended_model.model_id,
                "name": report.recommended_model.name,
                "size_gb": report.recommended_model.size_gb,
            },
            "local_ready": report.local_ready(),
        }

    # ── Installation ──

    def ensure_ollama(self, on_progress: Callable[[str], None] | None = None) -> InstallResult:
        if on_progress:
            on_progress("Starting Ollama...")
        result = ensure_ollama_running()
        if result.success:
            self.state.configured_ollama = True
        return result

    def install_playwright(self, on_progress: Callable[[str], None] | None = None) -> InstallResult:
        if on_progress:
            on_progress("Installing Playwright and browser...")
        result = install_playwright()
        if result.success:
            self.state.configured_playwright = True
        return result

    def pull_model(self, model_id: str, on_progress: Callable[[str], None] | None = None) -> InstallResult:
        if on_progress:
            on_progress(f"Downloading {model_id}...")
        result = pull_ollama_model(model_id)
        if result.success:
            if model_id not in self.state.installed_models:
                self.state.installed_models.append(model_id)
        return result

    # ── Configuration ──

    def configure(self, model_id: str | None = None,
                  api_keys: dict[str, str] | None = None) -> list[InstallResult]:
        results: list[InstallResult] = []
        if model_id:
            results.append(set_default_model(model_id))
        if api_keys:
            results.append(configure_api_keys(api_keys))
        return results

    # ── Validation ──

    def validate(self) -> list[ValidationResult]:
        return validate_all()

    def is_server_ready(self) -> bool:
        result = validate_server()
        return result.status.value == "ok"

    # ── Demo ──

    def run_demo(self, on_progress: Callable[[str], None] | None = None) -> DemoResult:
        """Build a hello.html file as a 20-second demo."""
        if on_progress:
            on_progress("Running 20-second demo...")

        from core.setup.demo import run_hello_demo
        start = time.monotonic()
        result = run_hello_demo(on_progress)
        elapsed = int((time.monotonic() - start) * 1000)

        demo_result = DemoResult(
            success=result.success,
            duration_ms=elapsed,
            artifact_path=result.detail if result.success else "",
            detail=result.detail,
        )
        if demo_result.success:
            self.state.demo_ran = True
        return demo_result

    # ── Completion ──

    def complete(self) -> None:
        """Mark setup as complete."""
        mark_setup_complete(self.state)

    def is_complete(self) -> bool:
        return self.state.phase == SetupPhase.COMPLETE

    # ── Full flow ──

    def run_full_setup(
        self,
        on_message: Callable[[str], None] = print,
        on_confirm: Callable[[str], bool] = lambda msg: True,
        on_choice: Callable[[str, list[str]], str | None] = lambda q, opts: opts[0] if opts else None,
    ) -> bool:
        """Run the complete setup flow with user interaction callbacks.

        Args:
            on_message: Display a message to the user (str -> None)
            on_confirm: Ask yes/no (prompt -> bool)
            on_choice: Ask a multiple-choice question (question, options -> selected option or None)

        Returns:
            True if setup completed successfully
        """
        is_resume = self.state.phase == SetupPhase.IN_PROGRESS
        label = "Resuming" if is_resume else "Running"
        on_message(f"\n{label} first-time setup...\n")

        # Mark IN_PROGRESS immediately so CTRL+C/power loss is recoverable
        mark_setup_in_progress(self.state)

        try:
            # Step 1: Detect
            report = self.detect()
            on_message(f"  {'✓' if report.python.status.value == 'ok' else 'x'} Python {report.python.detail}")
            on_message(f"  {'✓' if report.git.status.value == 'ok' else '○'} Git {report.git.detail}")

            # Step 2: Ollama
            if report.ollama_installed.status.value == "ok":
                on_message("  ✓ Ollama installed")
            else:
                on_message("  ○ Ollama not found — install from https://ollama.com")

            if report.ollama_running.status.value == "ok":
                on_message("  ✓ Ollama running")
            else:
                on_message("  Starting Ollama...")
                self.ensure_ollama(on_progress=on_message)

            # Step 3: Model
            if report.models.status.value == "ok":
                on_message(f"  ✓ Models: {report.recommended_model.name}")
            else:
                rec = report.recommended_model
                msg = f"  No model found. Recommended: {rec.name} ({rec.size_gb}GB)"
                on_message(msg)
                if on_confirm(f"Download {rec.name} ({rec.size_gb}GB)? (Y/n)"):
                    self.pull_model(rec.model_id, on_progress=on_message)

            # Step 4: Playwright
            if report.playwright.status.value != "ok":
                if on_confirm("\nBrowser automation requires Playwright. Install now? (Y/n)"):
                    self.install_playwright(on_progress=on_message)
                else:
                    on_message("  ○ Skipped Playwright")

            # Step 5: API keys
            if not report.has_api_keys:
                choice = on_choice(
                    "Configure API keys for cloud providers?",
                    ["Skip (local mode only)", "OpenAI", "Gemini", "Both"],
                )
                if choice and choice != "Skip (local mode only)":
                    keys = {}
                    if "OpenAI" in choice:
                        val = self._prompt_for_key("OpenAI API key (skippable)")
                        if val:
                            keys["OPENAI_API_KEY"] = val
                    if "Gemini" in choice:
                        val = self._prompt_for_key("Gemini API key (skippable)")
                        if val:
                            keys["GEMINI_API_KEY"] = val
                    if keys:
                        self.configure(api_keys=keys)

            # Step 6: Configure
            self.configure(model_id=report.recommended_model.model_id)
            on_message(f"\n  ✓ Default model set to {report.recommended_model.name}")

            # Step 7: Demo — never blocks, always optional
            if not is_resume and on_confirm("\nRun 20-second demo?"):
                on_message("")
                result = self.run_demo(on_progress=on_message)
                if result.success:
                    on_message(f"  ✓ Demo complete ({result.duration_ms}ms)")
                else:
                    on_message(f"  ○ Demo skipped: {result.detail}")

            # Step 8: Complete
            self.complete()
            on_message("\n  ✓ Setup complete.")
            return True

        except (KeyboardInterrupt, Exception) as e:
            if isinstance(e, KeyboardInterrupt):
                logger.info("Setup interrupted by user")
                on_message("\n  ○ Setup interrupted — progress saved. Resume by running 'jarvis' again.")
            else:
                logger.warning("Setup failed: %s", e)
                on_message(f"\n  x Setup failed: {e}")
            mark_setup_failed(self.state)
            return False

    def _prompt_for_key(self, label: str) -> str | None:
        """Override in CLI/Web to actually prompt. Default: ask env."""
        import os as _os
        val = _os.getenv(label.replace(" ", "_").upper())
        return val
