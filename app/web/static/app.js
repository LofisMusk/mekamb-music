const state = {
  token: localStorage.getItem("mekambMusicToken") || "",
  currentView: "tracks",
  currentAudioUrl: null,
  importsTimer: null,
};

const queueStatuses = ["queued", "downloading", "ready_to_import", "failed"];

const els = {
  tokenForm: document.querySelector("#tokenForm"),
  tokenInput: document.querySelector("#tokenInput"),
  healthStatus: document.querySelector("#healthStatus"),
  trackCount: document.querySelector("#trackCount"),
  artistCount: document.querySelector("#artistCount"),
  activeImports: document.querySelector("#activeImports"),
  trackSearchForm: document.querySelector("#trackSearchForm"),
  trackQuery: document.querySelector("#trackQuery"),
  tracksList: document.querySelector("#tracksList"),
  sourceSearchForm: document.querySelector("#sourceSearchForm"),
  sourceQuery: document.querySelector("#sourceQuery"),
  sourceResults: document.querySelector("#sourceResults"),
  importsList: document.querySelector("#importsList"),
  refreshImports: document.querySelector("#refreshImports"),
  message: document.querySelector("#message"),
  audio: document.querySelector("#audio"),
  nowTitle: document.querySelector("#nowTitle"),
  nowMeta: document.querySelector("#nowMeta"),
  tabs: [...document.querySelectorAll(".tab")],
};

els.tokenInput.value = state.token;

function authHeaders(extra = {}) {
  return {
    ...extra,
    Authorization: `Bearer ${state.token}`,
  };
}

