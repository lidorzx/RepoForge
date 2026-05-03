// ── DOM refs ────────────────────────────────────────────────────────────────
const jobForm       = document.getElementById("jobForm");
const packagesInput = document.getElementById("packages");
const buildBtn      = document.getElementById("buildBtn");
const downloadLink  = document.getElementById("downloadLink");
const dockerDot     = document.getElementById("dockerDot");
const dockerLabel   = document.getElementById("dockerLabel");
const buildBadge    = document.getElementById("buildBadge");
const badgeText     = document.getElementById("badgeText");
const osFamilies    = document.getElementById("osFamilies");
const extraRepoList = document.getElementById("extraRepoList");
const presetGrid    = document.getElementById("presetGrid");
const distroMeta    = document.getElementById("distroMeta");
const jobStatus     = document.getElementById("jobStatus");
const jobDistro     = document.getElementById("jobDistro");
const jobPackages   = document.getElementById("jobPackages");
const bundleSize    = document.getElementById("bundleSize");
const logBody       = document.getElementById("logs");
const logJobId      = document.getElementById("logJobId");
const jobHistory    = document.getElementById("jobHistory");

// ── State ────────────────────────────────────────────────────────────────────
let pollTimer        = null;
let distroCatalog    = {};   // { distro_id: DistroInfo }
let allOptions       = [];   // PackageOption[]
let extraRepoCatalog = {};   // { repo_id: ExtraRepoInfo }
let selectedDistroId = "ubuntu-22.04";
const enabledRepos   = new Map(); // repo_id -> version (or null)

// ── Helpers ──────────────────────────────────────────────────────────────────
function parsePackages(value) {
  return value.split(",").map(s => s.trim()).filter(Boolean);
}

function addPackages(pkgs) {
  const merged = [...new Set([...parsePackages(packagesInput.value), ...pkgs])];
  packagesInput.value = merged.join(", ");
}

function formatBytes(bytes) {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes, u = 0;
  while (size >= 1024 && u < units.length - 1) { size /= 1024; u++; }
  return `${size.toFixed(u === 0 ? 0 : 1)} ${units[u]}`;
}

function setBadge(text, state) {
  badgeText.textContent = text;
  buildBadge.className = "build-badge " + (state || "");
}

// ── OS card grid ─────────────────────────────────────────────────────────────
const FAMILY_META = {
  debian: { label: "Debian / Ubuntu" },
  rhel:   { label: "RHEL Family" },
};

