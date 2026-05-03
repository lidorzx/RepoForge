from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.validation import (
    validate_architecture,
    validate_distro_id,
    validate_extra_repos,
    validate_package_name,
)


JobStatus = Literal["queued", "running", "completed", "failed"]


class JobCreate(BaseModel):
    distro_id: str = Field(..., examples=["ubuntu-22.04"])
    architecture: str = Field(default="amd64", examples=["amd64"])
    packages: list[str] = Field(..., min_length=1, max_length=50, examples=[["realmd", "sssd"]])
    extra_repos: list[str] = Field(default_factory=list, examples=[["docker-ce", "kubernetes:1.32"]])

    @field_validator("distro_id")
    @classmethod
    def distro_id_supported(cls, value: str) -> str:
        return validate_distro_id(value)

    @field_validator("architecture")
    @classmethod
    def architecture_supported(cls, value: str) -> str:
        return validate_architecture(value)

    @field_validator("packages")
    @classmethod
    def packages_are_safe(cls, values: list[str]) -> list[str]:
        normalized = []
        seen: set[str] = set()
        for value in values:
            package = validate_package_name(value.strip())
            if package not in seen:
                normalized.append(package)
                seen.add(package)
        return normalized

    @field_validator("extra_repos")
    @classmethod
    def extra_repos_valid(cls, values: list[str]) -> list[str]:
        return validate_extra_repos(values)


class JobResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    distro_id: str
    architecture: str
    packages: list[str]
    extra_repos: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    logs: list[str]
    bundle_file: str | None = None
    bundle_size_bytes: int | None = None
    error: str | None = None


class JobsResponse(BaseModel):
    jobs: list[JobResponse]


class DistroInfo(BaseModel):
    label: str
    family: str
    pkg_ext: str
    codename: str | None = None
    components: list[str] | None = None
    suites: list[str] | None = None


class DistrosResponse(BaseModel):
    distros: dict[str, DistroInfo]


class ExtraRepoInfo(BaseModel):
    label: str
    description: str
    families: list[str]
    versioned: bool
    versions: list[str] | None = None
    default_version: str | None = None
    default_packages: list[str]


class ExtraReposResponse(BaseModel):
    repos: dict[str, ExtraRepoInfo]


class PackageOption(BaseModel):
    id: str
    title: str
    description: str
    distro_families: list[str]
    packages: list[str]


class PackageOptionsResponse(BaseModel):
    options: list[PackageOption]


class HealthResponse(BaseModel):
    status: str
    application: str
    version: str


class SystemStatusResponse(BaseModel):
    docker_cli_available: bool
    docker_cli_path: str | None = None
    docker_server_available: bool
    docker_version: str | None = None
    bundles_dir: str
    workdir: str
    output_uid: int | None = None
    output_gid: int | None = None
