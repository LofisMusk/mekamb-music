const state = {
  token: localStorage.getItem("mekambMusicToken") || "",
  apiEndpoints: readApiEndpoints(),
  apiBase: normalizeEndpoint(localStorage.getItem("mekambMusicApiBase") || ""),
  currentView: "tracks",
  currentAudioUrl: null,
  artworkUrls: new Set(),
  importsTimer: null,
  visibleTracks: [],
  expandedAlbumKey: "",
  queue: [],
  queueIndex: -1,
  shuffle: false,
  loop: "off",
};

const queueStatuses = ["queued", "downloading", "ready_to_import", "failed"];

const els = {
  tokenForm: document.querySelector("#tokenForm"),
  apiEndpointsInput: document.querySelector("#apiEndpointsInput"),
  apiBaseStatus: document.querySelector("#apiBaseStatus"),
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
els.apiEndpointsInput.value = state.apiEndpoints.join("\n");

function normalizeEndpoint(endpoint) {
  return (endpoint || "").trim().replace(/\/+$/, "");
}

function currentOriginEndpoint() {
  if (window.location.protocol === "http:" || window.location.protocol === "https:") {
    return window.location.origin;
  }
  return "";
}

function parseApiEndpoints(value) {
  const seen = new Set();
  return (value || "")
    .split(/[,\n]/)
    .map(normalizeEndpoint)
    .filter((endpoint) => {
      if (!endpoint || seen.has(endpoint)) return false;
      seen.add(endpoint);
      return true;
    });
}

function readApiEndpoints() {
  const saved = parseApiEndpoints(localStorage.getItem("mekambMusicApiEndpoints") || "");
  if (saved.length) return saved;
  const origin = currentOriginEndpoint();
  return origin ? [origin] : [];
}

function saveApiEndpoints() {
  state.apiEndpoints = parseApiEndpoints(els.apiEndpointsInput.value);
  localStorage.setItem("mekambMusicApiEndpoints", state.apiEndpoints.join("\n"));
}

function endpointCandidates(skipEndpoint = "") {
  const seen = new Set();
  return [state.apiBase, ...state.apiEndpoints, currentOriginEndpoint()]
    .map(normalizeEndpoint)
    .filter((endpoint) => {
      if (!endpoint || endpoint === skipEndpoint || seen.has(endpoint)) return false;
      seen.add(endpoint);
      return true;
    });
}

function apiUrl(path, endpoint = state.apiBase) {
  const base = normalizeEndpoint(endpoint);
  if (!base) throw new Error("Dodaj adres API.");
  return new URL(path, base).toString();
}

function setApiBase(endpoint) {
  state.apiBase = normalizeEndpoint(endpoint);
  localStorage.setItem("mekambMusicApiBase", state.apiBase);
  els.apiBaseStatus.textContent = state.apiBase ? `Aktywne API: ${state.apiBase}` : "Brak aktywnego API";
}

async function rawFetch(url, options = {}) {
  if (window.mekambDesktop?.fetchApi) {
    const result = await window.mekambDesktop.fetchApi({
      url,
      method: options.method || "GET",
      headers: options.headers || {},
      body: options.body,
      timeoutMs: options.timeoutMs,
    });
    return new Response(result.body, {
      status: result.status,
      statusText: result.statusText,
      headers: result.headers,
    });
  }

  if (!options.timeoutMs) return fetch(url, options);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    window.clearTimeout(timeout);
  }
}

async function selectApiBase(skipEndpoint = "") {
  const candidates = endpointCandidates(skipEndpoint);
  if (!candidates.length) {
    setApiBase("");
    throw new Error("Dodaj adres API.");
  }

  for (const endpoint of candidates) {
    try {
      const response = await rawFetch(apiUrl("/health", endpoint), { timeoutMs: 3500 });
      if (response.ok) {
        setApiBase(endpoint);
        return endpoint;
      }
    } catch {
      // Try the next configured API endpoint.
    }
  }

  setApiBase("");
  throw new Error("Żaden adres API nie odpowiada.");
}

function authHeaders(extra = {}) {
  return {
    ...extra,
    Authorization: `Bearer ${state.token}`,
  };
}

