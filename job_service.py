import threading
import time
import uuid
from typing import Any


class JobManager:
    def __init__(self):
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

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
                job["logs"].append(
                    {
                        "time": time.time(),
                        "message": log,
                    }
                )
                job["logs"] = job["logs"][-100:]
            if status is not None:
                job["status"] = status
            if result is not None:
                job["result"] = result
            if error is not None:
                job["error"] = error
            if status in {"done", "error"}:
                job["finished_at"] = time.time()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._jobs.get(job_id)

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
