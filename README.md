# RepoForge

RepoForge is a FastAPI web application that creates offline
`.deb` bundles for air-gapped Ubuntu servers. It resolves packages inside
temporary Docker containers that match the requested Ubuntu version, downloads
only the requested packages and dependencies, and produces a downloadable
`tar.gz` bundle.

Author: Lidor Eliya

## Supported Targets

- Ubuntu 20.04 `focal`
- Ubuntu 22.04 `jammy`
- Ubuntu 24.04 `noble`
- Architecture: `amd64`

For each Ubuntu version, the app configures the resolver container with the
standard Ubuntu suites for that release:

- Base release, for example `jammy`
- Updates, for example `jammy-updates`
- Security, for example `jammy-security`

Each suite uses `main restricted universe multiverse`.

## What a Bundle Contains

Each generated archive contains:

- `packages/*.deb`
- `install.sh`
- `README.md`
- `manifest.json`
- `checksums.sha256`

## Requirements

- Docker Engine
- Docker Compose plugin
- Internet access from the host for pulling images & downloading packages

The compose setup mounts `/var/run/docker.sock` so the web app can start temporary
resolver containers such as `ubuntu:22.04`. It also passes `REPOFORGE_HOST_WORKDIR`
so those resolver containers can mount the host `workdir` path correctly.

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

If generated bundle files appear as root-owned or hard to delete from your SSH
user, set the output owner before starting Compose:

```bash
export REPOFORGE_OUTPUT_UID=$(id -u)
export REPOFORGE_OUTPUT_GID=$(id -g)
docker compose up -d --build
```

Open:

```text
http://localhost:8000
```

## Simple CLI Usage

If you do not need the web UI, use the same container as a one-shot package
bundle command.

Example: download `curl` and its dependencies for Ubuntu 22.04:

```bash
docker compose run --rm repoforge \
  python -m app.cli --ubuntu 22.04 curl
```

Example: download `realmd` and `sssd` for Ubuntu 22.04:

```bash
docker compose run --rm repoforge \
  python -m app.cli --ubuntu 22.04 realmd sssd
```

Recommended full Active Directory join bundle for a fresh Ubuntu 22.04 VM:

```bash
docker compose run --rm repoforge \
  python -m app.cli --ubuntu 22.04 \
  realmd sssd sssd-tools libnss-sss libpam-sss adcli krb5-user \
  samba-common-bin packagekit chrony dnsutils ldap-utils ca-certificates
```

In the web UI, press **Active Directory Join - Full VM Bundle** to fill this
package list automatically.

The final archive is written under:

```text
./bundles
```

The command still uses a fresh temporary `ubuntu:<version>` resolver container,
real APT repositories, and real APT dependency resolution.

Generated bundles are stored under:

```text
./bundles
```

Temporary job work is stored under:

```text
./workdir
```

## Example: realmd + sssd for Ubuntu 22.04

In the UI:

1. Select `Ubuntu 22.04`.
2. Keep architecture as `amd64`.
3. Enter package names:

```text
realmd, sssd
```

4. Click `Start build`.
5. Wait for the status to become `completed`.
6. Click `Download bundle`.

## Active Directory Join Bundle

For a fresh Ubuntu VM that needs to join Microsoft Active Directory, use the
**Active Directory Join - Full VM Bundle** option. It includes:

- `realmd`: domain discovery and join workflow.
- `sssd`, `sssd-tools`: identity, authentication, and diagnostics.
- `libnss-sss`, `libpam-sss`: NSS/PAM integration for AD users.
- `adcli`: Active Directory computer account join.
- `krb5-user`: Kerberos client tooling.
- `samba-common-bin`: AD/Samba helper utilities.
- `packagekit`: helps `realmd` workflows detect required components.
- `chrony`: time synchronization, important for Kerberos.
- `dnsutils`, `ldap-utils`: DNS and LDAP diagnostics.
- `ca-certificates`: trusted CA baseline.

After installing the offline bundle on the target VM, verify prerequisites:

```bash
timedatectl
resolvectl status
realm discover example.local
```

Then join:

```bash
sudo realm join example.local -U Administrator
realm list
id user@example.local
```

For automatic home directory creation on first login:

```bash
sudo pam-auth-update --enable mkhomedir
```

