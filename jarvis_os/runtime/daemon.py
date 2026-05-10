from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable


class DaemonService:
    def __init__(self, data_dir: Path, interval_s: float = 5.0) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "daemon_state.json"
        self.interval_s = interval_s
        self._runner: Callable[[], dict[str, Any]] | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = {
            "running": False,
            "ticks": 0,
            "last_tick_at": None,
            "last_result": {},
            "started_at": None,
            "stopped_at": None,
            "interval_s": interval_s,
        }
        self._load()

    def _load(self) -> None:
        if not self.state_file.exists():
            return
        raw = self.state_file.read_text(encoding="utf-8").strip()
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        self._state.update(payload)
        self._state["running"] = False

    def _persist(self) -> None:
        self.state_file.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def bind_runner(self, runner: Callable[[], dict[str, Any]]) -> None:
        self._runner = runner

    def start(self) -> dict[str, Any]:
        if self._thread and self._thread.is_alive():
            return self.status()
        self._stop_event.clear()
        self._state["running"] = True
        self._state["started_at"] = time.time()
        self._state["stopped_at"] = None
        self._persist()

        def _loop() -> None:
            while not self._stop_event.wait(self.interval_s):
                self.tick()

        self._thread = threading.Thread(target=_loop, name="jarvis-os-daemon", daemon=True)
        self._thread.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self.interval_s + 0.5))
        self._state["running"] = False
        self._state["stopped_at"] = time.time()
        self._persist()
        return self.status()

    def tick(self) -> dict[str, Any]:
        result = self._runner() if self._runner is not None else {"triggered": 0, "error": "runner not bound"}
        self._state["ticks"] += 1
        self._state["last_tick_at"] = time.time()
        self._state["last_result"] = result
        self._state["interval_s"] = self.interval_s
        self._persist()
        return self.status()

    def status(self) -> dict[str, Any]:
        alive = bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set())
        payload = dict(self._state)
        payload["running"] = alive if payload["running"] else False
        return payload
