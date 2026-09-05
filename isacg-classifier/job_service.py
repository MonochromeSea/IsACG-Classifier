import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any


logger = logging.getLogger("isacg")

TERMINAL_STATUSES = {"done", "error", "cancelled", "interrupted"}


class JobManager:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._events: dict[str, dict[str, threading.Event]] = {}
        self._lock = threading.Lock()
        self._save_interval = self._read_float_env("JOB_SAVE_INTERVAL", 0.75)
        self._history_limit = self._read_int_env("JOB_HISTORY_LIMIT", 30)
        self._last_save = 0.0
        self._load()

    @staticmethod
    def _read_float_env(name: str, default: float) -> float:
        try:
            return max(0.1, float(os.environ.get(name, default)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _read_int_env(name: str, default: int) -> int:
        try:
            return max(1, int(os.environ.get(name, default)))
        except (TypeError, ValueError):
            return default

    def _prune_locked(self):
        if len(self._jobs) <= self._history_limit:
            return
        removable = sorted(
            (
                job
                for job in self._jobs.values()
                if job.get("status") in TERMINAL_STATUSES
            ),
            key=lambda item: item.get("started_at", 0),
        )
        remove_count = max(0, len(self._jobs) - self._history_limit)
        for job in removable[:remove_count]:
            job_id = job.get("id")
            if not job_id:
                continue
            self._jobs.pop(job_id, None)
            self._events.pop(job_id, None)

    def _load(self):
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            data = {}
        for job_id, job in data.items():
            if job.get("status") == "running":
                job["status"] = "interrupted"
                job["message"] = "程序异常关闭，任务已中断，可查看已保存的结果"
                job.setdefault("logs", []).append(
                    {"time": time.time(), "message": "检测到异常关闭，标记为已中断"}
                )
            self._jobs[job_id] = job
            self._events[job_id] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
            }
        with self._lock:
            self._prune_locked()
        self._save(force=True)

    def _save(self, *, force: bool = False):
        with self._lock:
            now = time.monotonic()
            if not force and now - self._last_save < self._save_interval:
                return
            self._prune_locked()
            try:
                self.storage_path.write_text(
                    json.dumps(self._jobs, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self._last_save = now
            except OSError:
                pass

    def create(self, kind: str) -> str:
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "kind": kind,
            "status": "running",
            "progress": 0,
            "total": 0,
            "message": "准备中...",
            "logs": [],
            "result": None,
            "error": None,
            "started_at": time.time(),
            "finished_at": None,
        }
        with self._lock:
            self._jobs[job_id] = job
            self._events[job_id] = {
                "pause": threading.Event(),
                "cancel": threading.Event(),
            }
            self._prune_locked()
        self._save(force=True)
        return job_id

    def update(
        self,
        job_id: str,
        *,
        progress: int | None = None,
        total: int | None = None,
        message: str | None = None,
        log: str | None = None,
        status: str | None = None,
        result: Any = None,
        error: str | None = None,
    ):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if progress is not None:
                job["progress"] = progress
            if total is not None:
                job["total"] = total
            if message is not None:
                job["message"] = message
            if log is not None:
                job["logs"].append({"time": time.time(), "message": log})
                job["logs"] = job["logs"][-100:]
                logger.info("[%s:%s] %s", job.get("kind", "job"), job_id[:8], log)
            if status is not None:
                job["status"] = status
            if result is not None:
                job["result"] = result
            if error is not None:
                job["error"] = error
            if status in TERMINAL_STATUSES:
                job["finished_at"] = time.time()
        self._save(force=status is not None or error is not None)

    def get(self, job_id: str, *, include_result: bool = True) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            snapshot = dict(job)
            if not include_result:
                snapshot.pop("result", None)
            return snapshot

    def recent(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._jobs:
                return None
            latest = max(self._jobs.values(), key=lambda item: item.get("started_at", 0))
            return dict(latest)

    def request_cancel(self, job_id: str):
        events = self._events.get(job_id)
        if events:
            events["cancel"].set()
            events["pause"].clear()

    def request_pause(self, job_id: str):
        events = self._events.get(job_id)
        if events:
            events["pause"].set()

    def request_resume(self, job_id: str):
        events = self._events.get(job_id)
        if events:
            events["pause"].clear()

    def is_cancelled(self, job_id: str) -> bool:
        events = self._events.get(job_id)
        return bool(events and events["cancel"].is_set())

    def wait_if_paused(self, job_id: str):
        events = self._events.get(job_id)
        if not events:
            return
        while events["pause"].is_set() and not events["cancel"].is_set():
            time.sleep(0.1)

    def run(self, kind: str, func, *args) -> str:
        job_id = self.create(kind)

        def runner():
            try:
                func(job_id, *args)
            except Exception as exc:
                self.update(job_id, status="error", error=str(exc), message="任务失败")

        thread = threading.Thread(target=runner, name=f"job-{kind}", daemon=True)
        thread.start()
        return job_id
