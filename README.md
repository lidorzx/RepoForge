# RepoForge

RepoForge is a FastAPI web application for building offline Linux package
bundles for air-gapped servers. It resolves packages inside temporary Docker
containers that match the selected target distribution, downloads only the
requested packages and dependencies, and produces a downloadable `tar.gz`
archive.

Author: Lidor Eliya

## Supported Targets

RepoForge currently supports:

- Ubuntu 20.04 LTS `focal`
- Ubuntu 22.04 LTS `jammy`
- Ubuntu 24.04 LTS `noble`
- Debian 11 `bullseye`
- Debian 12 `bookworm`
- Rocky Linux 8
- Rocky Linux 9
- AlmaLinux 8
- AlmaLinux 9

Architectures:

- `amd64`
- `arm64`

Debian-family targets produce `.deb` bundles. RHEL-family targets produce `.rpm`
bundles.

## What a Bundle Contains

Each generated archive contains:

- `packages/*`
- `install.sh`
- `README.md`
- `manifest.json`
- `checksums.sha256`

The package files are `.deb` for Ubuntu/Debian targets and `.rpm` for
Rocky Linux / AlmaLinux targets.

## Requirements

- Docker Engine
- Docker Compose plugin
- Internet access from the host for pulling resolver images and downloading packages

The compose setup mounts `/var/run/docker.sock` so the web app can start
temporary resolver containers such as `ubuntu:22.04`, `debian:12`,
`rockylinux:9`, or `almalinux:9`.

The app image includes the Docker CLI and uses the mounted Docker socket to start
resolver containers on the host Docker daemon.

## Run

```bash
docker compose up -d
```

After code or Dockerfile changes, rebuild:

```bash
docker compose up -d --build
```

Open:

```text
http://localhost:8000
```

If generated bundle files appear as root-owned or hard to delete from your SSH
user, set the output owner before starting Compose:

```bash
export REPOFORGE_OUTPUT_UID=$(id -u)
export REPOFORGE_OUTPUT_GID=$(id -g)
docker compose up -d --build
```

## Web UI Usage

1. Select the target operating system.
2. Select the CPU architecture.
3. Enter package names, comma separated.
4. Optionally select supported extra repositories.
5. Click `Build Bundle`.
6. Watch job status and logs.
7. Download the bundle when the job is completed.

Examples:

```text
curl
realmd, sssd
nginx
docker-ce, docker-ce-cli, containerd.io
```

## CLI Usage

If you do not need the web UI, use the same container as a one-shot bundle
builder.

Ubuntu shortcut:

```bash
docker compose run --rm repoforge \
  python -m app.cli --ubuntu 22.04 curl
```

Direct distro ID:

```bash
docker compose run --rm repoforge \
  python -m app.cli --distro debian-12 curl
```

RHEL-family example:

```bash
docker compose run --rm repoforge \
  python -m app.cli --distro rocky-9 realmd sssd adcli
```

The final archive is written under:

```text
./bundles
```

Temporary job work is stored under:

```text
./workdir
```

## Active Directory Join Bundles

RepoForge includes package presets in the UI for joining Linux servers to
Microsoft Active Directory.

Ubuntu/Debian preset packages:

- `realmd`
- `sssd`
- `sssd-tools`
- `libnss-sss`
- `libpam-sss`
- `adcli`
- `krb5-user`
- `samba-common-bin`
- `packagekit`
- `chrony`
- `dnsutils`
- `ldap-utils`
- `ca-certificates`

Rocky Linux / AlmaLinux preset packages:

- `realmd`
- `sssd`
- `sssd-tools`
- `adcli`
- `krb5-workstation`
- `samba-common-tools`
- `oddjob`
- `oddjob-mkhomedir`
- `chrony`
- `bind-utils`
- `openldap-clients`

## Install on the Air-Gapped Server

Copy and extract the downloaded archive on the target server:

```bash
tar -xzf repoforge-bundle-*.tar.gz
cd bundle
chmod +x install.sh
./install.sh
```

For Debian-family bundles, the installer runs:

```bash
sudo dpkg -i packages/*.deb || sudo apt-get install -f -y
```

For RHEL-family bundles, the installer runs one of:

```bash
sudo dnf install -y packages/*.rpm
sudo yum install -y packages/*.rpm
sudo rpm -Uvh packages/*.rpm
```

Debian-family bundles can also create a local mini APT repository:

```bash
./install.sh --make-repo
echo "deb [trusted=yes] file:$(pwd)/packages ./" | sudo tee /etc/apt/sources.list.d/repoforge-local.list
sudo apt-get update
sudo apt-get install realmd sssd
```

