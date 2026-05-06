import os
from pathlib import Path


DISTRO_CATALOG: dict[str, dict] = {
    "ubuntu-20.04": {
        "label": "Ubuntu 20.04 LTS",
        "family": "debian",
        "docker_image": "ubuntu:20.04",
        "codename": "focal",
        "pkg_ext": "deb",
        "components": ("main", "restricted", "universe", "multiverse"),
        "suites": ("focal", "focal-updates", "focal-security"),
        "archive_host": "archive.ubuntu.com/ubuntu",
        "security_host": "security.ubuntu.com/ubuntu",
    },
    "ubuntu-22.04": {
        "label": "Ubuntu 22.04 LTS",
        "family": "debian",
        "docker_image": "ubuntu:22.04",
        "codename": "jammy",
        "pkg_ext": "deb",
        "components": ("main", "restricted", "universe", "multiverse"),
        "suites": ("jammy", "jammy-updates", "jammy-security"),
        "archive_host": "archive.ubuntu.com/ubuntu",
        "security_host": "security.ubuntu.com/ubuntu",
    },
    "ubuntu-24.04": {
        "label": "Ubuntu 24.04 LTS",
        "family": "debian",
        "docker_image": "ubuntu:24.04",
        "codename": "noble",
        "pkg_ext": "deb",
        "components": ("main", "restricted", "universe", "multiverse"),
        "suites": ("noble", "noble-updates", "noble-security"),
        "archive_host": "archive.ubuntu.com/ubuntu",
        "security_host": "security.ubuntu.com/ubuntu",
    },
    "debian-11": {
        "label": "Debian 11 (Bullseye)",
        "family": "debian",
        "docker_image": "debian:11",
        "codename": "bullseye",
        "pkg_ext": "deb",
        "components": ("main", "contrib", "non-free"),
        "suites": ("bullseye", "bullseye-updates", "bullseye-security"),
        "archive_host": "deb.debian.org/debian",
        "security_host": "security.debian.org/debian-security",
    },
    "debian-12": {
        "label": "Debian 12 (Bookworm)",
        "family": "debian",
        "docker_image": "debian:12",
        "codename": "bookworm",
        "pkg_ext": "deb",
        "components": ("main", "contrib", "non-free", "non-free-firmware"),
        "suites": ("bookworm", "bookworm-updates", "bookworm-security"),
        "archive_host": "deb.debian.org/debian",
        "security_host": "security.debian.org/debian-security",
    },
    "rocky-8": {
        "label": "Rocky Linux 8",
        "family": "rhel",
        "docker_image": "rockylinux:8",
        "codename": "Green Obsidian",
        "pkg_ext": "rpm",
        "version": "8",
    },
    "rocky-9": {
        "label": "Rocky Linux 9",
        "family": "rhel",
        "docker_image": "rockylinux:9",
        "codename": "Blue Onyx",
        "pkg_ext": "rpm",
        "version": "9",
    },
    "almalinux-8": {
        "label": "AlmaLinux 8",
        "family": "rhel",
        "docker_image": "almalinux:8",
        "codename": "Sky Tiger",
        "pkg_ext": "rpm",
        "version": "8",
    },
    "almalinux-9": {
        "label": "AlmaLinux 9",
        "family": "rhel",
        "docker_image": "almalinux:9",
        "codename": "Seafoam Ocelot",
        "pkg_ext": "rpm",
        "version": "9",
    },
    "opensuse-leap-15.5": {
        "label": "openSUSE Leap 15.5",
        "family": "suse",
        "docker_image": "opensuse/leap:15.5",
        "codename": "Piko",
        "pkg_ext": "rpm",
        "version": "15.5",
    },
    "opensuse-leap-15.6": {
        "label": "openSUSE Leap 15.6",
        "family": "suse",
        "docker_image": "opensuse/leap:15.6",
        "codename": "Kalimba",
        "pkg_ext": "rpm",
        "version": "15.6",
    },
}

SUPPORTED_DISTRO_IDS = tuple(DISTRO_CATALOG.keys())
SUPPORTED_ARCHITECTURES = ("amd64", "arm64")

BASE_DIR = Path(__file__).resolve().parent.parent
BUNDLES_DIR = BASE_DIR / "bundles"
WORKDIR = BASE_DIR / "workdir"
STATIC_DIR = BASE_DIR / "static"
HOST_WORKDIR = Path(
    os.environ.get("REPOFORGE_HOST_WORKDIR")
    or os.environ.get("AIRGAP_HOST_WORKDIR")
    or str(WORKDIR)
).resolve()
DOCKER_BIN = os.environ.get("REPOFORGE_DOCKER_BIN") or os.environ.get("AIRGAP_DOCKER_BIN") or "docker"
OUTPUT_UID_RAW = os.environ.get("REPOFORGE_OUTPUT_UID") or os.environ.get("AIRGAP_OUTPUT_UID")
OUTPUT_GID_RAW = os.environ.get("REPOFORGE_OUTPUT_GID") or os.environ.get("AIRGAP_OUTPUT_GID")
OUTPUT_UID = int(OUTPUT_UID_RAW) if OUTPUT_UID_RAW else None
OUTPUT_GID = int(OUTPUT_GID_RAW) if OUTPUT_GID_RAW else None

DOCKER_TIMEOUT_SECONDS = 60 * 60