The same job can be created through the API:

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H 'Content-Type: application/json' \
  -d '{"distro_id":"ubuntu-22.04","architecture":"amd64","packages":["realmd","sssd"]}'
```

Poll the returned UUID:

```bash
curl http://localhost:8000/api/jobs/<job_id>
```

Download when complete:

```bash
curl -L -o repoforge-bundle.tar.gz http://localhost:8000/api/jobs/<job_id>/download
```

## Install on the Air-Gapped Server

Copy the extracted bundle directory to the target server.

Direct install:

```bash
chmod +x install.sh
./install.sh
```

This runs:

```bash
sudo dpkg -i packages/*.deb || sudo apt-get install -f -y
```

Optional local mini APT repository:

```bash
./install.sh --make-repo
echo "deb [trusted=yes] file:$(pwd)/packages ./" | sudo tee /etc/apt/sources.list.d/repoforge-local.list
sudo apt-get update
sudo apt-get install realmd sssd
```

`--make-repo` requires `dpkg-scanpackages`, usually provided by `dpkg-dev`.

## API

### `GET /api/health`

Returns application liveness:

```json
{
  "status": "ok",
  "application": "RepoForge",
  "version": "0.2.0"
}
```

### `GET /api/system`

Returns operational readiness details such as Docker CLI availability, Docker
server availability, output paths, and configured output UID/GID.

### `GET /api/distros`

Returns supported Linux distributions and the repository catalog used by the resolver.

### `GET /api/package-options`

Returns customer-facing package presets for common scenarios such as AD join,
container runtime, web servers, SSH, and operations baseline tools.

### `POST /api/jobs`

Request:

```json
{
  "distro_id": "ubuntu-22.04",
  "architecture": "amd64",
  "packages": ["realmd", "sssd"]
}
```

Response includes a UUID job ID, status, logs, and bundle metadata when complete.

### `GET /api/jobs/{job_id}`

Returns job status and logs.

### `GET /api/jobs`

Returns recent jobs from the current application process.

### `GET /api/jobs/{job_id}/download`

Downloads the generated `tar.gz` bundle after the job is completed.

## Security Notes

- Package names are validated with a strict allowlist: letters, numbers, plus,
  minus, and dot.
- Ubuntu versions and architectures are allowlisted.
- Job IDs are UUIDs.
- Downloads are served only from the configured `./bundles` directory.
- Host subprocess calls use argument arrays and never use `shell=True`.

## Resolver Behavior

For each build, the backend runs a temporary container using the matching Ubuntu
image, for example `ubuntu:22.04`. Inside that resolver container it:

1. Enables standard Ubuntu components: `main restricted universe multiverse`.
2. Writes deterministic APT source lines for the selected Ubuntu codename,
   including release, updates, and security suites.
3. Runs `apt-get update`.
4. Installs resolver helpers including `apt-rdepends`.
5. Validates that each requested package exists with `apt-cache show`.
6. Logs the selected package candidate with `apt-cache policy`.
7. Runs `apt-get install --download-only -y --reinstall <packages>`.
8. Recursively resolves dependencies with `apt-rdepends`.
9. Runs `apt-get download` for the resolved package set.
10. Copies downloaded `.deb` files into the mounted output directory.

This avoids mirroring a full Ubuntu repository and downloads only the requested
packages and their dependency closure.

Resolver containers are named `repoforge-resolver-<job_id>` and labeled with the
job ID so operators can inspect them while a build is running:

```bash
docker ps --filter label=com.repoforge.role=resolver
```

The container is started with `--rm`, so it is removed automatically after the
resolver exits.

## Production Notes

- The app exposes `/api/health` and the image includes a Docker healthcheck.
- API responses include basic hardening headers such as `X-Frame-Options` and
  `X-Content-Type-Options`.
- Job logs are bounded in memory to avoid unbounded growth during large package
  builds.
- Job history is in memory for this MVP. Restarting the app clears job status,
  while generated archives remain under `./bundles`.

## Troubleshooting

### Permission denied on generated bundles or workdir

The resolver containers run as root because APT needs root inside Ubuntu. The app
normalizes generated file permissions and can chown outputs back to your host SSH
user.

Use:

```bash
export REPOFORGE_OUTPUT_UID=$(id -u)
export REPOFORGE_OUTPUT_GID=$(id -g)
docker compose up -d --build
```

New bundles should then be owned by your SSH user/group and readable from the host.

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
