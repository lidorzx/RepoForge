const jobForm = document.getElementById("jobForm");
const packagesInput = document.getElementById("packages");
const buildBtn = document.getElementById("buildBtn");
const downloadLink = document.getElementById("downloadLink");
const dockerDot = document.getElementById("dockerDot");
const dockerLabel = document.getElementById("dockerLabel");
const buildBadge = document.getElementById("buildBadge");
const badgeText = document.getElementById("badgeText");
const osFamilies = document.getElementById("osFamilies");
const extraRepoList = document.getElementById("extraRepoList");
const presetGrid = document.getElementById("presetGrid");
const distroMeta = document.getElementById("distroMeta");
const jobStatus = document.getElementById("jobStatus");
const jobDistro = document.getElementById("jobDistro");
const jobPackages = document.getElementById("jobPackages");
const bundleSize = document.getElementById("bundleSize");
const logBody = document.getElementById("logs");
const logJobId = document.getElementById("logJobId");
const jobHistory = document.getElementById("jobHistory");

let pollTimer = null;
let distroCatalog = {};
let allOptions = [];
let extraRepoCatalog = {};
let selectedDistroId = "ubuntu-22.04";
const enabledRepos = new Map();

const FAMILY_META = {
  debian: { label: "Debian / Ubuntu" },
  rhel: { label: "RHEL Family" },
};

const STATUS_CLASS = {
  queued: "status-queued",
  running: "status-running",
  completed: "status-done",
  failed: "status-failed",
};