async function apiResponse(path, options = {}, allowRetry = true) {
  if (!state.token && path !== "/health") {
    throw new Error("Najpierw wpisz API token.");
  }

  if (!state.apiBase) await selectApiBase();
  const needsAuth = path !== "/health";
  const headers = needsAuth ? authHeaders(options.headers || {}) : options.headers || {};

  let response;
  try {
    response = await rawFetch(apiUrl(path), { ...options, headers });
  } catch (error) {
    if (!allowRetry) throw error;
    const failedEndpoint = state.apiBase;
    await selectApiBase(failedEndpoint);
    response = await rawFetch(apiUrl(path), { ...options, headers });
  }

  if (!response.ok && allowRetry && [502, 503, 504].includes(response.status)) {
    const failedEndpoint = state.apiBase;
    await selectApiBase(failedEndpoint);
    response = await rawFetch(apiUrl(path), { ...options, headers });
  }

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

  return response;
}

async function api(path, options = {}) {
  const response = await apiResponse(path, options);

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

function normalizeAlbumName(album) {
  return (album || "Nieznany album")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function albumKey(track) {
  return normalizeAlbumName(track.album);
}

function mostCommonArtist(tracks) {
  const counts = new Map();
  tracks.forEach((track) => {
    const artist = track.artist || "Nieznany artysta";
    counts.set(artist, (counts.get(artist) || 0) + 1);
  });
  return [...counts.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] || "Nieznany artysta";
}

function trackNumber(track) {
  const value = `${track.original_filename || ""} ${track.title || ""}`;
  const patterns = [
    /(?:^|[/\s_-])(\d{1,3})\s*[.)_-]/,
    /-(\d{1,3})\s*[.)_-]/,
  ];
  for (const pattern of patterns) {
    const match = value.match(pattern);
    if (match) return Number(match[1]);
  }
  return Number.POSITIVE_INFINITY;
}

function sortAlbumTracks(tracks) {
  return [...tracks].sort((left, right) => {
    const leftNumber = trackNumber(left);
    const rightNumber = trackNumber(right);
    if (leftNumber !== rightNumber) return leftNumber - rightNumber;
    const leftDate = Date.parse(left.created_at || "") || 0;
    const rightDate = Date.parse(right.created_at || "") || 0;
    if (leftDate !== rightDate) return leftDate - rightDate;
    return (left.title || "").localeCompare(right.title || "", "pl");
  });
}

function groupTracksByAlbum(tracks) {
  const groups = new Map();
  tracks.forEach((track) => {
    const key = albumKey(track);
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        album: track.album || "Nieznany album",
        tracks: [],
      });
    }
    groups.get(key).tracks.push(track);
  });
  return [...groups.values()]
    .map((group) => {
      const sortedTracks = sortAlbumTracks(group.tracks);
      return { ...group, artist: mostCommonArtist(sortedTracks), tracks: sortedTracks };
    })
    .sort((left, right) => left.album.localeCompare(right.album, "pl"));
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

function setTracksListMode(mode) {
  els.tracksList.classList.toggle("album-grid", mode === "albums");
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
    const response = await apiResponse(`/tracks/${encodeURIComponent(trackId)}/artwork`);
    const url = URL.createObjectURL(await response.blob());
    state.artworkUrls.add(url);
    img.src = url;
  } catch {
    img.classList.add("missing");
    img.src = placeholderArtwork();
  }
}

function renderAlbum(group) {
  const isExpanded = state.expandedAlbumKey === group.key;
  const item = document.createElement("article");
  item.className = "album-item";
  item.classList.toggle("expanded", isExpanded);

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
  trackList.addEventListener("click", (event) => event.stopPropagation());
  if (isExpanded) {
    group.tracks.forEach((track) => trackList.appendChild(renderTrack(track)));
    text.append(title, meta, trackList);
  } else {
    text.append(title, meta);
  }

  const actions = document.createElement("div");
  actions.className = "actions";
  const toggle = document.createElement("button");
  toggle.className = "quiet";
  toggle.type = "button";
  toggle.textContent = isExpanded ? "Zwiń" : "Otwórz";
  toggle.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleAlbum(group.key);
  });

  const play = document.createElement("button");
  play.type = "button";
  play.textContent = "Odtwórz";
  play.addEventListener("click", (event) => event.stopPropagation());
  play.addEventListener("click", () => runAction(async () => {
    state.queue = [...group.tracks];
    state.queueIndex = 0;
    await playCurrentQueueTrack();
  }));
  actions.append(toggle, play);

  item.addEventListener("click", () => toggleAlbum(group.key));
  item.append(cover, text, actions);
  return item;
}

