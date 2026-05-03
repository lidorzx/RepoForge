import re

from app.config import EXTRA_REPOS, SUPPORTED_ARCHITECTURES, SUPPORTED_DISTRO_IDS


PACKAGE_RE = re.compile(r"^[A-Za-z0-9+.-]+$")


def validate_distro_id(value: str) -> str:
    if value not in SUPPORTED_DISTRO_IDS:
        allowed = ", ".join(SUPPORTED_DISTRO_IDS)
        raise ValueError(f"Unsupported distro. Allowed values: {allowed}")
    return value


def validate_architecture(value: str) -> str:
    if value not in SUPPORTED_ARCHITECTURES:
        allowed = ", ".join(SUPPORTED_ARCHITECTURES)
        raise ValueError(f"Unsupported architecture. Allowed values: {allowed}")
    return value


def validate_extra_repos(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for spec in values:
        repo_id, _, version = spec.partition(":")
        version = version.strip() or None
        if repo_id not in EXTRA_REPOS:
            allowed = ", ".join(EXTRA_REPOS.keys())
            raise ValueError(f"Unknown extra repo '{repo_id}'. Allowed: {allowed}")
        repo = EXTRA_REPOS[repo_id]
        if repo["versioned"]:
            if version is None:
                version = str(repo["default_version"])
            if version not in repo["versions"]:
                allowed = ", ".join(str(v) for v in repo["versions"])
                raise ValueError(f"Invalid version '{version}' for repo '{repo_id}'. Allowed: {allowed}")
            canonical = f"{repo_id}:{version}"
        else:
            canonical = repo_id
        if canonical not in seen:
            normalized.append(canonical)
            seen.add(canonical)
    return normalized


def validate_package_name(value: str) -> str:
    if not value or not PACKAGE_RE.fullmatch(value):
        raise ValueError(
            "Package names may contain only letters, numbers, plus, minus, and dot."
        )
    return value