K8S_VERSIONS  = ("1.28", "1.29", "1.30", "1.31", "1.32")
RKE2_VERSIONS = ("1.28", "1.29", "1.30", "1.31", "1.32")

EXTRA_REPOS: dict[str, dict] = {
    "docker-ce": {
        "label": "Docker CE",
        "description": "Official Docker Engine, CLI, containerd, buildx, and compose plugin.",
        "families": ["debian", "rhel"],
        "versioned": False,
        "default_packages": [
            "docker-ce", "docker-ce-cli", "containerd.io",
            "docker-buildx-plugin", "docker-compose-plugin",
        ],
    },
    "kubernetes": {
        "label": "Kubernetes",
        "description": "kubeadm, kubelet, and kubectl from the official Kubernetes repository (pkgs.k8s.io).",
        "families": ["debian", "rhel"],
        "versioned": True,
        "versions": K8S_VERSIONS,
        "default_version": "1.32",
        "default_packages": ["kubeadm", "kubelet", "kubectl"],
    },
    "rancher-rke2": {
        "label": "Rancher RKE2",
        "description": "Rancher Kubernetes Engine 2 — packages from rancher.io for RHEL and Debian/Ubuntu.",
        "families": ["debian", "rhel"],
        "versioned": True,
        "versions": RKE2_VERSIONS,
        "default_version": "1.32",
        "default_packages": ["rke2-server"],
    },
}

PACKAGE_OPTIONS = [
    {
        "id": "identity-ad",
        "title": "Active Directory Join",
        "description": "Join an Ubuntu/Debian machine to Microsoft Active Directory via Kerberos and SSSD.",
        "distro_families": ["debian"],
        "packages": (
            "realmd", "sssd", "sssd-tools", "libnss-sss", "libpam-sss",
            "adcli", "krb5-user", "samba-common-bin", "packagekit",
            "chrony", "dnsutils", "ldap-utils", "ca-certificates",
        ),
    },
    {
        "id": "identity-ad-rhel",
        "title": "Active Directory Join",
        "description": "Join a Rocky Linux / AlmaLinux machine to Microsoft Active Directory.",
        "distro_families": ["rhel"],
        "packages": (
            "realmd", "sssd", "sssd-tools", "adcli", "krb5-workstation",
            "samba-common-tools", "oddjob", "oddjob-mkhomedir",
            "chrony", "bind-utils", "openldap-clients",
        ),
    },
    {
        "id": "web-nginx",
        "title": "Nginx Web Server",
        "description": "Serve HTTP/S traffic with Nginx.",
        "distro_families": ["debian", "rhel"],
        "packages": ("nginx",),
    },
    {
        "id": "web-apache-deb",
        "title": "Apache Web Server",
        "description": "Apache HTTP server and common utilities for Debian/Ubuntu.",
        "distro_families": ["debian"],
        "packages": ("apache2",),
    },
    {
        "id": "web-apache-rhel",
        "title": "Apache (httpd)",
        "description": "Apache HTTP server and SSL module for RHEL-family.",
        "distro_families": ["rhel"],
        "packages": ("httpd", "mod_ssl"),
    },
    {
        "id": "ops-baseline",
        "title": "Operations Baseline",
        "description": "Common admin tools: curl, wget, vim, net-tools, ca-certificates.",
        "distro_families": ["debian", "rhel"],
        "packages": ("curl", "wget", "vim", "net-tools", "ca-certificates"),
    },
    {
        "id": "ssh-tools",
        "title": "SSH and File Transfer",
        "description": "OpenSSH server/client and rsync for remote administration.",
        "distro_families": ["debian", "rhel"],
        "packages": ("openssh-server", "openssh-client", "rsync"),
    },
    {
        "id": "monitoring",
        "title": "Monitoring Agents",
        "description": "Prometheus node exporter and sysstat for host-level metrics.",
        "distro_families": ["debian", "rhel"],
        "packages": ("prometheus-node-exporter", "sysstat", "lsof", "strace"),
    },
    {
        "id": "ops-baseline-suse",
        "title": "Operations Baseline",
        "description": "Common admin tools: curl, wget, vim, net-tools, ca-certificates.",
        "distro_families": ["suse"],
        "packages": ("curl", "wget", "vim", "net-tools", "ca-certificates"),
    },
    {
        "id": "ssh-tools-suse",
        "title": "SSH and File Transfer",
        "description": "OpenSSH server/client and rsync for remote administration.",
        "distro_families": ["suse"],
        "packages": ("openssh", "rsync"),
    },
    {
        "id": "web-nginx-suse",
        "title": "Nginx Web Server",
        "description": "Serve HTTP/S traffic with Nginx.",
        "distro_families": ["suse"],
        "packages": ("nginx",),
    },
    {
        "id": "web-apache-suse",
        "title": "Apache Web Server",
        "description": "Apache HTTP server and SSL module for openSUSE.",
        "distro_families": ["suse"],
        "packages": ("apache2", "apache2-mod_ssl"),
    },
    {
        "id": "identity-ad-suse",
        "title": "Active Directory Join",
        "description": "Join an openSUSE machine to Microsoft Active Directory.",
        "distro_families": ["suse"],
        "packages": (
            "realmd", "sssd", "sssd-tools", "adcli", "krb5-client",
            "samba-client", "chrony",
        ),
    },
]
