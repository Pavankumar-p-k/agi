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
"""core/interrupt_override.py
Phase 3 (C1): Interrupt / Override system.
Users can pause builds mid-run, override decisions, modify plans.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

INTERRUPTS_DIR = Path.home() / ".jarvis" / "interrupts"


@dataclass
class OverrideCommand:
    field: str
    value: str

    def apply(self, state_dict: dict) -> dict:
        state_dict[self.field] = self.value
        return state_dict


@dataclass
class InterruptSignal:
    project: str
    action: str  # "pause_after_step", "cancel", "override_plan", "modify_goal"
    payload: dict = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def save(self):
        INTERRUPTS_DIR.mkdir(parents=True, exist_ok=True)
        path = INTERRUPTS_DIR / f"{self.project}.json"
        path.write_text(json.dumps({
            "project": self.project,
            "action": self.action,
            "payload": self.payload,
            "created_at": self.created_at,
        }, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, project: str) -> Optional["InterruptSignal"]:
        path = INTERRUPTS_DIR / f"{project}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return cls(**data)
            except Exception as e:
                logger.warning(f"Failed to load interrupt for {project}: {e}")
        return None

    @classmethod
    def clear(cls, project: str):
        path = INTERRUPTS_DIR / f"{project}.json"
        if path.exists():
            path.unlink()

    @classmethod
    def has_pending(cls, project: str) -> bool:
        path = INTERRUPTS_DIR / f"{project}.json"
        return path.exists()


class InterruptManager:
    def __init__(self):
        self._pending_overrides: dict[str, OverrideCommand] = {}

    def signal_pause(self, project: str):
        InterruptSignal(project=project, action="pause_after_step").save()
        logger.info(f"[INTERRUPT] Pause signaled for {project}")

    def signal_cancel(self, project: str):
        InterruptSignal(project=project, action="cancel").save()
        logger.info(f"[INTERRUPT] Cancel signaled for {project}")

    def signal_override(self, project: str, overrides: dict):
        InterruptSignal(project=project, action="override", payload=overrides).save()
        logger.info(f"[INTERRUPT] Override signaled for {project}: {overrides}")

    def check_and_handle(self, state) -> bool:
        if not InterruptSignal.has_pending(state.project_name):
            return False
        signal = InterruptSignal.load(state.project_name)
        if not signal:
            return False

        if signal.action == "cancel":
            state.status = "cancelled"
            state.log_event("cancelled_by_user", signal.payload)
            logger.info(f"[INTERRUPT] Build cancelled by user: {state.project_name}")
            InterruptSignal.clear(state.project_name)
            return True

        if signal.action == "pause_after_step":
            state.status = "paused"
            state.log_event("paused_by_user", signal.payload)
            logger.info(f"[INTERRUPT] Build paused by user: {state.project_name}")
            InterruptSignal.clear(state.project_name)
            return True

        if signal.action == "override":
            for k, v in signal.payload.items():
                if hasattr(state, k):
                    setattr(state, k, v)
                    state.log_event("overridden", {"field": k, "value": v})
                    logger.info(f"[INTERRUPT] Overrode {k} = {v}")
            InterruptSignal.clear(state.project_name)
            return True

        return False


interrupt_manager = InterruptManager()