function toggleAlbum(key) {
  state.expandedAlbumKey = state.expandedAlbumKey === key ? "" : key;
  renderList(
    els.tracksList,
    groupTracksByAlbum(state.visibleTracks),
    renderAlbum,
    "Brak albumów dla tego wyszukiwania.",
  );
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
    `${sourceLabel(result.source)} • ${result.size_label} • S:${result.seeders} L:${result.leechers} • ${result.uploader}`,
  );
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Importuj";
  button.addEventListener("click", () => runAction(() => startImport(result)));
  actions.appendChild(button);
  return item;
}

function sourceLabel(source) {
  return source === "1337x" ? "1337x" : "Pirate Bay";
}

function normalizeSourceResult(result, source) {
  return {
    ...result,
    source,
    size_label: source === "piratebay" ? formatBytes(result.size_bytes) : result.size || "nieznany rozmiar",
    seeders_number: Number.parseInt(result.seeders || "0", 10) || 0,
  };
}

function topSeededResults(results) {
  return [...results]
    .sort((left, right) => right.seeders_number - left.seeders_number)
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
    setTracksListMode("tracks");
    payload = await api("/tracks/liked?limit=50");
    state.visibleTracks = payload.items.map((item) => item.track);
    renderList(
      els.tracksList,
      state.visibleTracks,
      renderTrack,
      "Nie ma jeszcze polubionych utworów.",
    );
    return state.visibleTracks.length;
  }
  if (state.currentView === "recent") {
    setTracksListMode("tracks");
    payload = await api("/tracks/recent?limit=50");
    state.visibleTracks = payload.items.map((item) => item.track);
    renderList(
      els.tracksList,
      state.visibleTracks,
      renderTrack,
      "Nie ma jeszcze historii odtwarzania.",
    );
    return state.visibleTracks.length;
  }

  const params = new URLSearchParams({ limit: state.currentView === "albums" ? "200" : "50" });
  if (query) params.set("q", query);
  payload = await api(`/tracks?${params}`);
  state.visibleTracks = payload.items;
  if (state.currentView === "albums") {
    setTracksListMode("albums");
    renderList(
      els.tracksList,
      groupTracksByAlbum(state.visibleTracks),
      renderAlbum,
      "Brak albumów dla tego wyszukiwania.",
    );
    return state.visibleTracks.length;
  }
  setTracksListMode("tracks");
  renderList(
    els.tracksList,
    state.visibleTracks,
    renderTrack,
    "Brak utworów dla tego wyszukiwania.",
  );
  return state.visibleTracks.length;
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

  const results = await searchTorrentSources(query);
  renderList(els.sourceResults, results, renderSourceResult, "Brak wyników.");
}

async function searchTorrentSources(query) {
  const searches = await Promise.allSettled([
    searchPirateBay(query),
    search1337x(query),
  ]);
  const results = searches
    .filter((search) => search.status === "fulfilled")
    .flatMap((search) => search.value);

  if (!results.length && searches.every((search) => search.status === "rejected")) {
    throw searches[0].reason;
  }

  return topSeededResults(results);
}

async function searchPirateBay(query) {
  const params = new URLSearchParams({ q: query });
  const payload = await api(`/sources/piratebay/search?${params}`);
  return payload.items.map((item) => normalizeSourceResult(item, "piratebay"));
}

async function search1337x(query) {
  const params = new URLSearchParams({ q: query, sort_by: "seeders" });
  const payload = await api(`/sources/1337x/search?${params}`);
  return payload.items.map((item) => normalizeSourceResult(item, "1337x"));
}

async function startImport(resultOrTorrentId, source = "piratebay") {
  const result = typeof resultOrTorrentId === "object" ? resultOrTorrentId : null;
  const torrentId = result ? result.torrent_id : resultOrTorrentId;
  const importSource = result ? result.source : source;
  const endpoint = importSource === "1337x" ? "1337x" : "piratebay";
  const record = await api(`/imports/${endpoint}/${encodeURIComponent(torrentId)}`, { method: "POST" });
  setMessage("Import dodany do kolejki.");
  await Promise.allSettled([loadImports(), loadSummary()]);
  return record;
}

async function libraryHasQuery(query) {
  const params = new URLSearchParams({ q: query, limit: "1" });
  const payload = await api(`/tracks?${params}`);
  return payload.items.length > 0;
}

async function importFirstTorrentResult(query) {
  setMessage("Nie ma w bibliotece. Szukam w torrentach...");
  const results = await searchTorrentSources(query);
  renderList(els.sourceResults, results, renderSourceResult, "Brak wyników.");
  if (!results.length) {
    setMessage("Nie ma w bibliotece i nie znalazłem wyniku w torrentach.", true);
    return;
  }

  const best = results[0];
  setMessage(`Nie ma w bibliotece. Dodaję do kolejki: ${best.name}`);
  await startImport(best);
}