function parsePackages(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function addPackages(packages) {
  const merged = [...new Set([...parsePackages(packagesInput.value), ...packages])];
  packagesInput.value = merged.join(", ");
}

function formatBytes(bytes) {
  if (!bytes) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function setBadge(text, state) {
  badgeText.textContent = text;
  buildBadge.className = `build-badge ${state || ""}`.trim();
}

function osDisplayParts(distro) {
  if (distro.id.startsWith("ubuntu-")) {
    return { name: "Ubuntu", detail: distro.label.replace("Ubuntu ", "") };
  }
  if (distro.id.startsWith("debian-")) {
    return { name: "Debian", detail: distro.label.replace("Debian ", "") };
  }
  if (distro.id.startsWith("rocky-")) {
    return { name: "Rocky Linux", detail: distro.label.replace("Rocky Linux ", "") };
  }
  if (distro.id.startsWith("almalinux-")) {
    return { name: "AlmaLinux", detail: distro.label.replace("AlmaLinux ", "") };
  }
  return { name: distro.label, detail: distro.id };
}

function renderOsGrid(catalog) {
  distroCatalog = catalog;
  if (!distroCatalog[selectedDistroId]) {
    selectedDistroId = Object.keys(distroCatalog)[0] || selectedDistroId;
  }

  const groups = {};
  for (const [id, info] of Object.entries(catalog)) {
    const family = info.family || "other";
    if (!groups[family]) groups[family] = [];
    groups[family].push({ id, ...info });
  }

  osFamilies.replaceChildren();
  for (const [family, distros] of Object.entries(groups)) {
    const section = document.createElement("div");
    section.className = "os-family";

    const heading = document.createElement("div");
    heading.className = "os-family-label";
    heading.textContent = (FAMILY_META[family] || { label: family }).label;
    section.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "os-card-grid";

    for (const distro of distros) {
      const label = document.createElement("label");
      label.className = `os-card ${distro.id === selectedDistroId ? "selected" : ""}`.trim();
      label.dataset.distroId = distro.id;

      const input = document.createElement("input");
      input.type = "radio";
      input.name = "distro";
      input.value = distro.id;
      input.checked = distro.id === selectedDistroId;

      const inner = document.createElement("span");
      inner.className = "os-card-inner";

      const parts = osDisplayParts(distro);
      const name = document.createElement("span");
      name.className = "os-name";
      name.textContent = parts.name;

      const detail = document.createElement("span");
      detail.className = "os-detail";
      detail.textContent = parts.detail;

      const badge = document.createElement("span");
      badge.className = `pkg-badge ${distro.pkg_ext === "rpm" ? "rpm" : "deb"}`;
      badge.textContent = distro.pkg_ext === "rpm" ? "RPM" : "DEB";

      inner.append(name, detail, badge);
      label.append(input, inner);
      label.addEventListener("click", () => selectDistro(distro.id));
      grid.appendChild(label);
    }

    section.appendChild(grid);
    osFamilies.appendChild(section);
  }

  updateDistroMeta();
  filterPresets();
  renderExtraRepos();
}

function selectDistro(distroId) {
  selectedDistroId = distroId;
  document.querySelectorAll(".os-card").forEach((card) => {
    card.classList.toggle("selected", card.dataset.distroId === distroId);
  });
  updateDistroMeta();
  filterPresets();
  renderExtraRepos();
}

function updateDistroMeta() {
  if (!distroMeta) return;
  const info = distroCatalog[selectedDistroId];
  if (!info) {
    distroMeta.replaceChildren();
    return;
  }

  const rows = info.family === "debian" && info.suites
    ? [
        ["Codename", info.codename || "-"],
        ["Suites", info.suites.join(", ")],
      ]
    : [
        ["Codename", info.codename || "-"],
        ["Package manager", "dnf / rpm"],
      ];

  distroMeta.replaceChildren();
  for (const [key, value] of rows) {
    const keyEl = document.createElement("span");
    keyEl.className = "meta-key";
    keyEl.textContent = key;
    const valueEl = document.createElement("span");
    valueEl.className = "meta-val";
    valueEl.textContent = value;
    distroMeta.append(keyEl, valueEl);
  }
}

function renderExtraRepos() {
  const info = distroCatalog[selectedDistroId];
  const family = info ? info.family : null;
  extraRepoList.replaceChildren();

  let visibleCount = 0;
  for (const [repoId, repo] of Object.entries(extraRepoCatalog)) {
    if (family && !repo.families.includes(family)) continue;
    visibleCount += 1;

    const isEnabled = enabledRepos.has(repoId);
    const currentVersion = enabledRepos.get(repoId) || repo.default_version;
    const row = document.createElement("div");
    row.className = `repo-row ${isEnabled ? "enabled" : ""}`.trim();
    row.dataset.repoId = repoId;

    const toggleLabel = document.createElement("label");
    toggleLabel.className = "repo-toggle-label";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "repo-checkbox";
    checkbox.dataset.repoId = repoId;
    checkbox.checked = isEnabled;
    const slider = document.createElement("span");
    slider.className = "repo-toggle-slider";
    toggleLabel.append(checkbox, slider);

    const infoBox = document.createElement("div");
    infoBox.className = "repo-info";
    const name = document.createElement("span");
    name.className = "repo-name";
    name.textContent = repo.label;
    const desc = document.createElement("span");
    desc.className = "repo-desc";
    desc.textContent = repo.description;
    infoBox.append(name, desc);

    row.append(toggleLabel, infoBox);

    let versionSelect = null;
    if (repo.versioned) {
      versionSelect = document.createElement("select");
      versionSelect.className = "repo-version-select";
      versionSelect.dataset.repoId = repoId;
      versionSelect.disabled = !isEnabled;
      for (const version of repo.versions) {
        const option = document.createElement("option");
        option.value = version;
        option.textContent = version;
        option.selected = version === currentVersion;
        versionSelect.appendChild(option);
      }
      versionSelect.addEventListener("change", () => {
        if (enabledRepos.has(repoId)) enabledRepos.set(repoId, versionSelect.value);
      });
      row.appendChild(versionSelect);
    }

    checkbox.addEventListener("change", () => toggleRepo(repoId, checkbox.checked, row));
    extraRepoList.appendChild(row);
  }

  if (!visibleCount) {
    const empty = document.createElement("p");
    empty.className = "no-presets";
    empty.textContent = "No extra repositories available for this OS family.";
    extraRepoList.appendChild(empty);
  }
}

function toggleRepo(repoId, enabled, row) {
  const repo = extraRepoCatalog[repoId];
  const versionSelect = row.querySelector(".repo-version-select");

  if (enabled) {
    enabledRepos.set(repoId, versionSelect ? versionSelect.value : null);
    row.classList.add("enabled");
    if (versionSelect) versionSelect.disabled = false;
    if (repo.default_packages?.length) addPackages(repo.default_packages);
  } else {
    enabledRepos.delete(repoId);
    row.classList.remove("enabled");
    if (versionSelect) versionSelect.disabled = true;
  }
}

function buildExtraReposPayload() {
  return [...enabledRepos.entries()].map(([repoId, version]) => (
    version ? `${repoId}:${version}` : repoId
  ));
}

function renderPresets(options) {
  allOptions = options;
  filterPresets();
}

function filterPresets() {
  const info = distroCatalog[selectedDistroId];
  const family = info ? info.family : null;
  const visible = family
    ? allOptions.filter((option) => option.distro_families.includes(family))
    : allOptions;

  presetGrid.replaceChildren();
  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "no-presets";
    empty.textContent = "No presets for this OS.";
    presetGrid.appendChild(empty);
    return;
  }

  for (const option of visible) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "preset-card";

    const title = document.createElement("strong");
    title.textContent = option.title;
    const desc = document.createElement("span");
    desc.textContent = option.description;
    const chips = document.createElement("div");
    chips.className = "chip-row";
    for (const pkg of option.packages) {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = pkg;
      chips.appendChild(chip);
    }

    card.append(title, desc, chips);
    card.addEventListener("click", () => addPackages(option.packages));
    presetGrid.appendChild(card);
  }
}

