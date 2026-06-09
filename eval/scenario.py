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

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


@dataclass
class EvalScenario:
    id: str
    prompt: str
    name: str = ""
    expected_tools: list[str] | None = None
    forbidden_tools: list[str] | None = None
    expected_patterns: list[str] | None = None
    forbidden_patterns: list[str] | None = None
    min_rounds: int = 0
    max_rounds: int = 10
    tags: list[str] = field(default_factory=list)
    model_override: str | None = None
    extra_params: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.name:
            self.name = self.id


@dataclass
class ScenarioResult:
    scenario_id: str
    prompt: str
    full_response: str
    tool_calls: list[dict]
    round_count: int
    total_duration: float
    events: list[str]
    error: str | None = None
    metrics: dict | None = None


def load_scenarios(path: str | Path) -> list[EvalScenario]:
    path = Path(path)
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.glob("**/*.yml")) + sorted(path.glob("**/*.yaml"))
    else:
        raise FileNotFoundError(f"Eval scenarios path not found: {path}")

    scenarios = []
    for f in files:
        if yaml is None:
            text = f.read_text(encoding="utf-8")
            try:
                import json
                data = json.loads(text)
            except json.JSONDecodeError:
                logger.warning("PyYAML not installed and %s is not valid JSON; skipping", f)
                continue
        else:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))

        entries = data if isinstance(data, list) else data.get("scenarios", [data])
        for entry in entries:
            scenarios.append(EvalScenario(**entry))

    logger.info("Loaded %d eval scenarios from %s", len(scenarios), path)
    return scenarios


def save_results(results: list[ScenarioResult], path: str | Path) -> Path:
    path = Path(path)
    rows = []
    for r in results:
        d = asdict(r)
        d["timestamp"] = datetime.now(timezone.utc).isoformat()
        rows.append(d)
    path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    logger.info("Saved %d results to %s", len(results), path)
    return path


def load_results(path: str | Path) -> list[dict]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))
