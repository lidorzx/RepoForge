import os
import shutil
import subprocess
from pathlib import Path
from uuid import UUID

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.bundler import BundleBuilder
from app.config import (
    BUNDLES_DIR,
    DISTRO_CATALOG,
    DOCKER_BIN,
    EXTRA_REPOS,
    OUTPUT_GID,
    OUTPUT_UID,
    PACKAGE_OPTIONS,
    STATIC_DIR,
    WORKDIR,
)
from app.jobs import JobStore
from app.schemas import (
    DistroInfo,
    DistrosResponse,
    ExtraRepoInfo,
    ExtraReposResponse,
    HealthResponse,
    JobCreate,
    JobResponse,
    JobsResponse,
    PackageOptionsResponse,
    SystemStatusResponse,
)


APP_NAME = "Bynet AirBridge Package Studio"
APP_VERSION = "0.3.0"

app = FastAPI(title=APP_NAME, version=APP_VERSION)
store = JobStore()
builder = BundleBuilder(store)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return response


@app.on_event("startup")
def ensure_directories() -> None:
    BUNDLES_DIR.mkdir(parents=True, exist_ok=True)
    WORKDIR.mkdir(parents=True, exist_ok=True)
    for directory in (BUNDLES_DIR, WORKDIR):
        directory.chmod(0o775)
        if OUTPUT_UID is not None or OUTPUT_GID is not None:
            uid = OUTPUT_UID if OUTPUT_UID is not None else -1
            gid = OUTPUT_GID if OUTPUT_GID is not None else -1
            try:
                os.chown(directory, uid, gid)
            except OSError:
                pass


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", application=APP_NAME, version=APP_VERSION)


@app.get("/api/system", response_model=SystemStatusResponse)
def system_status() -> SystemStatusResponse:
    docker_path = shutil.which(DOCKER_BIN)
    docker_version = None
    docker_server_available = False
    if docker_path is not None:
        try:
            process = subprocess.run(
                [docker_path, "version", "--format", "{{.Server.Version}}"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if process.returncode == 0:
                docker_server_available = True
                docker_version = process.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            docker_server_available = False

    return SystemStatusResponse(
        docker_cli_available=docker_path is not None,
        docker_cli_path=docker_path,
        docker_server_available=docker_server_available,
        docker_version=docker_version or None,
        bundles_dir=str(BUNDLES_DIR.resolve()),
        workdir=str(WORKDIR.resolve()),
        output_uid=OUTPUT_UID,
        output_gid=OUTPUT_GID,
    )


@app.get("/api/distros", response_model=DistrosResponse)
def list_distros() -> DistrosResponse:
    distros = {
        distro_id: DistroInfo(
            label=str(info["label"]),
            family=str(info["family"]),
            pkg_ext=str(info["pkg_ext"]),
            codename=str(info["codename"]) if "codename" in info else None,
            components=list(info["components"]) if "components" in info else None,
            suites=list(info["suites"]) if "suites" in info else None,
        )
        for distro_id, info in DISTRO_CATALOG.items()
    }
    return DistrosResponse(distros=distros)


@app.get("/api/extra-repos", response_model=ExtraReposResponse)
def list_extra_repos() -> ExtraReposResponse:
    repos = {
        repo_id: ExtraRepoInfo(
            label=str(info["label"]),
            description=str(info["description"]),
            families=list(info["families"]),
            versioned=bool(info["versioned"]),
            versions=list(info["versions"]) if info.get("versions") else None,
            default_version=str(info["default_version"]) if info.get("default_version") else None,
            default_packages=list(info["default_packages"]),
        )
        for repo_id, info in EXTRA_REPOS.items()
    }
    return ExtraReposResponse(repos=repos)


@app.get("/api/package-options", response_model=PackageOptionsResponse)
def package_options() -> PackageOptionsResponse:
    return PackageOptionsResponse(
        options=[
            {
                "id": str(option["id"]),
                "title": str(option["title"]),
                "description": str(option["description"]),
                "distro_families": list(option["distro_families"]),
                "packages": list(option["packages"]),
            }
            for option in PACKAGE_OPTIONS
        ]
    )


@app.post("/api/jobs", response_model=JobResponse, status_code=202)
def create_job(request: JobCreate, background_tasks: BackgroundTasks) -> JobResponse:
    job = store.create(request)
    store.update(job.job_id, log="Job queued.")
    background_tasks.add_task(builder.build, job.job_id)
    return JobResponse(**job.to_response())


@app.get("/api/jobs", response_model=JobsResponse)
def list_jobs() -> JobsResponse:
    return JobsResponse(jobs=[JobResponse(**job.to_response()) for job in store.list()])


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: UUID) -> JobResponse:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JobResponse(**job.to_response())


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: UUID) -> FileResponse:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != "completed" or not job.bundle_file:
        raise HTTPException(status_code=409, detail="Bundle is not ready.")

    bundle_path = Path(job.bundle_file).resolve()
    bundles_root = BUNDLES_DIR.resolve()
    if bundles_root not in bundle_path.parents or not bundle_path.is_file():
        raise HTTPException(status_code=404, detail="Bundle file not found.")

    return FileResponse(
        bundle_path,
        filename=bundle_path.name,
        media_type="application/gzip",
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
