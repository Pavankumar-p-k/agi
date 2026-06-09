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

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def validate_events(events: str) -> list[str]:
    valid = {"chat.completed", "session.created", "agent.started", "agent.completed"}
    parts = [e.strip() for e in events.replace(",", " ").split() if e.strip()]
    return [e for e in parts if e in valid]


def validate_webhook_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid scheme: {parsed.scheme}")
    if not parsed.netloc:
        raise ValueError("Missing hostname")
    return url
