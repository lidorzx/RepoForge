import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tarfile
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.config import (
    BUNDLES_DIR,
    DISTRO_CATALOG,
    DOCKER_BIN,
    DOCKER_TIMEOUT_SECONDS,
    HOST_WORKDIR,
    OUTPUT_GID,
    OUTPUT_UID,
    WORKDIR,
)
from app.jobs import JobStore


class BundleBuildError(RuntimeError):
    pass


class BundleBuilder:
    def __init__(self, store: JobStore) -> None:
        self.store = store

    def build(self, job_id: UUID) -> None:
        job = self.store.get(job_id)
        if job is None:
            return

        self.store.update(job_id, status="running", log="Job started.")
        try:
            bundle_path = self._build_bundle(
                job_id=job_id,
                distro_id=job.distro_id,
                architecture=job.architecture,
                packages=job.packages,
                extra_repos=job.extra_repos,
            )
        except Exception as exc:
            self.store.update(job_id, status="failed", log=f"Build failed: {exc}", error=str(exc))
            return

        self.store.update(
            job_id,
            status="completed",
            log=f"Bundle completed: {bundle_path.name}",
            bundle_file=str(bundle_path),
            bundle_size_bytes=bundle_path.stat().st_size,
        )

    def _build_bundle(
        self,
        *,
        job_id: UUID,
        distro_id: str,
        architecture: str,
        packages: list[str],
        extra_repos: list[str],
    ) -> Path:
        distro = DISTRO_CATALOG[distro_id]
        pkg_ext = str(distro["pkg_ext"])

        job_workdir = WORKDIR / str(job_id)
        output_dir = job_workdir / "output"
        package_dir = output_dir / "packages"
        bundle_root = job_workdir / "bundle"
        bundle_package_dir = bundle_root / "packages"

        if job_workdir.exists():
            shutil.rmtree(job_workdir)
        package_dir.mkdir(parents=True, exist_ok=True)
        BUNDLES_DIR.mkdir(parents=True, exist_ok=True)

        repo_labels = [r.split(":")[0] for r in extra_repos]
        repo_note = f" + extra repos: {', '.join(repo_labels)}" if repo_labels else ""
        self.store.update(job_id, log=f"Using {distro['docker_image']} resolver container{repo_note}.")

        self._run_resolver_container(
            job_id=job_id,
            distro=distro,
            architecture=architecture,
            output_dir=output_dir,
            packages=packages,
            extra_repos=extra_repos,
        )

        pkg_files = sorted(package_dir.glob(f"*.{pkg_ext}"))
        if not pkg_files:
            raise BundleBuildError(f"No .{pkg_ext} files were downloaded.")

        bundle_package_dir.mkdir(parents=True, exist_ok=True)
        for pkg in pkg_files:
            shutil.copy2(pkg, bundle_package_dir / pkg.name)

        checksums = self._write_checksums(bundle_root, bundle_package_dir, pkg_ext)
        self._write_install_script(bundle_root, str(distro["family"]))
        self._write_manifest(
            bundle_root=bundle_root,
            distro_id=distro_id,
            architecture=architecture,
            packages=packages,
            extra_repos=extra_repos,
            distro=distro,
            pkg_files=sorted(bundle_package_dir.glob(f"*.{pkg_ext}")),
        )
        self._write_readme(bundle_root, distro_id, architecture, packages, extra_repos, distro)

        archive_path = BUNDLES_DIR / f"repoforge-bundle-{distro_id}-{job_id}.tar.gz"
        if archive_path.exists():
            archive_path.unlink()
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(bundle_root, arcname=bundle_root.name)

        self._normalize_permissions(job_workdir)
        self._normalize_permissions(archive_path)
        self.store.update(job_id, log=f"Wrote {len(pkg_files)} package files and {checksums.name}.")
        return archive_path

    def _run_resolver_container(
        self,
        *,
        job_id: UUID,
        distro: dict,
        architecture: str,
        output_dir: Path,
        packages: list[str],
        extra_repos: list[str],
    ) -> None:
        family = str(distro["family"])
        if family == "debian":
            container_script = self._apt_script(packages, distro, architecture, extra_repos)
        elif family == "rhel":
            container_script = self._dnf_script(packages, distro, architecture, extra_repos)
        elif family == "suse":
            container_script = self._zypper_script(packages, distro, architecture, extra_repos)
        else:
            raise BundleBuildError(f"Unsupported distro family: {family}")

        docker_bin = shutil.which(DOCKER_BIN)
        if docker_bin is None:
            raise BundleBuildError(
                f"Docker CLI not found: {DOCKER_BIN}. Run with the provided Dockerfile/compose setup "
                "or set REPOFORGE_DOCKER_BIN to the docker client path."
            )
        host_output_dir = HOST_WORKDIR / str(job_id) / "output"
        command = [
            docker_bin, "run", "--rm",
            "--name", f"repoforge-resolver-{job_id}",
            "--label", "com.repoforge.role=resolver",
            "--label", f"com.repoforge.job_id={job_id}",
            "--platform", f"linux/{architecture}",
            "-v", f"{host_output_dir}:/out",
            str(distro["docker_image"]),
            "bash", "-lc", container_script,
        ]
        self.store.update(job_id, log="Launching resolver container.")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            self.store.update(job_id, log=line.rstrip())
        try:
            return_code = process.wait(timeout=DOCKER_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            raise BundleBuildError("Docker resolver timed out.") from exc
        if return_code != 0:
            raise BundleBuildError(f"Docker resolver exited with code {return_code}.")
        self.store.update(job_id, log="Resolver container finished successfully.")

    # ── Repo setup snippets ────────────────────────────────────────────────

    @staticmethod
    def _apt_repo_snippet(repo_id: str, version: str | None, distro: dict, architecture: str) -> str:
        deb_arch = "arm64" if architecture == "arm64" else "amd64"
        docker_image = str(distro["docker_image"])
        distro_type = "ubuntu" if docker_image.startswith("ubuntu") else "debian"
        codename = str(distro["codename"])

        if repo_id == "docker-ce":
            return f"""
echo "--- Adding Docker CE repository ({distro_type}/{codename}) ---"
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/{distro_type}/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch={deb_arch} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/{distro_type} {codename} stable" > /etc/apt/sources.list.d/docker.list
"""
        if repo_id == "kubernetes" and version:
            return f"""
echo "--- Adding Kubernetes {version} repository ---"
apt-get install -y apt-transport-https ca-certificates curl gpg
curl -fsSL https://pkgs.k8s.io/core:/stable:/v{version}/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v{version}/deb/ /" > /etc/apt/sources.list.d/kubernetes.list
"""
        if repo_id == "rancher-rke2" and version:
            ver_minor = ".".join(version.split(".")[:2])
            return f"""
echo "--- Adding Rancher RKE2 {version} repository (Debian/Ubuntu) ---"
apt-get install -y curl gpg
curl -fsSL https://rpm.rancher.io/public.key | gpg --dearmor -o /etc/apt/keyrings/rancher-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/rancher-keyring.gpg] https://apt.rancher.io/rke2/stable/v{ver_minor}/deb/ /" > /etc/apt/sources.list.d/rancher-rke2.list
apt-get update -qq
"""
        return ""

    @staticmethod
    def _dnf_repo_snippet(repo_id: str, version: str | None, distro: dict, architecture: str) -> str:
        rhel_ver = str(distro.get("version", "9"))
        rpm_arch = "aarch64" if architecture == "arm64" else "x86_64"

        if repo_id == "docker-ce":
            return f"""
echo "--- Adding Docker CE repository ---"
dnf install -y --allowerasing curl
curl -fsSL https://download.docker.com/linux/centos/docker-ce.repo -o /etc/yum.repos.d/docker-ce.repo
"""
        if repo_id == "kubernetes" and version:
            return f"""
echo "--- Adding Kubernetes {version} repository ---"
cat > /etc/yum.repos.d/kubernetes.repo << 'REPOEOF'
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v{version}/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v{version}/rpm/repodata/repomd.xml.key
REPOEOF
"""
        if repo_id == "rancher-rke2" and version:
            ver_dash = version.replace(".", "-")
            return f"""
echo "--- Adding Rancher RKE2 {version} repository ---"
curl -fsSL https://rpm.rancher.io/public.key | gpg --import 2>/dev/null || true
cat > /etc/yum.repos.d/rancher-rke2.repo << 'REPOEOF'
[rancher-rke2-common-stable]
name=Rancher RKE2 Common (stable)
baseurl=https://rpm.rancher.io/rke2/stable/common/centos/{rhel_ver}/noarch
enabled=1
gpgcheck=1
gpgkey=https://rpm.rancher.io/public.key

[rancher-rke2-{ver_dash}-{rpm_arch}]
name=Rancher RKE2 v{version} ({rpm_arch})
baseurl=https://rpm.rancher.io/rke2/stable/v{version}/centos/{rhel_ver}/{rpm_arch}
enabled=1
gpgcheck=1
gpgkey=https://rpm.rancher.io/public.key
REPOEOF
"""
        return ""

    @staticmethod
    def _zypper_repo_snippet(repo_id: str, version: str | None, distro: dict, architecture: str) -> str:
        return ""

    # ── Container scripts ──────────────────────────────────────────────────

    @staticmethod
    def _apt_script(
        packages: list[str],
        distro: dict,
        architecture: str,
        extra_repos: list[str],
    ) -> str:
        package_args = " ".join(shlex.quote(p) for p in packages)
        component_args = " ".join(distro["components"])
        archive_host = distro["archive_host"]
        security_host = distro["security_host"]
        source_lines = [
            f"deb http://{security_host} {suite} {component_args}"
            if suite.endswith("-security")
            else f"deb http://{archive_host} {suite} {component_args}"
            for suite in distro["suites"]
        ]
        source_args = " ".join(shlex.quote(line) for line in source_lines)
        label = distro["label"]

        extra_setup = ""
        for spec in extra_repos:
            repo_id, _, version = spec.partition(":")
            extra_setup += BundleBuilder._apt_repo_snippet(repo_id, version or None, distro, architecture)

        return textwrap.dedent(
            f"""
            set -euo pipefail
            export DEBIAN_FRONTEND=noninteractive
            rm -f /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources
            printf '%s\\n' {source_args} > /etc/apt/sources.list
            echo "Configured {label} repositories:"
            cat /etc/apt/sources.list
            apt-get update -qq
            apt-get install -y --no-install-recommends apt-utils apt-rdepends ca-certificates curl gnupg
            {extra_setup}
            apt-get update
            rm -f /var/cache/apt/archives/*.deb
            for pkg in {package_args}; do
              apt-cache show "$pkg" >/dev/null || (echo "Package not found in configured repositories: $pkg" >&2; exit 20)
              echo "Candidate for $pkg:"
              apt-cache policy "$pkg" | sed 's/^/  /'
            done
            apt-get install --download-only -y --reinstall {package_args}
            apt-rdepends {package_args} \\
              | awk '/^[A-Za-z0-9.+-]+$/ {{ print $1 }}' \\
              | sort -u > /out/package-list.txt
            while IFS= read -r pkg; do
              [ -n "$pkg" ] || continue
              apt-get download "$pkg" || true
            done < /out/package-list.txt
            cp -f /var/cache/apt/archives/*.deb /out/packages/ 2>/dev/null || true
            cp -f ./*.deb /out/packages/ 2>/dev/null || true
            find /out/packages -type f -name '*.deb' -printf '%f\\n' | sort
            """
        ).strip()

    @staticmethod
    def _dnf_script(
        packages: list[str],
        distro: dict,
        architecture: str,
        extra_repos: list[str],
    ) -> str:
        package_args = " ".join(shlex.quote(p) for p in packages)

        extra_setup = ""
        for spec in extra_repos:
            repo_id, _, version = spec.partition(":")
            extra_setup += BundleBuilder._dnf_repo_snippet(repo_id, version or None, distro, architecture)

        return textwrap.dedent(
            f"""
            set -euo pipefail
            {extra_setup}
            dnf install -y dnf-plugins-core 2>/dev/null || true
            for pkg in {package_args}; do
              dnf info "$pkg" >/dev/null 2>&1 || (echo "Package not found in configured repositories: $pkg" >&2; exit 20)
              echo "Candidate for $pkg:"
              dnf info "$pkg" 2>/dev/null | grep -E '(Name|Version|Release|Architecture|Repository)' | sed 's/^/  /'
            done
            mkdir -p /out/packages
            dnf download --resolve --destdir=/out/packages {package_args}
            find /out/packages -type f -name '*.rpm' -exec basename {{}} \\; | sort
            """
        ).strip()

    @staticmethod
    def _zypper_script(
        packages: list[str],
        distro: dict,
        architecture: str,
        extra_repos: list[str],
    ) -> str:
        package_args = " ".join(shlex.quote(p) for p in packages)

        extra_setup = ""
        for spec in extra_repos:
            repo_id, _, version = spec.partition(":")
            extra_setup += BundleBuilder._zypper_repo_snippet(repo_id, version or None, distro, architecture)

        return textwrap.dedent(
            f"""
            set -euo pipefail
            zypper --non-interactive --gpg-auto-import-keys refresh
            {extra_setup}
            for pkg in {package_args}; do
              zypper --non-interactive info "$pkg" >/dev/null 2>&1 || (echo "Package not found in configured repositories: $pkg" >&2; exit 20)
              echo "Candidate for $pkg:"
              zypper --non-interactive info "$pkg" | grep -E '(Name|Version|Release|Arch|Repository)' | sed 's/^/  /'
            done
            mkdir -p /out/packages
            zypper --non-interactive install --download-only --no-recommends {package_args}
            find /var/cache/zypp/packages -type f -name '*.rpm' | while IFS= read -r f; do
              cp -f "$f" /out/packages/
            done
            find /out/packages -type f -name '*.rpm' -exec basename {{}} \\; | sort
            """
        ).strip()

    # ── Bundle artifacts ───────────────────────────────────────────────────

    @staticmethod
    def _write_checksums(bundle_root: Path, package_dir: Path, pkg_ext: str) -> Path:
        checksum_path = bundle_root / "checksums.sha256"
        lines = []
        for pkg in sorted(package_dir.glob(f"*.{pkg_ext}")):
            digest = hashlib.sha256(pkg.read_bytes()).hexdigest()
            lines.append(f"{digest}  packages/{pkg.name}")
        checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return checksum_path

    @staticmethod
    def _write_install_script(bundle_root: Path, family: str) -> None:
        install_path = bundle_root / "install.sh"
        if family in ("rhel", "suse"):
            pkg_mgr_note = "zypper / rpm" if family == "suse" else "dnf / yum / rpm"
            install_cmd = (
                "sudo zypper --non-interactive install packages/*.rpm"
                if family == "suse"
                else textwrap.dedent("""\
                    if command -v dnf &>/dev/null; then
                        sudo dnf install -y packages/*.rpm
                    elif command -v yum &>/dev/null; then
                        sudo yum install -y packages/*.rpm
                    else
                        sudo rpm -Uvh packages/*.rpm
                    fi""")
            )
            script = textwrap.dedent(
                f"""\
                #!/usr/bin/env bash
                # RepoForge bundle installer — {'openSUSE / SUSE' if family == 'suse' else 'RHEL / Rocky Linux / AlmaLinux'}
                set -euo pipefail
                cd "$(dirname "$0")"

                usage() {{
                  echo "Usage: $(basename "$0") [OPTION]"
                  echo ""
                  echo "Options:"
                  echo "  (none)       Install all RPMs with {pkg_mgr_note}"
                  echo "  --check      Verify SHA-256 checksums only, do not install"
                  echo "  --list       List all package files in this bundle"
                  echo "  --help       Show this help message"
                  echo ""
                  echo "Examples:"
                  echo "  sudo ./install.sh"
                  echo "  ./install.sh --check"
                  echo "  ./install.sh --list"
                }}

                case "${{1:-}}" in
                  --help)
                    usage; exit 0 ;;
                  --check)
                    echo "Verifying checksums..."
                    sha256sum -c checksums.sha256 && echo "All checksums OK." || {{ echo "Checksum mismatch!" >&2; exit 1; }}
                    exit 0 ;;
                  --list)
                    echo "Package files in this bundle:"
                    ls -lh packages/*.rpm
                    echo ""
                    echo "Total: $(ls packages/*.rpm | wc -l) RPM file(s)"
                    exit 0 ;;
                  "")
                    : ;;
                  *)
                    echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
                esac

                echo "Installing $(ls packages/*.rpm | wc -l) RPM package(s)..."
                {install_cmd}
                echo "Done."
                """
            )
        else:
            script = textwrap.dedent(
                """\
                #!/usr/bin/env bash
                # RepoForge bundle installer — Debian / Ubuntu
                set -euo pipefail
                cd "$(dirname "$0")"

                usage() {
                  echo "Usage: $(basename "$0") [OPTION]"
                  echo ""
                  echo "Options:"
                  echo "  (none)       Install all .deb packages with dpkg"
                  echo "  --make-repo  Build a local APT repository from the bundle"
                  echo "               (requires dpkg-scanpackages from the dpkg-dev package)"
                  echo "  --check      Verify SHA-256 checksums only, do not install"
                  echo "  --list       List all package files in this bundle"
                  echo "  --help       Show this help message"
                  echo ""
                  echo "Examples:"
                  echo "  sudo ./install.sh"
                  echo "  sudo ./install.sh --make-repo"
                  echo "  ./install.sh --check"
                  echo "  ./install.sh --list"
                }

                case "${1:-}" in
                  --help)
                    usage; exit 0 ;;
                  --check)
                    echo "Verifying checksums..."
                    sha256sum -c checksums.sha256 && echo "All checksums OK." || { echo "Checksum mismatch!" >&2; exit 1; }
                    exit 0 ;;
                  --list)
                    echo "Package files in this bundle:"
                    ls -lh packages/*.deb
                    echo ""
                    echo "Total: $(ls packages/*.deb | wc -l) .deb file(s)"
                    exit 0 ;;
                  --make-repo)
                    if ! command -v dpkg-scanpackages >/dev/null 2>&1; then
                      echo "dpkg-scanpackages not found. Install it with:" >&2
                      echo "  sudo apt-get install dpkg-dev" >&2
                      exit 1
                    fi
                    (cd packages && dpkg-scanpackages --multiversion . 2>/dev/null | gzip -9c > Packages.gz)
                    echo ""
                    echo "Local APT repository created at: $(pwd)/packages"
                    echo ""
                    echo "Register it on the target machine:"
                    echo "  echo \"deb [trusted=yes] file:$(pwd)/packages ./\" | sudo tee /etc/apt/sources.list.d/repoforge-local.list"
                    echo "  sudo apt-get update"
                    echo "  sudo apt-get install <package-name>"
                    echo ""
                    echo "Remove when done:"
                    echo "  sudo rm /etc/apt/sources.list.d/repoforge-local.list"
                    exit 0 ;;
                  "")
                    : ;;
                  *)
                    echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
                esac

                echo "Installing $(ls packages/*.deb | wc -l) .deb package(s)..."
                sudo dpkg -i packages/*.deb || sudo apt-get install -f -y
                echo "Done."
                """
            )
        install_path.write_text(script, encoding="utf-8")
        install_path.chmod(0o755)

    @staticmethod
    def _write_manifest(
        *,
        bundle_root: Path,
        distro_id: str,
        architecture: str,
        packages: list[str],
        extra_repos: list[str],
        distro: dict,
        pkg_files: list[Path],
    ) -> None:
        manifest: dict = {
            "requested_packages": packages,
            "extra_repos": extra_repos,
            "distro_id": distro_id,
            "distro_label": distro["label"],
            "distro_family": distro["family"],
            "architecture": architecture,
            "build_timestamp": datetime.now(UTC).isoformat(),
            "package_files": [f"packages/{p.name}" for p in pkg_files],
            "package_count": len(pkg_files),
            "checksum_file": "checksums.sha256",
        }
        if "codename" in distro:
            manifest["codename"] = distro["codename"]
        if "suites" in distro:
            manifest["repositories"] = BundleBuilder._repository_manifest(distro)
        (bundle_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_readme(
        bundle_root: Path,
        distro_id: str,
        architecture: str,
        packages: list[str],
        extra_repos: list[str],
        distro: dict,
    ) -> None:
        package_list = ", ".join(packages)
        family = str(distro["family"])
        label = str(distro["label"])

        extra_repo_section = ""
        if extra_repos:
            lines = "\n".join(f"- `{r}`" for r in extra_repos)
            extra_repo_section = f"\nExtra repositories included:\n\n{lines}\n"

        if family == "rhel":
            install_section = textwrap.dedent(
                """\
                ## Install

                Copy this directory to the target air-gapped server, then run:

                ```bash
                chmod +x install.sh
                ./install.sh
                ```

                The installer detects and runs:

                ```bash
                sudo dnf install -y packages/*.rpm
                ```
                """
            )
        elif family == "suse":
            install_section = textwrap.dedent(
                """\
                ## Install

                Copy this directory to the target air-gapped server, then run:

                ```bash
                chmod +x install.sh
                ./install.sh
                ```

                The installer runs:

                ```bash
                sudo zypper --non-interactive install packages/*.rpm
                ```
                """
            )
        else:
            install_section = textwrap.dedent(
                f"""\
                ## Install Directly With dpkg

                Copy this directory to the target air-gapped server, then run:

                ```bash
                chmod +x install.sh
                ./install.sh
                ```

                ## Optional Local Mini APT Repository

                ```bash
                ./install.sh --make-repo
                echo "deb [trusted=yes] file:$(pwd)/packages ./" | sudo tee /etc/apt/sources.list.d/repoforge-local.list
                sudo apt-get update
                sudo apt-get install {" ".join(packages)}
                ```
                """
            )

        repo_section = ""
        if "suites" in distro:
            repo_lines = "\n".join(
                f"- `{repo}`" for repo in BundleBuilder._repository_manifest(distro)
            )
            repo_section = f"Resolver repositories:\n\n{repo_lines}\n\n"

        (bundle_root / "README.md").write_text(
            textwrap.dedent(
                f"""\
                # RepoForge Package Bundle

                This bundle was generated for **{label}** on **{architecture}**.

                Requested packages: {package_list}
                {extra_repo_section}
                {repo_section}## Verify Package Checksums

                ```bash
                sha256sum -c checksums.sha256
                ```

                {install_section}"""
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _repository_manifest(distro: dict) -> list[str]:
        if distro.get("family") != "debian":
            return []
        components = " ".join(distro["components"])
        repositories = []
        for suite in distro["suites"]:
            host = distro["security_host"] if str(suite).endswith("-security") else distro["archive_host"]
            repositories.append(f"deb http://{host} {suite} {components}")
        return repositories

    @staticmethod
    def _normalize_permissions(path: Path) -> None:
        targets = [path]
        if path.is_dir():
            targets = [path, *path.rglob("*")]

        for target in targets:
            try:
                if target.is_dir():
                    target.chmod(0o775)
                elif target.name == "install.sh":
                    target.chmod(0o775)
                else:
                    target.chmod(0o664)
            except OSError:
                pass

            if OUTPUT_UID is not None or OUTPUT_GID is not None:
                try:
                    uid = OUTPUT_UID if OUTPUT_UID is not None else -1
                    gid = OUTPUT_GID if OUTPUT_GID is not None else -1
                    os.chown(target, uid, gid)
                except OSError:
                    pass
