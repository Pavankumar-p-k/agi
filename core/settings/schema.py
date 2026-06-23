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
from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field


class LLMSettings(BaseModel):
    default_model: str = "claude-sonnet-4-20250514"
    ollama_host: str = "http://127.0.0.1:11434"
    planner_model: str = "qwen2.5:7b"
    reasoning_model: str = "llama3.1:8b"
    fast_model: str = "phi3:mini"
    coder_model: str = "qwen3:4b"
    lightweight_model: str = "tinyllama:latest"
    max_response_tokens: int = 512
    vision_model: str | None = None
    ollama_model: str | None = None

class AGISettings(BaseModel):
    autonomous_enabled: bool = False
    confidence_threshold: float = 0.7
    max_agents: int = 8
    agent_timeout_s: int = 120
    pause_before_effectful: bool = False

class DNDSettings(BaseModel):
    dnd_mode: bool = False
    dnd_hours: list[int] = [23, 0, 1, 2, 3, 4, 5, 6]

class MemorySettings(BaseModel):
    backend: Literal["sqlite", "supabase", "auto"] = "auto"
    db_path: str = "ai_os_memory.db"

class VoiceSettings(BaseModel):
    enabled: bool = False
    wake_word: str = "jarvis"
    wake_word_enabled: bool = True
    stt_model: str = "tiny"
    tts_engine: Literal["pyttsx3", "elevenlabs", "edge-tts"] = "pyttsx3"
    tts_voice: str = "am_adam"

class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["*"]
    dev_mode: bool = True
    local_only: bool = True

class LoggingSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    file: str = str(os.path.expanduser("~/.jarvis/jarvis.log"))

class UISettings(BaseModel):
    theme: Literal["dark", "light"] = "dark"
    show_timestamps: bool = False
    debug: bool = False
    debug_search: bool = False
    mode: Literal["chat", "agent"] = "chat"
    aliases: dict[str, str] = Field(default_factory=dict)

class JarvisSettings(BaseModel):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    agi: AGISettings = Field(default_factory=AGISettings)
    dnd: DNDSettings = Field(default_factory=DNDSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    ui: UISettings = Field(default_factory=UISettings)

    # Skills
    enabled_skills: list[str] = []   # empty = all enabled
    disabled_skills: list[str] = []

    # API Keys (Stored as strings, masked in output)
    news_api_key: str | None = None
    openweather_api_key: str | None = None
    alpha_vantage_key: str | None = None
    composio_api_key: str | None = None
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    github_token: str | None = None
    telegram_bot_token: str | None = None
    pexels_api_key: str | None = None
    nvidia_api_key: str | None = None
    discord_bot_token: str | None = None
    slack_bot_token: str | None = None
    slack_app_token: str | None = None
    meta_whatsapp_token: str | None = None
    meta_whatsapp_phone_id: str | None = None
