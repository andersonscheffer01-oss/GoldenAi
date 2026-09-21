from __future__ import annotations

import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class Job:
    job_id: str
    job_type: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    result: Any = None
    error: str = ""
    cancel_requested: bool = False


class JobManager:
    def __init__(self, max_workers: int = 2):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.jobs: dict[str, Job] = {}
        self.futures: dict[str, Future] = {}

    def submit(self, job_type: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Job:
        job = Job(job_id=str(uuid.uuid4()), job_type=job_type)
        self.jobs[job.job_id] = job
        future = self.executor.submit(self._run, job.job_id, func, *args, **kwargs)
        self.futures[job.job_id] = future
        return job

    def _run(self, job_id: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        job = self.jobs[job_id]
        if job.cancel_requested:
            job.status = JobStatus.CANCELLED
            job.finished_at = datetime.now(timezone.utc).isoformat()
            return None
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc).isoformat()
        try:
            job.result = func(*args, **kwargs)
            job.progress = 1.0
            job.status = JobStatus.COMPLETED
            return job.result
        except Exception as exc:
            job.error = f"{type(exc).__name__}: {exc}"
            job.status = JobStatus.FAILED
            raise
        finally:
            job.finished_at = datetime.now(timezone.utc).isoformat()

    def get(self, job_id: str) -> Job:
        return self.jobs[job_id]

    def cancel(self, job_id: str) -> None:
        job = self.jobs[job_id]
        job.cancel_requested = True
        future = self.futures.get(job_id)
        if future:
            future.cancel()
