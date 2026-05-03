import argparse
import sys

from pydantic import ValidationError

from app.bundler import BundleBuilder
from app.jobs import JobStore
from app.schemas import JobCreate


class ConsoleJobStore(JobStore):
    def update(self, *args, **kwargs) -> None:
        log = kwargs.get("log")
        status = kwargs.get("status")
        super().update(*args, **kwargs)
        if status is not None:
            print(f"status: {status}", flush=True)
        if log is not None:
            print(log, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="repoforge",
        description="Build an offline Linux package bundle with dependencies.",
    )
    parser.add_argument(
        "--ubuntu",
        "--ubuntu-version",
        dest="ubuntu_version",
        required=True,
        choices=["20.04", "22.04", "24.04"],
        help="Target Ubuntu version.",
    )
    parser.add_argument(
        "--arch",
        "--architecture",
        dest="architecture",
        default="amd64",
        choices=["amd64"],
        help="Target CPU architecture. Default: amd64.",
    )
    parser.add_argument(
        "packages",
        nargs="+",
        help="Package names to download, for example: curl realmd sssd.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        request = JobCreate(
            ubuntu_version=args.ubuntu_version,
            architecture=args.architecture,
            packages=args.packages,
        )
    except ValidationError as exc:
        print(exc, file=sys.stderr)
        return 2

    store = ConsoleJobStore()
    job = store.create(request)
    store.update(job.job_id, log=f"Created job {job.job_id}")
    BundleBuilder(store).build(job.job_id)

    completed_job = store.get(job.job_id)
    if completed_job is None or completed_job.status != "completed":
        error = completed_job.error if completed_job else "unknown error"
        print(f"Build failed: {error}", file=sys.stderr)
        return 1

    print("")
    print(f"Bundle ready: {completed_job.bundle_file}")
    print(f"Size: {completed_job.bundle_size_bytes or 0} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
