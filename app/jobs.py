from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4

from app.schemas import JobCreate, JobStatus

MAX_JOB_LOG_LINES = 600


@dataclass
class Job:
    job_id: UUID
    distro_id: str
    architecture: str
    packages: list[str]
    extra_repos: list[str] = field(default_factory=list)
    status: JobStatus = "queued"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    logs: list[str] = field(default_factory=list)
    bundle_file: str | None = None
    bundle_size_bytes: int | None = None
    error: str | None = None

    def to_response(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "distro_id": self.distro_id,
            "architecture": self.architecture,
            "packages": self.packages,
            "extra_repos": self.extra_repos,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "logs": self.logs,
            "bundle_file": self.bundle_file,
            "bundle_size_bytes": self.bundle_size_bytes,
            "error": self.error,
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[UUID, Job] = {}
        self._lock = Lock()

    def create(self, request: JobCreate) -> Job:
        job = Job(
            job_id=uuid4(),
            distro_id=request.distro_id,
            architecture=request.architecture,
            packages=request.packages,
            extra_repos=list(request.extra_repos),
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: UUID) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def update(
        self,
        job_id: UUID,
        *,
        status: JobStatus | None = None,
        log: str | None = None,
        bundle_file: str | None = None,
        bundle_size_bytes: int | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if status is not None:
                job.status = status
            if log is not None:
                timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                job.logs.append(f"{timestamp} {log}")
                if len(job.logs) > MAX_JOB_LOG_LINES:
                    job.logs = job.logs[-MAX_JOB_LOG_LINES:]
            if bundle_file is not None:
                job.bundle_file = bundle_file
            if bundle_size_bytes is not None:
                job.bundle_size_bytes = bundle_size_bytes
            if error is not None:
                job.error = error
            job.updated_at = datetime.now(UTC)
