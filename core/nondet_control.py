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
"""core/nondet_control.py
Phase 3 (C2): Non-Determinism Control.
Seed-based execution, fixed decision logs, replayable runs.
"""
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DECISION_LOG_DIR = Path.home() / ".jarvis" / "decision_logs"


@dataclass
class DecisionEntry:
    step: str
    decision_type: str  # "agent_select", "plan_step", "template_pick", "retry_strategy"
    choices: list[str]
    chosen: str
    rationale: str = ""
    seeded: bool = False
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "decision_type": self.decision_type,
            "choices": self.choices,
            "chosen": self.chosen,
            "rationale": self.rationale,
            "seeded": self.seeded,
            "timestamp": self.timestamp,
        }


class DecisionLogger:
    def __init__(self):
        self._log: dict[str, list[DecisionEntry]] = {}

    def init_project(self, project: str, seed: int | None = None):
        self._log[project] = []
        path = DECISION_LOG_DIR / project
        path.mkdir(parents=True, exist_ok=True)
        if seed is not None:
            (path / "seed.txt").write_text(str(seed), encoding="utf-8")

    def log(self, project: str, entry: DecisionEntry):
        self._log.setdefault(project, []).append(entry)
        path = DECISION_LOG_DIR / project / "decisions.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def get_log(self, project: str) -> list[DecisionEntry]:
        return self._log.get(project, [])

    def get_seed(self, project: str) -> int | None:
        path = DECISION_LOG_DIR / project / "seed.txt"
        if path.exists():
            try:
                return int(path.read_text(encoding="utf-8").strip())
            except Exception as e:
                logger.exception("[NONDET] seed read: %s", e)
        return None

    def set_seed(self, project: str, seed: int):
        DECISION_LOG_DIR.mkdir(parents=True, exist_ok=True)
        (DECISION_LOG_DIR / project).mkdir(parents=True, exist_ok=True)
        (DECISION_LOG_DIR / project / "seed.txt").write_text(str(seed), encoding="utf-8")

    def replay_mode(self, project: str) -> bool:
        path = DECISION_LOG_DIR / project / "replay.txt"
        return path.exists()

    def enable_replay(self, project: str):
        path = DECISION_LOG_DIR / project
        path.mkdir(parents=True, exist_ok=True)
        (path / "replay.txt").write_text("1", encoding="utf-8")
        logger.info(f"[NONDET] Replay mode enabled for {project}")

    def disable_replay(self, project: str):
        path = DECISION_LOG_DIR / project / "replay.txt"
        if path.exists():
            path.unlink()


class SeedPicker:
    def deterministic_choice(self, project: str, choices: list[str], seed: int) -> str:
        h = hashlib.sha256(f"{project}:{seed}:{','.join(choices)}".encode()).hexdigest()
        idx = int(h[:8], 16) % len(choices)
        return choices[idx]

    def sort_paths(self, paths: list[Path], seed: int) -> list[Path]:
        h = hashlib.sha256(f"{seed}:paths:{len(paths)}".encode()).hexdigest()
        rng_seed = int(h[:8], 16)
        return sorted(paths, key=lambda p: hashlib.sha256(f"{rng_seed}:{str(p)}".encode()).hexdigest())


decision_logger = DecisionLogger()
seed_picker = SeedPicker()