async function runGlobalSearch() {
  const query = els.trackQuery.value.trim();
  const renderedCount = await loadTracks();
  if (!query) return;

  if (renderedCount > 0 || await libraryHasQuery(query)) {
    setMessage("Znaleziono w bibliotece.");
    return;
  }

  await importFirstTorrentResult(query);
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
  const response = await apiResponse(`/tracks/${track.id}/stream`);

  if (state.currentAudioUrl) {
    URL.revokeObjectURL(state.currentAudioUrl);
  }
  const contentType = response.headers.get("Content-Type") || track.media_type || "application/octet-stream";
  const blob = new Blob([await response.arrayBuffer()], { type: contentType });
  state.currentAudioUrl = URL.createObjectURL(blob);
  els.audio.src = state.currentAudioUrl;
  els.nowTitle.textContent = track.title;
  els.nowMeta.textContent = trackMeta(track);
  updateMediaSession(track);
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

async function togglePlayPause() {
  if (els.audio.src) {
    if (els.audio.paused) {
      await els.audio.play();
    } else {
      els.audio.pause();
    }
    return;
  }

  if (!state.queue.length && state.visibleTracks.length) {
    setQueueFromVisible(state.visibleTracks[0].id);
  }
  await playCurrentQueueTrack();
}

async function playOrStartQueue() {
  if (els.audio.src) {
    await els.audio.play();
    return;
  }

  if (!state.queue.length && state.visibleTracks.length) {
    setQueueFromVisible(state.visibleTracks[0].id);
  }
  await playCurrentQueueTrack();
}

function pausePlayback() {
  els.audio.pause();
}

function stopPlayback() {
  els.audio.pause();
  els.audio.currentTime = 0;
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

function updatePlaybackState() {
  if (!("mediaSession" in navigator)) return;
  navigator.mediaSession.playbackState = els.audio.paused ? "paused" : "playing";
}

function updateMediaSession(track) {
  if (!("mediaSession" in navigator)) return;
  if (typeof MediaMetadata !== "undefined") {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title || "Mekamb Music",
      artist: track.artist || "Nieznany artysta",
      album: track.album || "Nieznany album",
    });
  }
  updatePlaybackState();
}

function setupMediaSession() {
  if (!("mediaSession" in navigator)) return;
  const handlers = {
    play: () => runAction(playOrStartQueue),
    pause: pausePlayback,
    stop: stopPlayback,
    previoustrack: () => runAction(playPreviousTrack),
    nexttrack: () => runAction(playNextTrack),
  };

  Object.entries(handlers).forEach(([action, handler]) => {
    try {
      navigator.mediaSession.setActionHandler(action, handler);
    } catch {
      // Some desktop environments expose only part of the Media Session API.
    }
  });
}

function setupDesktopMediaControls() {
  if (!window.mekambDesktop?.onMediaCommand) return;
  window.mekambDesktop.onMediaCommand((command) => {
    const actions = {
      "play-pause": () => runAction(togglePlayPause),
      next: () => runAction(playNextTrack),
      previous: () => runAction(playPreviousTrack),
      stop: stopPlayback,
    };
    actions[command]?.();
  });
}

async function loadDesktopApiEndpoints() {
  const hasSavedEndpoints = Boolean(localStorage.getItem("mekambMusicApiEndpoints"));
  if (hasSavedEndpoints || !window.mekambDesktop?.getConfiguredApiEndpoints) return;

  const configuredEndpoints = parseApiEndpoints(
    (await window.mekambDesktop.getConfiguredApiEndpoints()).join("\n"),
  );
  if (!configuredEndpoints.length) return;

  state.apiEndpoints = configuredEndpoints;
  els.apiEndpointsInput.value = state.apiEndpoints.join("\n");
  localStorage.setItem("mekambMusicApiEndpoints", state.apiEndpoints.join("\n"));
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
  saveApiEndpoints();
  setApiBase("");
  state.token = els.tokenInput.value.trim();
  localStorage.setItem("mekambMusicToken", state.token);
  await refreshAll();
});

els.trackSearchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await runGlobalSearch();
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
els.audio.addEventListener("play", updatePlaybackState);
els.audio.addEventListener("pause", updatePlaybackState);

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

async function boot() {
  await loadDesktopApiEndpoints();
  setApiBase(state.apiBase);
  await refreshAll();
  startImportsAutoRefresh();
  updateTransport();
  setupMediaSession();
  setupDesktopMediaControls();
}

boot();