async function api(path, options = {}) {
  if (!state.token && path !== "/health") {
    throw new Error("Najpierw wpisz API token.");
  }

  const response = await fetch(path, {
    ...options,
    headers: authHeaders(options.headers || {}),
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // Response has no JSON body.
    }
    throw new Error(`${response.status}: ${detail}`);
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function setMessage(text, isError = false) {
  els.message.textContent = text;
  els.message.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function formatDuration(seconds) {
  if (!seconds) return "bez czasu";
  if (seconds >= 8640000) return "nieznane";
  if (seconds >= 3600) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  }
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${rest}`;
}

function formatPercent(value) {
  return `${Math.round(Math.max(0, Math.min(1, value || 0)) * 100)}%`;
}

function trackMeta(track) {
  const artist = track.artist || "Nieznany artysta";
  const album = track.album || "Nieznany album";
  return `${artist} • ${album} • ${formatDuration(track.duration_seconds)} • ${formatBytes(track.size_bytes)}`;
}

function renderList(element, items, renderer, emptyText) {
  element.innerHTML = "";
  element.classList.toggle("empty", items.length === 0);
  if (!items.length) {
    element.textContent = emptyText;
    return;
  }
  items.forEach((item) => element.appendChild(renderer(item)));
}

function itemShell(title, meta) {
  const item = document.createElement("article");
  item.className = "item";

  const text = document.createElement("div");
  const titleEl = document.createElement("p");
  titleEl.className = "title";
  titleEl.textContent = title;
  const metaEl = document.createElement("p");
  metaEl.className = "meta";
  metaEl.textContent = meta;
  text.append(titleEl, metaEl);

  const actions = document.createElement("div");
  actions.className = "actions";
  item.append(text, actions);
  return { item, actions };
}

function renderTrack(track) {
  const { item, actions } = itemShell(track.title, trackMeta(track));

  const play = document.createElement("button");
  play.className = "icon";
  play.type = "button";
  play.title = "Odtwórz";
  play.ariaLabel = "Odtwórz";
  play.textContent = "▶";
  play.addEventListener("click", () => runAction(() => playTrack(track)));

  const like = document.createElement("button");
  like.className = "icon quiet";
  like.type = "button";
  like.title = "Polub";
  like.ariaLabel = "Polub";
  like.textContent = "♥";
  like.addEventListener("click", () => runAction(() => likeTrack(track.id)));

  actions.append(play, like);
  return item;
}

function renderImport(download) {
  const record = download.import || download;
  const torrent = download.torrent || null;
  const title = torrent?.name || record.torrent_id;
  const progress = torrent?.progress || 0;
  const details = torrent
    ? [
        `${formatBytes(torrent.downloaded_bytes)} / ${formatBytes(torrent.size_bytes)}`,
        `${formatBytes(torrent.download_speed_bytes)}/s`,
        `ETA ${formatDuration(torrent.eta_seconds)}`,
        torrent.state,
      ].join(" • ")
    : record.error_message || record.source_url;

  const { item, actions } = itemShell(title, details);
  item.classList.add("import-item");

  const progressWrap = document.createElement("div");
  progressWrap.className = "progress-wrap";
  const progressBar = document.createElement("div");
  progressBar.className = "progress-bar";
  progressBar.style.width = formatPercent(progress);
  const progressText = document.createElement("span");
  progressText.className = "progress-text";
  progressText.textContent = formatPercent(progress);
  progressWrap.append(progressBar, progressText);

  const status = document.createElement("span");
  status.className = `pill ${record.status}`;
  status.textContent = record.status;

  if (record.status === "failed") {
    const retry = document.createElement("button");
    retry.className = "quiet";
    retry.type = "button";
    retry.textContent = "Ponów";
    retry.addEventListener("click", () => runAction(() => retryImport(record.id)));
    actions.appendChild(retry);
  }
  if (record.status !== "imported" && record.status !== "canceled") {
    const cancel = document.createElement("button");
    cancel.className = "quiet danger";
    cancel.type = "button";
    cancel.textContent = record.status === "failed" ? "Usuń" : "Anuluj";
    cancel.addEventListener("click", () => runAction(() => cancelImport(record.id)));
    actions.appendChild(cancel);
  }

  item.firstElementChild.appendChild(progressWrap);
  actions.appendChild(status);
  return item;
}

function renderSourceResult(result) {
  const { item, actions } = itemShell(
    result.name,
    `${formatBytes(result.size_bytes)} • S:${result.seeders} L:${result.leechers} • ${result.uploader}`,
  );
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Importuj";
  button.addEventListener("click", () => runAction(() => startImport(result.torrent_id)));
  actions.appendChild(button);
  return item;
}

function topSeededResults(results) {
  return [...results]
    .sort((left, right) => Number(right.seeders || 0) - Number(left.seeders || 0))
    .slice(0, 5);
}

async function loadHealth() {
  try {
    const health = await api("/health");
    els.healthStatus.textContent = health.status;
  } catch (error) {
    els.healthStatus.textContent = "offline";
  }
}

async function loadSummary() {
  const summary = await api("/library/summary");
  els.trackCount.textContent = summary.track_count;
  els.artistCount.textContent = summary.artist_count;
  els.activeImports.textContent = summary.active_import_count;
}

async function loadTracks() {
  const query = els.trackQuery.value.trim();
  let payload;
  if (state.currentView === "liked") {
    payload = await api("/tracks/liked?limit=50");
    renderList(
      els.tracksList,
      payload.items.map((item) => item.track),
      renderTrack,
      "Nie ma jeszcze polubionych utworów.",
    );
    return;
  }
  if (state.currentView === "recent") {
    payload = await api("/tracks/recent?limit=50");
    renderList(
      els.tracksList,
      payload.items.map((item) => item.track),
      renderTrack,
      "Nie ma jeszcze historii odtwarzania.",
    );
    return;
  }

  const params = new URLSearchParams({ limit: "50" });
  if (query) params.set("q", query);
  payload = await api(`/tracks?${params}`);
  renderList(els.tracksList, payload.items, renderTrack, "Brak utworów dla tego wyszukiwania.");
}

async function loadImports() {
  const pages = await Promise.all(
    queueStatuses.map((status) => api(`/imports?status=${encodeURIComponent(status)}&limit=20`)),
  );
  const records = pages
    .flatMap((page) => page.items)
    .sort((left, right) => new Date(right.created_at) - new Date(left.created_at))
    .slice(0, 20);
  const downloads = await Promise.all(
    records.map(async (record) => {
      if (!["queued", "downloading", "ready_to_import", "importing"].includes(record.status)) {
        return { import: record, torrent: null };
      }
      try {
        return await api(`/downloads/${record.id}`);
      } catch {
        return { import: record, torrent: null };
      }
    }),
  );
  renderList(els.importsList, downloads, renderImport, "Kolejka jest pusta.");
}

async function searchSource() {
  const query = els.sourceQuery.value.trim();
  if (!query) return;

  const params = new URLSearchParams({ q: query });
  const payload = await api(`/sources/piratebay/search?${params}`);
  renderList(els.sourceResults, topSeededResults(payload.items), renderSourceResult, "Brak wyników.");
}

async function startImport(torrentId) {
  await api(`/imports/piratebay/${encodeURIComponent(torrentId)}`, { method: "POST" });
  setMessage("Import dodany do kolejki.");
  await Promise.allSettled([loadImports(), loadSummary()]);
}

async function cancelImport(importId) {
  await api(`/imports/${encodeURIComponent(importId)}/cancel?delete_files=true`, { method: "POST" });
  setMessage("Import usunięty z kolejki.");
  await Promise.allSettled([loadImports(), loadSummary()]);
}

async function retryImport(importId) {
  await api(`/imports/${encodeURIComponent(importId)}/retry?delete_files=true`, { method: "POST" });
  setMessage("Import dodany ponownie.");
  await Promise.allSettled([loadImports(), loadSummary()]);
}

async function likeTrack(trackId) {
  await api(`/tracks/${trackId}/like`, { method: "PUT" });
  setMessage("Utwór polubiony.");
}

async function playTrack(track) {
  setMessage("Ładuję plik audio...");
  const response = await fetch(`/tracks/${track.id}/stream`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(`${response.status}: Nie udało się załadować streamu.`);
  }

  if (state.currentAudioUrl) {
    URL.revokeObjectURL(state.currentAudioUrl);
  }
  const contentType = response.headers.get("Content-Type") || track.media_type || "application/octet-stream";
  const blob = new Blob([await response.arrayBuffer()], { type: contentType });
  state.currentAudioUrl = URL.createObjectURL(blob);
  els.audio.src = state.currentAudioUrl;
  els.nowTitle.textContent = track.title;
  els.nowMeta.textContent = trackMeta(track);
  await api(`/tracks/${track.id}/plays`, { method: "POST" });
  await els.audio.play();
  setMessage("");
}

async function refreshAll() {
  try {
    await loadHealth();
    if (!state.token) return;
    await Promise.all([loadSummary(), loadTracks(), loadImports()]);
    setMessage("Gotowe.");
  } catch (error) {
    setMessage(error.message, true);
  }
}

function startImportsAutoRefresh() {
  if (state.importsTimer) return;
  state.importsTimer = window.setInterval(async () => {
    if (!state.token) return;
    try {
      await Promise.allSettled([loadImports(), loadSummary()]);
    } catch {
      // Manual refresh will show any persistent error.
    }
  }, 5000);
}

async function runAction(action) {
  try {
    await action();
  } catch (error) {
    setMessage(error.message, true);
  }
}

els.tokenForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.token = els.tokenInput.value.trim();
  localStorage.setItem("mekambMusicToken", state.token);
  await refreshAll();
});

els.trackSearchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await loadTracks();
  } catch (error) {
    setMessage(error.message, true);
  }
});

els.sourceSearchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await searchSource();
  } catch (error) {
    setMessage(error.message, true);
  }
});

els.refreshImports.addEventListener("click", async () => {
  try {
    await loadImports();
  } catch (error) {
    setMessage(error.message, true);
  }
});

els.tabs.forEach((tab) => {
  tab.addEventListener("click", async () => {
    state.currentView = tab.dataset.view;
    els.tabs.forEach((item) => item.classList.toggle("active", item === tab));
    try {
      await loadTracks();
    } catch (error) {
      setMessage(error.message, true);
    }
  });
});

refreshAll();
startImportsAutoRefresh();
