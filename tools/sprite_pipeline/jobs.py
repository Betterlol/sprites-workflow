"""In-memory export jobs for progress and cooperative cancellation."""

from __future__ import annotations

import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .workbench import ConflictError, ExportCancelled, Project


@dataclass
class ExportJob:
    id: str
    project_id: str
    created_at: float = field(default_factory=time.monotonic)
    status: str = "queued"
    completed: int = 0
    total: int = 0
    phase: str = "等待开始"
    error: str | None = None
    content: bytes | None = None
    filename: str | None = None
    media_type: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def summary(self) -> dict:
        return {"id": self.id, "status": self.status, "completed": self.completed,
                "total": self.total, "phase": self.phase, "error": self.error}


class ExportJobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.jobs: dict[str, ExportJob] = {}
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sprite-export")

    def _prune(self) -> None:
        now = time.monotonic()
        for job_id, job in list(self.jobs.items()):
            if job.status in {"done", "failed", "cancelled"} and now - job.created_at > 600:
                del self.jobs[job_id]
        while len(self.jobs) >= 8:
            finished = [job for job in self.jobs.values() if job.status in {"done", "failed", "cancelled"}]
            if not finished:
                raise ValueError("Too many active exports; wait for a job to finish")
            oldest = min(finished, key=lambda job: job.created_at)
            del self.jobs[oldest.id]

    def start(self, project_id: str, project: Project, data: dict, options: dict,
              revision: str | None, asset_revision: str | None) -> dict:
        with self.lock:
            self._prune()
            job = ExportJob(id=secrets.token_urlsafe(12), project_id=project_id)
            self.jobs[job.id] = job
        self.pool.submit(self._run, job, project, data, options, revision, asset_revision)
        return job.summary()

    def _run(self, job: ExportJob, project: Project, data: dict, options: dict,
             revision: str | None, asset_revision: str | None) -> None:
        def progress(completed: int, total: int, phase: str) -> None:
            with self.lock:
                job.completed, job.total, job.phase = completed, total, phase
        with self.lock:
            job.status = "running"
        try:
            content, filename, media_type = project.export(
                data, options, progress=progress, cancelled=job.cancel_event,
                expected_asset_revision=asset_revision, expected_revision=revision)
            with self.lock:
                if job.cancel_event.is_set():
                    job.status, job.phase = "cancelled", "已取消"
                else:
                    job.content, job.filename, job.media_type = content, filename, media_type
                    job.status, job.phase = "done", "已完成"
        except ExportCancelled:
            with self.lock:
                job.status, job.phase = "cancelled", "已取消"
        except Exception as error:
            with self.lock:
                job.status, job.error = "failed", str(error)

    def _job(self, project_id: str, job_id: str) -> ExportJob:
        job = self.jobs.get(job_id)
        if job is None or job.project_id != project_id:
            raise FileNotFoundError("Unknown export job")
        return job

    def status(self, project_id: str, job_id: str) -> dict:
        with self.lock:
            return self._job(project_id, job_id).summary()

    def cancel(self, project_id: str, job_id: str) -> dict:
        with self.lock:
            job = self._job(project_id, job_id)
            if job.status in {"queued", "running"}:
                job.cancel_event.set()
                job.phase = "正在取消"
            return job.summary()

    def download(self, project_id: str, job_id: str) -> tuple[bytes, str, str]:
        with self.lock:
            job = self._job(project_id, job_id)
            if job.status != "done" or job.content is None:
                raise ConflictError("Export is not complete")
            return job.content, job.filename, job.media_type

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
