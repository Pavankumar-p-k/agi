from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from ..contracts import JobRecord


class JobControl:
    def __init__(self, manager: "JobManager", job_id: str) -> None:
        self.manager = manager
        self.job_id = job_id
        self._resume_event = threading.Event()
        self._resume_event.set()

    def request_pause(self) -> None:
        self._resume_event.clear()

    def resume(self) -> None:
        self._resume_event.set()

    def wait_if_paused(self) -> None:
        if self._resume_event.is_set():
            return
        self.manager.update(self.job_id, status="paused")
        self._resume_event.wait()
        self.manager.update(self.job_id, status="running")


class JobManager:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_file = self.data_dir / "jobs.json"
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._controls: dict[str, JobControl] = {}
        self._load()

    def _load(self) -> None:
        if not self.jobs_file.exists():
            return
        raw = self.jobs_file.read_text(encoding="utf-8").strip()
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = []
        reconciled = False
        for item in payload:
            record = JobRecord(**item)
            if record.status == "running":
                record.status = "paused"
                record.error = record.error or "Recovered an interrupted job after restart. Resume it to continue from the last checkpoint."
                record.updated_at = time.time()
                reconciled = True
            self._jobs[record.job_id] = record
        if reconciled:
            self._persist()

    def _persist(self) -> None:
        self.jobs_file.parent.mkdir(parents=True, exist_ok=True)
        serializable = [record.to_dict() for record in sorted(self._jobs.values(), key=lambda item: item.created_at)]
        self.jobs_file.write_text(json.dumps(serializable, indent=2), encoding="utf-8")

    def create(
        self,
        prompt: str,
        agent_name: str = "auto",
        *,
        context: dict[str, Any] | None = None,
        plan: dict[str, Any] | None = None,
        preview: dict[str, Any] | None = None,
    ) -> JobRecord:
        with self._lock:
            job = JobRecord(
                job_id=f"job_{uuid.uuid4().hex[:10]}",
                prompt=prompt,
                status="queued",
                agent_name=agent_name,
                context=dict(context or {}),
                plan=dict(plan or {}),
                preview=dict(preview or {}),
                checkpoint={"next_step_index": 0, "results": []},
            )
            self._jobs[job.job_id] = job
            self._controls.setdefault(job.job_id, JobControl(self, job.job_id))
            self._persist()
            return job

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        result: dict[str, Any] | None = None,
        error: str = "",
        checkpoint: dict[str, Any] | None = None,
    ) -> JobRecord:
        with self._lock:
            job = self._jobs[job_id]
            if status is not None:
                job.status = status
            if result is not None:
                job.result = result
            if error:
                job.error = error
            if checkpoint is not None:
                job.checkpoint = dict(checkpoint)
            job.updated_at = time.time()
            self._persist()
            return job

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[JobRecord]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for job in self.list():
            counts[job.status] = counts.get(job.status, 0) + 1
        return counts

    def control(self, job_id: str) -> JobControl:
        with self._lock:
            return self._controls.setdefault(job_id, JobControl(self, job_id))

    def record_checkpoint(self, job_id: str, checkpoint: dict[str, Any]) -> JobRecord:
        return self.update(job_id, checkpoint=checkpoint)

    def submit(
        self,
        prompt: str,
        agent_name: str,
        runner: Callable[[JobRecord, JobControl], dict[str, Any]],
        *,
        context: dict[str, Any] | None = None,
        plan: dict[str, Any] | None = None,
        preview: dict[str, Any] | None = None,
    ) -> JobRecord:
        job = self.create(prompt=prompt, agent_name=agent_name, context=context, plan=plan, preview=preview)
        self._start_thread(job.job_id, runner)
        return job

    def pause(self, job_id: str) -> JobRecord | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in {"completed", "failed"}:
                return job
            control = self._controls.setdefault(job_id, JobControl(self, job_id))
            control.request_pause()
            if job.status == "queued":
                job.status = "paused"
                job.updated_at = time.time()
                self._persist()
            return job

    def resume(self, job_id: str, runner: Callable[[JobRecord, JobControl], dict[str, Any]]) -> JobRecord | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in {"completed", "failed"}:
                return job
            control = self._controls.setdefault(job_id, JobControl(self, job_id))
            control.resume()
            thread = self._threads.get(job_id)
            alive = bool(thread and thread.is_alive())
            job.status = "running" if alive else "queued"
            job.updated_at = time.time()
            self._persist()
        if not alive:
            self._start_thread(job_id, runner)
        return self.get(job_id)

    def _start_thread(self, job_id: str, runner: Callable[[JobRecord, JobControl], dict[str, Any]]) -> None:
        control = self.control(job_id)

        def _target() -> None:
            # Preserve a visible queued state long enough for monitoring snapshots.
            time.sleep(0.02)
            self.update(job_id, status="running")
            try:
                job = self.get(job_id)
                if job is None:
                    return
                result = runner(job, control)
                status = "completed" if result.get("execution", {}).get("success", False) else result.get("status", "failed")
                self.update(job_id, status=status, result=result)
            except Exception as exc:
                self.update(job_id, status="failed", error=str(exc))

        thread = threading.Thread(target=_target, name=job_id, daemon=True)
        self._threads[job_id] = thread
        thread.start()

    def wait_all(self, timeout_s: float = 5.0) -> None:
        deadline = time.time() + timeout_s
        for job_id, thread in list(self._threads.items()):
            remaining = max(0.0, deadline - time.time())
            if thread.is_alive():
                thread.join(timeout=remaining)
            if not thread.is_alive():
                self._threads.pop(job_id, None)
