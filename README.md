# RepoForge
<img width="1990" height="1263" alt="image" src="https://github.com/user-attachments/assets/52bb3028-c3a4-4da4-84c4-ba6e81b996a8" />

RepoForge builds offline Linux package bundles for air-gapped servers. It uses
temporary Docker resolver containers that match the target OS, resolves real
package dependencies, downloads only the required packages, and creates a
downloadable `tar.gz` bundle.

Author: Lidor Eliya

## Supported Targets

- Ubuntu 20.04, 22.04, 24.04
- Debian 11, 12
- Rocky Linux 8, 9
- AlmaLinux 8, 9
- Architectures: `amd64`, `arm64`

Ubuntu/Debian bundles contain `.deb` files. Rocky/Alma bundles contain `.rpm`
files.

## Requirements

- Docker Engine
- Docker Compose plugin
- Internet access for pulling resolver images and downloading packages

RepoForge mounts `/var/run/docker.sock` so the app container can start temporary
resolver containers such as `ubuntu:22.04`, `debian:12`, or `rockylinux:9`.

## Run

```bash
docker compose up -d
```

Open:

```text
http://localhost:8000
```

Rebuild after code changes:

```bash
docker compose up -d --build
```

If generated files are root-owned on the host:

```bash
export REPOFORGE_OUTPUT_UID=$(id -u)
export REPOFORGE_OUTPUT_GID=$(id -g)
docker compose up -d --build
```

## Web UI

1. Select the target OS.
2. Select architecture.
3. Enter packages, comma separated.
4. Optionally select extra repositories.
5. Click `Build Bundle`.
6. Download the completed bundle.

Example package input:

```text
curl, vim, realmd, sssd
```

## CLI

Ubuntu shortcut:

```bash
docker compose run --rm repoforge \
  python -m app.cli --ubuntu 22.04 curl
```

Direct distro ID:

```bash
docker compose run --rm repoforge \
  python -m app.cli --distro rocky-9 realmd sssd adcli
```

Generated archives are written to:

```text
./bundles
```

## Install a Bundle

Copy the downloaded archive to the air-gapped target server:

```bash
tar -xzf repoforge-bundle-*.tar.gz
cd bundle
chmod +x install.sh
./install.sh
```

For Debian-family bundles, `install.sh` runs:

```bash
sudo dpkg -i packages/*.deb || sudo apt-get install -f -y
```

For RHEL-family bundles, `install.sh` uses `dnf`, `yum`, or `rpm` to install
`packages/*.rpm`.

Debian-family bundles can also create a local mini APT repo:

```bash
./install.sh --make-repo
```

## Bundle Contents

Each archive contains:

- `packages/*`
- `install.sh`
- `README.md`
- `manifest.json`
- `checksums.sha256`

## Extra Repositories

Optional extra repositories are selected from the UI and validated by the
backend. Current documented options:

- Docker CE
- Kubernetes

## API

Create a job:

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H 'Content-Type: application/json' \
  -d '{"distro_id":"ubuntu-22.04","architecture":"amd64","packages":["curl"],"extra_repos":[]}'
```

Check job status:

```bash
curl http://localhost:8000/api/jobs/<job_id>
```

Download:

```bash
curl -L -o repoforge-bundle.tar.gz http://localhost:8000/api/jobs/<job_id>/download
```

Useful endpoints:

- `GET /api/health`
- `GET /api/system`
- `GET /api/distros`
- `GET /api/extra-repos`
- `GET /api/package-options`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/download`

## How Resolution Works

For each build, RepoForge starts a fresh temporary Docker container for the
selected OS.

- Ubuntu/Debian: uses APT, `apt-rdepends`, `apt-get --download-only`, and
  `apt-get download`.
- Rocky/Alma: uses DNF and `dnf download --resolve`.

RepoForge does not mirror full repositories. It downloads only the requested
packages and their dependency closure.

## Security Notes

- Package names are strictly validated.
- Distro IDs, architectures, and extra repositories are allowlisted.
- Job IDs are UUIDs.
- Downloads are served only from `./bundles`.
- Subprocess calls use argument arrays, not `shell=True`.
- Docker socket access is powerful. Run RepoForge only on trusted hosts and
  restrict access to the web UI.

## Troubleshooting

If Docker is not detected inside the app, rebuild with the provided Dockerfile:

```bash
docker compose up -d --build
```

If running directly on the host, make sure Docker is installed and in `PATH`, or
set:

```bash
export REPOFORGE_DOCKER_BIN=/path/to/docker
```
