"""JARVIS configuration schema."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = False
    dev_mode: bool = False


@dataclass
class SecurityConfig:
    secret_key: str = "test-secret-key-32-chars-long-xxx"
    allowed_origins: list[str] = field(default_factory=lambda: ["*"])


@dataclass
class DatabaseConfig:
    url: str = "sqlite+aiosqlite:///:memory:"


@dataclass
class JarvisConfig:
    server_host: str = "127.0.0.1"
    server_port: int = 8000
    dev_mode: bool = True
    llm_model: str = "ollama/qwen2.5:3b"
    data_dir: str = "data"
    server: ServerConfig = field(default_factory=ServerConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    raw_config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "JarvisConfig":
        return cls()

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw_config.get(key, default)


# Module-level singleton used across the app (jarvis_config).
jarvis_config = JarvisConfig()