function renderJob(job) {
  const statusClass = STATUS_CLASS[job.status] || "";
  jobStatus.textContent = job.status;
  jobStatus.className = `stat-value status-badge ${statusClass}`.trim();

  const distroInfo = distroCatalog[job.distro_id];
  jobDistro.textContent = distroInfo ? distroInfo.label : job.distro_id;
  jobPackages.textContent = job.packages.join(", ") || "-";
  bundleSize.textContent = formatBytes(job.bundle_size_bytes);
  logJobId.textContent = job.job_id;
  logBody.textContent = job.logs.length ? job.logs.join("\n") : "Waiting for logs...";
  logBody.scrollTop = logBody.scrollHeight;

  if (job.status === "completed") {
    downloadLink.href = `/api/jobs/${job.job_id}/download`;
    downloadLink.classList.remove("hidden");
    buildBtn.disabled = false;
    setBadge("Completed", "done");
  } else if (job.status === "failed") {
    downloadLink.classList.add("hidden");
    buildBtn.disabled = false;
    setBadge("Failed", "failed");
  } else {
    downloadLink.classList.add("hidden");
    buildBtn.disabled = true;
    setBadge(job.status === "running" ? "Building..." : "Queued", "running");
  }
}

async function loadSystemStatus() {
  const response = await fetch("/api/system");
  if (!response.ok) return;
  const system = await response.json();
  const ok = system.docker_cli_available && system.docker_server_available;
  dockerDot.className = `indicator-dot ${ok ? "dot-ok" : "dot-err"}`;
  dockerLabel.textContent = ok ? `Docker ${system.docker_version || ""}`.trim() : "Docker unavailable";
}

async function loadJobHistory() {
  const response = await fetch("/api/jobs");
  if (!response.ok) return;
  const { jobs } = await response.json();
  if (!jobs.length) {
    jobHistory.innerHTML = `<div class="history-empty">No jobs yet.</div>`;
    return;
  }

  jobHistory.replaceChildren();
  for (const job of jobs.slice(0, 10)) {
    const distroInfo = distroCatalog[job.distro_id];
    const distroLabel = distroInfo ? distroInfo.label : job.distro_id;
    const row = document.createElement("div");
    row.className = "history-row";

    const status = document.createElement("span");
    status.className = `status-badge ${STATUS_CLASS[job.status] || ""}`.trim();
    status.textContent = job.status;

    const id = document.createElement("code");
    id.className = "history-id";
    id.textContent = `${job.job_id.slice(0, 8)}...`;

    const distro = document.createElement("span");
    distro.className = "history-distro";
    distro.textContent = `${distroLabel} / ${job.architecture}`;

    const packages = document.createElement("span");
    packages.className = "history-pkgs";
    packages.textContent = job.packages.join(", ");

    const size = document.createElement("span");
    size.className = "history-size";
    size.textContent = formatBytes(job.bundle_size_bytes);

    row.append(status, id, distro, packages, size);
    if (job.status === "completed") {
      const download = document.createElement("a");
      download.href = `/api/jobs/${job.job_id}/download`;
      download.className = "history-dl";
      download.textContent = "DL";
      download.title = "Download";
      row.appendChild(download);
    }
    jobHistory.appendChild(row);
  }
}

async function pollJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`);
  if (!response.ok) throw new Error("Unable to fetch job status.");
  const job = await response.json();
  renderJob(job);
  if (job.status === "completed" || job.status === "failed") {
    clearInterval(pollTimer);
    pollTimer = null;
    loadJobHistory().catch(() => {});
  }
}

jobForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const packages = parsePackages(packagesInput.value);
  if (!packages.length) {
    logBody.textContent = "Enter at least one package name.";
    return;
  }

  const archEl = document.querySelector('input[name="arch"]:checked');
  const architecture = archEl ? archEl.value : "amd64";
  const extra_repos = buildExtraReposPayload();

  buildBtn.disabled = true;
  downloadLink.classList.add("hidden");
  setBadge("Submitting...", "running");
  logBody.textContent = "Submitting job...";

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ distro_id: selectedDistroId, architecture, packages, extra_repos }),
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail ? JSON.stringify(detail.detail) : "Job submission failed.");
    }

    const job = await response.json();
    renderJob(job);
    clearInterval(pollTimer);
    loadJobHistory().catch(() => {});
    pollTimer = setInterval(() => pollJob(job.job_id).catch(showError), 2500);
  } catch (error) {
    showError(error);
  }
});

function showError(error) {
  clearInterval(pollTimer);
  pollTimer = null;
  buildBtn.disabled = false;
  setBadge("Error", "failed");
  jobStatus.textContent = "failed";
  jobStatus.className = "stat-value status-badge status-failed";
  logBody.textContent = error.message || String(error);
}

async function loadDistros() {
  const response = await fetch("/api/distros");
  if (!response.ok) throw new Error("Unable to load distros.");
  const { distros } = await response.json();
  renderOsGrid(distros);
}

async function loadExtraRepos() {
  const response = await fetch("/api/extra-repos");
  if (!response.ok) return;
  const { repos } = await response.json();
  extraRepoCatalog = repos;
  renderExtraRepos();
}

async function loadPresets() {
  const response = await fetch("/api/package-options");
  if (!response.ok) throw new Error("Unable to load package options.");
  const { options } = await response.json();
  renderPresets(options);
}

Promise.all([loadDistros(), loadExtraRepos(), loadPresets(), loadSystemStatus(), loadJobHistory()])
  .catch(showError);
