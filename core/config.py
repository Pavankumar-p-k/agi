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
import os
from pathlib import Path

from .config_schema import jarvis_config

BASE_DIR = Path(__file__).resolve().parents[1]

HOST = jarvis_config.server.host
PORT = jarvis_config.server.port
ALLOWED_ORIGINS = jarvis_config.server.allowed_origins
SECRET_KEY = jarvis_config.server.secret_key
DEV_MODE = jarvis_config.server.dev_mode
FIREBASE_CREDENTIALS = jarvis_config.server.firebase_credentials

DATABASE_URL = jarvis_config.db.url

OLLAMA_URL = jarvis_config.ollama.url
OLLAMA_MODEL = jarvis_config.ollama.default_model
OLLAMA_PORTS = jarvis_config.ollama.ports

VOSK_MODEL_PATH = jarvis_config.hardware.vosk_model_path

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY") or jarvis_config.get_api_key("claude_api_key")
COPILOT_API_KEY = os.getenv("COPILOT_API_KEY") or jarvis_config.get_api_key("copilot_api_key")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or jarvis_config.get_api_key("github_token")
CODEX_CLI_PATH = jarvis_config.build.codex_cli_path

HYBRID_MAX_RETRIES = jarvis_config.llm.hybrid_max_retries
HYBRID_TIMEOUT_SECONDS = jarvis_config.llm.hybrid_timeout_seconds

SUPABASE_URL = os.getenv("SUPABASE_URL") or jarvis_config.supabase_url
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

FACES_DIR = Path(jarvis_config.hardware.faces_dir)
FACE_RECOGNITION_MODEL = jarvis_config.hardware.face_recognition_model
FACE_DETECTION_BACKEND = jarvis_config.hardware.face_detection_backend
FACE_DISTANCE_THRESHOLD = jarvis_config.hardware.face_distance_threshold
MUSIC_DIR = jarvis_config.hardware.music_dir

MAX_RETRIES = jarvis_config.build.max_retries
DAEMON_MODE = jarvis_config.build.daemon_mode
VAULT_PATH = jarvis_config.build.vault_path
MAX_PARALLEL_BUILDS = jarvis_config.build.max_parallel_builds
PROJECTS_DIR = Path(jarvis_config.build.projects_dir)