function renderOsGrid(catalog) {
  distroCatalog = catalog;
  const groups = {};
  for (const [id, info] of Object.entries(catalog)) {
    const f = info.family;
    if (!groups[f]) groups[f] = [];
    groups[f].push({ id, ...info });
  }

  osFamilies.innerHTML = "";
  for (const [family, distros] of Object.entries(groups)) {
    const meta = FAMILY_META[family] || { label: family };
    const section = document.createElement("div");
    section.className = "os-family";

    const heading = document.createElement("div");
    heading.className = "os-family-label";
    heading.textContent = meta.label;
    section.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "os-card-grid";

    for (const distro of distros) {
      const label = document.createElement("label");
      label.className = "os-card" + (distro.id === selectedDistroId ? " selected" : "");
      label.dataset.distroId = distro.id;

      // Split label into name + detail
      let osName = distro.label, osDetail = "";
      if (distro.id.startsWith("ubuntu-"))    { osName = "Ubuntu";       osDetail = distro.label.replace("Ubuntu ", ""); }
      else if (distro.id.startsWith("debian-")) { osName = "Debian";     osDetail = distro.label.replace("Debian ", ""); }
      else if (distro.id.startsWith("rocky-"))  { osName = "Rocky Linux"; osDetail = distro.label.replace("Rocky Linux ", ""); }
      else if (distro.id.startsWith("almalinux-")) { osName = "AlmaLinux"; osDetail = distro.label.replace("AlmaLinux ", ""); }

      const pkgBadge = distro.pkg_ext === "rpm"
        ? `<span class="pkg-badge rpm">RPM</span>`
        : `<span class="pkg-badge deb">DEB</span>`;

      label.innerHTML = `
        <input type="radio" name="distro" value="${distro.id}" ${distro.id === selectedDistroId ? "checked" : ""} />
        <span class="os-card-inner">
          <span class="os-name">${osName}</span>
          <span class="os-detail">${osDetail}</span>
          ${pkgBadge}
        </span>`;

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
  document.querySelectorAll(".os-card").forEach(card => {
    card.classList.toggle("selected", card.dataset.distroId === distroId);
  });
  updateDistroMeta();
  filterPresets();
  renderExtraRepos();
}

function updateDistroMeta() {
  const info = distroCatalog[selectedDistroId];
  if (!info) { distroMeta.innerHTML = ""; return; }
  if (info.family === "debian" && info.suites) {
    distroMeta.innerHTML = `
      <span class="meta-key">Codename</span><span class="meta-val">${info.codename}</span>
      <span class="meta-key">Suites</span><span class="meta-val">${info.suites.join(", ")}</span>`;
  } else {
    distroMeta.innerHTML = `
      <span class="meta-key">Codename</span><span class="meta-val">${info.codename || "—"}</span>
      <span class="meta-key">Package manager</span><span class="meta-val">dnf / rpm</span>`;
  }
}

// ── Extra Repositories ────────────────────────────────────────────────────────
function renderExtraRepos() {
  const info = distroCatalog[selectedDistroId];
  const family = info ? info.family : null;
  extraRepoList.innerHTML = "";

  let anyVisible = false;
  for (const [repoId, repo] of Object.entries(extraRepoCatalog)) {
    const compatible = !family || repo.families.includes(family);
    if (!compatible) continue;
    anyVisible = true;

    const isEnabled = enabledRepos.has(repoId);
    const currentVersion = enabledRepos.get(repoId) || repo.default_version;

    const row = document.createElement("div");
    row.className = "repo-row" + (isEnabled ? " enabled" : "");
    row.dataset.repoId = repoId;

    const versionSelect = repo.versioned
      ? `<select class="repo-version-select" data-repo-id="${repoId}" ${!isEnabled ? "disabled" : ""}>
          ${repo.versions.map(v =>
            `<option value="${v}" ${v === currentVersion ? "selected" : ""}>${v}</option>`
          ).join("")}
        </select>`
      : "";

    row.innerHTML = `
      <label class="repo-toggle-label">
        <input type="checkbox" class="repo-checkbox" data-repo-id="${repoId}" ${isEnabled ? "checked" : ""} />
        <span class="repo-toggle-slider"></span>
      </label>
      <div class="repo-info">
        <span class="repo-name">${repo.label}</span>
        <span class="repo-desc">${repo.description}</span>
      </div>
      ${versionSelect}
    `;

    const checkbox = row.querySelector(".repo-checkbox");
    checkbox.addEventListener("change", () => toggleRepo(repoId, checkbox.checked, row));

    const sel = row.querySelector(".repo-version-select");
    if (sel) {
      sel.addEventListener("change", () => {
        if (enabledRepos.has(repoId)) enabledRepos.set(repoId, sel.value);
      });
    }

    extraRepoList.appendChild(row);
  }

  if (!anyVisible) {
    extraRepoList.innerHTML = `<p class="no-presets" style="padding:14px 18px">No extra repositories available for this OS family.</p>`;
  }
}

function toggleRepo(repoId, enabled, row) {
  const repo = extraRepoCatalog[repoId];
  const sel = row.querySelector(".repo-version-select");

  if (enabled) {
    const version = sel ? sel.value : null;
    enabledRepos.set(repoId, version);
    row.classList.add("enabled");
    if (sel) sel.disabled = false;
    // Auto-add the default packages
    if (repo.default_packages && repo.default_packages.length) {
      addPackages(repo.default_packages);
    }
  } else {
    enabledRepos.delete(repoId);
    row.classList.remove("enabled");
    if (sel) sel.disabled = true;
  }
}

function buildExtraReposPayload() {
  const result = [];
  for (const [repoId, version] of enabledRepos.entries()) {
    result.push(version ? `${repoId}:${version}` : repoId);
  }
  return result;
}

// ── Preset cards ─────────────────────────────────────────────────────────────
function renderPresets(options) {
  allOptions = options;
  filterPresets();
}

function filterPresets() {
  const info = distroCatalog[selectedDistroId];
  const family = info ? info.family : null;
  const visible = family
    ? allOptions.filter(o => o.distro_families.includes(family))
    : allOptions;

  presetGrid.innerHTML = "";
  if (!visible.length) {
    presetGrid.innerHTML = `<p class="no-presets">No presets for this OS.</p>`;
    return;
  }
  for (const opt of visible) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "preset-card";
    card.innerHTML = `
      <strong>${opt.title}</strong>
      <span>${opt.description}</span>
      <div class="chip-row">${opt.packages.map(p => `<span class="chip">${p}</span>`).join("")}</div>`;
    card.addEventListener("click", () => addPackages(opt.packages));
    presetGrid.appendChild(card);
  }
}

// ── Job rendering ─────────────────────────────────────────────────────────────
const STATUS_CLASS = {
  queued: "status-queued", running: "status-running",
  completed: "status-done", failed: "status-failed",
};

function renderJob(job) {
  const cls = STATUS_CLASS[job.status] || "";
  jobStatus.textContent = job.status;
  jobStatus.className = "stat-value status-badge " + cls;

  const distroInfo = distroCatalog[job.distro_id];
  jobDistro.textContent = distroInfo ? distroInfo.label : job.distro_id;
  jobPackages.textContent = job.packages.join(", ") || "—";
  bundleSize.textContent = formatBytes(job.bundle_size_bytes);
  logJobId.textContent = job.job_id;
  logBody.textContent = job.logs.length ? job.logs.join("\n") : "Waiting for logs…";
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
    setBadge(job.status === "running" ? "Building…" : "Queued", "running");
  }
}

