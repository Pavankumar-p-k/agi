from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class JarvisConfig:
    workspace_root: Path
    data_dir: Path
    legacy_backend_root: str = ""
    api_host: str = "127.0.0.1"
    api_port: int = 8011
    ollama_base_url: str = "http://127.0.0.1:11434"
    model_provider: str = "ollama"
    model_api_base_url: str = ""
    model_api_generate_path: str = "/generate"
    model_api_stream_path: str = "/generate"
    model_api_status_path: str = "/health"
    model_api_models_path: str = "/models"
    default_models: dict[str, str] = field(
        default_factory=lambda: {
            "chat": "llama3.1:8b",
            "reasoning": "llama3.1:8b",
            "coding": "qwen2.5-coder:3b",
            "analysis": "mistral:7b",
        }
    )
    allow_network: bool = True
    strict_policy: bool = True
    daemon_interval_s: float = 5.0
    max_plan_steps: int = 8
    shell_timeout_s: int = 30
    browser_headless: bool = True
    short_term_limit: int = 40
    log_level: str = "INFO"
    log_file: str = ""
    plugin_roots: list[Path] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["workspace_root"] = str(self.workspace_root)
        payload["data_dir"] = str(self.data_dir)
        payload["plugin_roots"] = [str(path) for path in self.plugin_roots]
        return payload

    @classmethod
    def from_env(cls) -> "JarvisConfig":
        workspace_root = Path(os.getenv("JARVIS_WORKSPACE_ROOT", Path.cwd())).resolve()
        data_dir = Path(os.getenv("JARVIS_DATA_DIR", workspace_root / "data" / "jarvis_os")).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            workspace_root=workspace_root,
            data_dir=data_dir,
            legacy_backend_root=os.getenv("JARVIS_LEGACY_BACKEND_ROOT", "").strip(),
            api_host=os.getenv("JARVIS_API_HOST", "127.0.0.1").strip() or "127.0.0.1",
            api_port=int(os.getenv("JARVIS_API_PORT", "8011")),
            ollama_base_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            model_provider=os.getenv("JARVIS_MODEL_PROVIDER", "ollama").strip().lower() or "ollama",
            model_api_base_url=os.getenv("JARVIS_MODEL_API_BASE_URL", "").rstrip("/"),
            model_api_generate_path=os.getenv("JARVIS_MODEL_API_GENERATE_PATH", "/generate"),
            model_api_stream_path=os.getenv("JARVIS_MODEL_API_STREAM_PATH", os.getenv("JARVIS_MODEL_API_GENERATE_PATH", "/generate")),
            model_api_status_path=os.getenv("JARVIS_MODEL_API_STATUS_PATH", "/health"),
            model_api_models_path=os.getenv("JARVIS_MODEL_API_MODELS_PATH", "/models"),
            allow_network=os.getenv("JARVIS_ALLOW_NETWORK", "1").lower() not in {"0", "false", "no"},
            strict_policy=os.getenv("JARVIS_STRICT_POLICY", "1").lower() not in {"0", "false", "no"},
            daemon_interval_s=float(os.getenv("JARVIS_DAEMON_INTERVAL_S", "5")),
            max_plan_steps=int(os.getenv("JARVIS_MAX_PLAN_STEPS", "8")),
            shell_timeout_s=int(os.getenv("JARVIS_SHELL_TIMEOUT_S", "30")),
            browser_headless=os.getenv("JARVIS_BROWSER_HEADLESS", "1").lower() not in {"0", "false", "no"},
            short_term_limit=int(os.getenv("JARVIS_SHORT_TERM_LIMIT", "40")),
            log_level=os.getenv("JARVIS_LOG_LEVEL", "INFO").strip().upper() or "INFO",
            log_file=os.getenv("JARVIS_LOG_FILE", "").strip(),
            plugin_roots=[
                Path(part.strip()).expanduser().resolve()
                for part in os.getenv("JARVIS_PLUGIN_ROOTS", "").split(os.pathsep)
                if part.strip()
            ],
        )