`--make-repo` requires `dpkg-scanpackages`, usually provided by `dpkg-dev`.

## Extra Repositories

RepoForge can add selected third-party repositories inside the temporary resolver
container before dependency resolution.

Currently configured options:

- Docker CE
- Kubernetes
- Rancher RKE2 for RHEL-family targets

These are optional and are selected from the UI. The backend validates requested
extra repositories against an allowlist.

## API

### `GET /api/health`

Returns application liveness:

```json
{
  "status": "ok",
  "application": "RepoForge",
  "version": "0.3.0"
}
```

### `GET /api/system`

Returns operational readiness details such as Docker CLI availability, Docker
server availability, output paths, and configured output UID/GID.

### `GET /api/distros`

Returns supported Linux distributions.

### `GET /api/extra-repos`

Returns supported optional repositories.

### `GET /api/package-options`

Returns customer-facing package presets for common scenarios such as AD join,
container runtime, web servers, SSH, and operations baseline tools.

### `POST /api/jobs`

Request:

```json
{
  "distro_id": "ubuntu-22.04",
  "architecture": "amd64",
  "packages": ["realmd", "sssd"],
  "extra_repos": []
}
```

RHEL-family example:

```json
{
  "distro_id": "rocky-9",
  "architecture": "amd64",
  "packages": ["realmd", "sssd", "adcli"],
  "extra_repos": []
}
```

Response includes a UUID job ID, status, logs, and bundle metadata when complete.

### `GET /api/jobs`

Returns recent jobs from the current application process.

### `GET /api/jobs/{job_id}`

Returns job status and logs.

### `GET /api/jobs/{job_id}/download`

Downloads the generated `tar.gz` bundle after the job is completed.

## Resolver Behavior

For each build, the backend runs a fresh temporary Docker container using the
matching target image.

Debian-family targets:

1. Configure deterministic APT repositories for the target release.
2. Run `apt-get update`.
3. Install resolver helpers, including `apt-rdepends`.
4. Validate requested packages with `apt-cache show`.
5. Run `apt-get install --download-only -y --reinstall <packages>`.
6. Recursively resolve dependencies with `apt-rdepends`.
7. Run `apt-get download` for the resolved package set.
8. Copy downloaded `.deb` files into the bundle.

RHEL-family targets:

1. Use the image's configured DNF repositories.
2. Optionally add supported third-party repositories.
3. Install `dnf-plugins-core`.
4. Validate requested packages with `dnf info`.
5. Run `dnf download --resolve`.
6. Copy downloaded `.rpm` files into the bundle.

This avoids mirroring a full repository and downloads only the requested packages
and their dependency closure.

Resolver containers are named `repoforge-resolver-<job_id>` and labeled with the
job ID so operators can inspect them while a build is running:

```bash
docker ps --filter label=com.repoforge.role=resolver
```

The container is started with `--rm`, so it is removed automatically after the
resolver exits.

## Security Notes

- Package names are validated with a strict allowlist: letters, numbers, plus,
  minus, and dot.
- Distribution IDs, architectures, and extra repositories are allowlisted.
- Job IDs are UUIDs.
- Downloads are served only from the configured `./bundles` directory.
- Host subprocess calls use argument arrays and never use `shell=True`.

## Production Notes

- The app exposes `/api/health` and the image includes a Docker healthcheck.
- API responses include basic hardening headers such as `X-Frame-Options` and
  `X-Content-Type-Options`.
- Job logs are bounded in memory to avoid unbounded growth during large package
  builds.
- Job history is in memory for this MVP. Restarting the app clears job status,
  while generated archives remain under `./bundles`.
- Docker socket access is powerful. Run RepoForge only on trusted hosts and
  restrict access to the web UI.

## Troubleshooting

### Permission denied on generated bundles or workdir

The resolver containers run as root because package managers need root inside
the temporary container. RepoForge normalizes generated file permissions and can
chown outputs back to your host SSH user.

Use:

```bash
export REPOFORGE_OUTPUT_UID=$(id -u)
export REPOFORGE_OUTPUT_GID=$(id -g)
docker compose up -d --build
```

New bundles should then be owned by your SSH user/group and readable from the
host.

### `Docker CLI not found`

Run the app with the provided Dockerfile and rebuild the image:

```bash
docker compose up -d --build
```

If you run the FastAPI app directly on the host instead of through Compose,
install Docker on the host and make sure `docker` is in `PATH`, or set:

```bash
export REPOFORGE_DOCKER_BIN=/path/to/docker
```

### Build works in UI but not from host Python

The supported deployment path is Docker Compose. Direct host execution requires
Python dependencies from `requirements.txt` and a working Docker CLI.