// ── System status ─────────────────────────────────────────────────────────────
async function loadSystemStatus() {
  const res = await fetch("/api/system");
  if (!res.ok) return;
  const sys = await res.json();
  const ok = sys.docker_cli_available && sys.docker_server_available;
  dockerDot.className = "indicator-dot " + (ok ? "dot-ok" : "dot-err");
  dockerLabel.textContent = ok ? `Docker ${sys.docker_version || ""}`.trim() : "Docker unavailable";
}

// ── Job history ───────────────────────────────────────────────────────────────
async function loadJobHistory() {
  const res = await fetch("/api/jobs");
  if (!res.ok) return;
  const { jobs } = await res.json();
  if (!jobs.length) {
    jobHistory.innerHTML = `<div class="history-empty">No jobs yet.</div>`;
    return;
  }
  jobHistory.innerHTML = "";
  for (const job of jobs.slice(0, 10)) {
    const distroInfo = distroCatalog[job.distro_id];
    const distroLabel = distroInfo ? distroInfo.label : job.distro_id;
    const cls = STATUS_CLASS[job.status] || "";
    const row = document.createElement("div");
    row.className = "history-row";
    row.innerHTML = `
      <span class="status-badge ${cls}">${job.status}</span>
      <code class="history-id">${job.job_id.slice(0, 8)}…</code>
      <span class="history-distro">${distroLabel} / ${job.architecture}</span>
      <span class="history-pkgs">${job.packages.join(", ")}</span>
      <span class="history-size">${formatBytes(job.bundle_size_bytes)}</span>`;
    if (job.status === "completed") {
      const dl = document.createElement("a");
      dl.href = `/api/jobs/${job.job_id}/download`;
      dl.className = "history-dl";
      dl.textContent = "↓";
      dl.title = "Download";
      row.appendChild(dl);
    }
    jobHistory.appendChild(row);
  }
}

// ── Polling ────────────────────────────────────────────────────────────────────
async function pollJob(jobId) {
  const res = await fetch(`/api/jobs/${jobId}`);
  if (!res.ok) throw new Error("Unable to fetch job status.");
  const job = await res.json();
  renderJob(job);
  if (job.status === "completed" || job.status === "failed") {
    clearInterval(pollTimer);
    pollTimer = null;
    loadJobHistory().catch(() => {});
  }
}

// ── Form submit ───────────────────────────────────────────────────────────────
jobForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const packages = parsePackages(packagesInput.value);
  if (!packages.length) { logBody.textContent = "Enter at least one package name."; return; }

  const archEl = document.querySelector('input[name="arch"]:checked');
  const architecture = archEl ? archEl.value : "amd64";
  const extra_repos = buildExtraReposPayload();

  buildBtn.disabled = true;
  downloadLink.classList.add("hidden");
  setBadge("Submitting…", "running");
  logBody.textContent = "Submitting job…";

  try {
    const res = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ distro_id: selectedDistroId, architecture, packages, extra_repos }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail ? JSON.stringify(detail.detail) : "Job submission failed.");
    }
    const job = await res.json();
    renderJob(job);
    clearInterval(pollTimer);
    loadJobHistory().catch(() => {});
    pollTimer = setInterval(() => pollJob(job.job_id).catch(showError), 2500);
  } catch (err) {
    showError(err);
  }
});

function showError(err) {
  clearInterval(pollTimer);
  pollTimer = null;
  buildBtn.disabled = false;
  setBadge("Error", "failed");
  jobStatus.textContent = "failed";
  jobStatus.className = "stat-value status-badge status-failed";
  logBody.textContent = err.message || String(err);
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────
async function loadDistros() {
  const res = await fetch("/api/distros");
  if (!res.ok) throw new Error("Unable to load distros.");
  const { distros } = await res.json();
  renderOsGrid(distros);
}

async function loadExtraRepos() {
  const res = await fetch("/api/extra-repos");
  if (!res.ok) return;
  const { repos } = await res.json();
  extraRepoCatalog = repos;
  renderExtraRepos();
}

async function loadPresets() {
  const res = await fetch("/api/package-options");
  if (!res.ok) throw new Error("Unable to load package options.");
  const { options } = await res.json();
  renderPresets(options);
}

Promise.all([loadDistros(), loadExtraRepos(), loadPresets(), loadSystemStatus(), loadJobHistory()])
  .catch(showError);
