const state = {
  token: localStorage.getItem("mekambMusicToken") || "",
  currentView: "tracks",
  currentAudioUrl: null,
  artworkUrls: new Set(),
  importsTimer: null,
  visibleTracks: [],
  queue: [],
  queueIndex: -1,
  shuffle: false,
  loop: "off",
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
  prevTrack: document.querySelector("#prevTrack"),
  nextTrack: document.querySelector("#nextTrack"),
  shuffleToggle: document.querySelector("#shuffleToggle"),
  loopToggle: document.querySelector("#loopToggle"),
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

function albumKey(track) {
  return `${track.artist || "Nieznany artysta"}\u0000${track.album || "Nieznany album"}`;
}

function groupTracksByAlbum(tracks) {
  const groups = new Map();
  tracks.forEach((track) => {
    const key = albumKey(track);
    if (!groups.has(key)) {
      groups.set(key, {
        artist: track.artist || "Nieznany artysta",
        album: track.album || "Nieznany album",
        tracks: [],
      });
    }
    groups.get(key).tracks.push(track);
  });
  return [...groups.values()].sort((left, right) => (
    `${left.artist} ${left.album}`.localeCompare(`${right.artist} ${right.album}`, "pl")
  ));
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

function placeholderArtwork() {
  return "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";
}

function clearArtworkUrls() {
  state.artworkUrls.forEach((url) => URL.revokeObjectURL(url));
  state.artworkUrls.clear();
}

async function loadArtwork(img, trackId) {
  try {
    const response = await fetch(`/tracks/${encodeURIComponent(trackId)}/artwork`, {
      headers: authHeaders(),
    });
    if (!response.ok) throw new Error("Artwork not found.");
    const url = URL.createObjectURL(await response.blob());
    state.artworkUrls.add(url);
    img.src = url;
  } catch {
    img.classList.add("missing");
    img.src = placeholderArtwork();
  }
}

function renderAlbum(group) {
  const item = document.createElement("article");
  item.className = "album-item";

  const cover = document.createElement("img");
  cover.className = "album-cover";
  cover.alt = "";
  cover.loading = "lazy";
  cover.src = placeholderArtwork();
  loadArtwork(cover, group.tracks[0].id);

  const text = document.createElement("div");
  const title = document.createElement("p");
  title.className = "title";
  title.textContent = group.album;
  const meta = document.createElement("p");
  meta.className = "meta";
  meta.textContent = `${group.artist} • ${group.tracks.length} utw.`;
  const trackList = document.createElement("div");
  trackList.className = "album-tracks";
  group.tracks.forEach((track) => trackList.appendChild(renderTrack(track)));
  text.append(title, meta, trackList);

  const actions = document.createElement("div");
  actions.className = "actions";
  const play = document.createElement("button");
  play.type = "button";
  play.textContent = "Odtwórz";
  play.addEventListener("click", () => runAction(async () => {
    state.queue = [...group.tracks];
    state.queueIndex = 0;
    await playCurrentQueueTrack();
  }));
  actions.appendChild(play);

  item.append(cover, text, actions);
  return item;
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
  play.addEventListener("click", () => runAction(() => playFromVisibleQueue(track.id)));

  const add = document.createElement("button");
  add.className = "icon quiet";
  add.type = "button";
  add.title = "Dodaj do kolejki";
  add.ariaLabel = "Dodaj do kolejki";
  add.textContent = "+";
  add.addEventListener("click", () => {
    addToQueue(track);
    setMessage("Dodano do kolejki.");
  });

  const like = document.createElement("button");
  like.className = "icon quiet";
  like.type = "button";
  like.title = "Polub";
  like.ariaLabel = "Polub";
  like.textContent = "♥";
  like.addEventListener("click", () => runAction(() => likeTrack(track.id)));

  actions.append(play, add, like);
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
  clearArtworkUrls();
  const query = els.trackQuery.value.trim();
  let payload;
  if (state.currentView === "liked") {
    payload = await api("/tracks/liked?limit=50");
    state.visibleTracks = payload.items.map((item) => item.track);
    renderList(
      els.tracksList,
      state.visibleTracks,
      renderTrack,
      "Nie ma jeszcze polubionych utworów.",
    );
    return;
  }
  if (state.currentView === "recent") {
    payload = await api("/tracks/recent?limit=50");
    state.visibleTracks = payload.items.map((item) => item.track);
    renderList(
      els.tracksList,
      state.visibleTracks,
      renderTrack,
      "Nie ma jeszcze historii odtwarzania.",
    );
    return;
  }

  const params = new URLSearchParams({ limit: "50" });
  if (query) params.set("q", query);
  payload = await api(`/tracks?${params}`);
  state.visibleTracks = payload.items;
  if (state.currentView === "albums") {
    renderList(
      els.tracksList,
      groupTracksByAlbum(state.visibleTracks),
      renderAlbum,
      "Brak albumów dla tego wyszukiwania.",
    );
    return;
  }
  renderList(
    els.tracksList,
    state.visibleTracks,
    renderTrack,
    "Brak utworów dla tego wyszukiwania.",
  );
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

function addToQueue(track) {
  state.queue.push(track);
  if (state.queueIndex === -1) state.queueIndex = 0;
}

function setQueueFromVisible(startTrackId) {
  const tracks = state.shuffle ? shuffled(state.visibleTracks) : [...state.visibleTracks];
  const selectedIndex = tracks.findIndex((track) => track.id === startTrackId);
  state.queue = tracks;
  state.queueIndex = selectedIndex >= 0 ? selectedIndex : 0;
}

function shuffled(items) {
  const copy = [...items];
  for (let index = copy.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [copy[index], copy[swapIndex]] = [copy[swapIndex], copy[index]];
  }
  return copy;
}

async function playFromVisibleQueue(trackId) {
  setQueueFromVisible(trackId);
  await playCurrentQueueTrack();
}

async function playCurrentQueueTrack() {
  const track = state.queue[state.queueIndex];
  if (!track) return;
  await playTrack(track);
}

async function playNextTrack() {
  if (!state.queue.length) return;
  if (state.loop === "one") {
    await playCurrentQueueTrack();
    return;
  }
  if (state.queueIndex < state.queue.length - 1) {
    state.queueIndex += 1;
  } else if (state.loop === "all") {
    state.queueIndex = 0;
  } else {
    return;
  }
  await playCurrentQueueTrack();
}

async function playPreviousTrack() {
  if (!state.queue.length) return;
  if (state.queueIndex > 0) {
    state.queueIndex -= 1;
  } else if (state.loop === "all") {
    state.queueIndex = state.queue.length - 1;
  }
  await playCurrentQueueTrack();
}

function updateTransport() {
  els.shuffleToggle.classList.toggle("active", state.shuffle);
  els.loopToggle.classList.toggle("active", state.loop !== "off");
  els.loopToggle.textContent = state.loop === "one" ? "↺1" : "↻";
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

els.nextTrack.addEventListener("click", () => runAction(playNextTrack));
els.prevTrack.addEventListener("click", () => runAction(playPreviousTrack));
els.audio.addEventListener("ended", () => runAction(playNextTrack));

els.shuffleToggle.addEventListener("click", () => {
  state.shuffle = !state.shuffle;
  updateTransport();
  setMessage(state.shuffle ? "Shuffle włączony." : "Shuffle wyłączony.");
});

els.loopToggle.addEventListener("click", () => {
  state.loop = state.loop === "off" ? "all" : state.loop === "all" ? "one" : "off";
  updateTransport();
  setMessage(state.loop === "off" ? "Loop wyłączony." : `Loop ${state.loop === "one" ? "utworu" : "kolejki"}.`);
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
updateTransport();
