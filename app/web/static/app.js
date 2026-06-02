const state = {
  token: localStorage.getItem("mekambMusicToken") || "",
  apiEndpoints: readApiEndpoints(),
  apiBase: normalizeEndpoint(localStorage.getItem("mekambMusicApiBase") || ""),
  currentPage: "home",
  searchQuery: "",
  currentAudioUrl: null,
  currentTrack: null,
  artworkUrls: new Set(),
  importsTimer: null,
  searchTimer: null,
  saveTimer: null,
  visibleTracks: [],
  currentAlbums: [],
  queue: [],
  queueIndex: -1,
  shuffle: localStorage.getItem("mekambShuffle") === "true",
  loop: localStorage.getItem("mekambLoopMode") || "off",
  sidebarCollapsed: localStorage.getItem("mekambSidebarCollapsed") === "true",
  restoredTrackId: "",
  restoredPosition: 0,
};

const queueStatuses = ["queued", "downloading", "ready_to_import", "failed"];

const els = {
  tokenForm: document.querySelector("#tokenForm"),
  apiEndpointsInput: document.querySelector("#apiEndpointsInput"),
  apiBaseStatus: document.querySelector("#apiBaseStatus"),
  tokenInput: document.querySelector("#tokenInput"),
  sidebarToggle: document.querySelector("#sidebarToggle"),
  sidebarResizer: document.querySelector("#sidebarResizer"),
  trackSearchForm: document.querySelector("#trackSearchForm"),
  trackQuery: document.querySelector("#trackQuery"),
  tracksList: document.querySelector("#tracksList"),
  pageTitle: document.querySelector("#pageTitle"),
  pageSubtitle: document.querySelector("#pageSubtitle"),
  libraryPanel: document.querySelector("#libraryPanel"),
  sourceResults: document.querySelector("#sourceResults"),
  importsList: document.querySelector("#importsList"),
  refreshImports: document.querySelector("#refreshImports"),
  message: document.querySelector("#message"),
  audio: document.querySelector("#audio"),
  playPause: document.querySelector("#playPause"),
  prevTrack: document.querySelector("#prevTrack"),
  nextTrack: document.querySelector("#nextTrack"),
  shuffleToggle: document.querySelector("#shuffleToggle"),
  loopToggle: document.querySelector("#loopToggle"),
  seekBar: document.querySelector("#seekBar"),
  currentTime: document.querySelector("#currentTime"),
  durationTime: document.querySelector("#durationTime"),
  muteToggle: document.querySelector("#muteToggle"),
  volumeBar: document.querySelector("#volumeBar"),
  nowTitle: document.querySelector("#nowTitle"),
  nowMeta: document.querySelector("#nowMeta"),
  pageTabs: [...document.querySelectorAll(".nav-tab")],
};

els.tokenInput.value = state.token;
els.apiEndpointsInput.value = state.apiEndpoints.join("\n");

const iconPaths = {
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  play: '<path d="M8 5v14l11-7z"/>',
  pause: '<path d="M7 5h4v14H7zM13 5h4v14h-4z"/>',
  previous: '<path d="M6 5h2v14H6zM19 6v12L9 12z"/>',
  next: '<path d="M16 5h2v14h-2zM5 6v12l10-6z"/>',
  shuffle: '<path d="M16 3h5v5M4 7h3c2.2 0 3.6 1 5.1 3.1M21 3l-6.8 6.8M16 21h5v-5M4 17h3c2.2 0 3.6-1 5.1-3.1M21 21l-6.8-6.8"/>',
  loop: '<path d="M17 2l4 4-4 4M3 11V9a4 4 0 0 1 4-4h14M7 22l-4-4 4-4M21 13v2a4 4 0 0 1-4 4H3"/>',
  volume: '<path d="M4 9v6h4l5 4V5L8 9zM17 9.5a4 4 0 0 1 0 5M19.5 7a7.5 7.5 0 0 1 0 10"/>',
  muted: '<path d="M4 9v6h4l5 4V5L8 9zM18 9l4 4M22 9l-4 4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  heart: '<path d="M20.8 5.6a5.2 5.2 0 0 0-7.4 0L12 7l-1.4-1.4a5.2 5.2 0 0 0-7.4 7.4L12 21l8.8-8a5.2 5.2 0 0 0 0-7.4z"/>',
  back: '<path d="M19 12H5M12 19l-7-7 7-7"/>',
  search: '<path d="M10.5 18a7.5 7.5 0 1 1 5.3-2.2L21 21"/>',
};

function svgIcon(name) {
  return `<svg class="symbol" viewBox="0 0 24 24" aria-hidden="true">${iconPaths[name] || ""}</svg>`;
}

function setButtonIcon(button, name, label) {
  button.innerHTML = svgIcon(name);
  button.title = label;
  button.ariaLabel = label;
}

function hydrateStaticIcons() {
  setButtonIcon(els.sidebarToggle, "menu", state.sidebarCollapsed ? "Pokaż sidebar" : "Schowaj sidebar");
  setButtonIcon(els.prevTrack, "previous", "Poprzedni");
  setButtonIcon(els.nextTrack, "next", "Następny");
  setButtonIcon(els.shuffleToggle, "shuffle", "Shuffle");
  setButtonIcon(els.loopToggle, "loop", "Loop");
  updateTransport();
  updateVolumeControls();
}

function applySidebarState() {
  document.body.classList.toggle("sidebar-collapsed", state.sidebarCollapsed);
  localStorage.setItem("mekambSidebarCollapsed", String(state.sidebarCollapsed));
  setButtonIcon(els.sidebarToggle, "menu", state.sidebarCollapsed ? "Pokaż sidebar" : "Schowaj sidebar");
}

function restoreSidebarWidth() {
  const savedWidth = Number(localStorage.getItem("mekambSidebarWidth") || "0");
  if (savedWidth > 180) {
    document.documentElement.style.setProperty("--sidebar-width", `${savedWidth}px`);
  }
}

function setupSidebarResize() {
  restoreSidebarWidth();
  applySidebarState();
  els.sidebarResizer.addEventListener("pointerdown", (event) => {
    if (state.sidebarCollapsed) return;
    event.preventDefault();
    document.body.classList.add("resizing-sidebar");
    const startX = event.clientX;
    const currentWidth = document.querySelector(".sidebar").getBoundingClientRect().width;
    const onMove = (moveEvent) => {
      const nextWidth = Math.max(190, Math.min(420, currentWidth + moveEvent.clientX - startX));
      document.documentElement.style.setProperty("--sidebar-width", `${nextWidth}px`);
      localStorage.setItem("mekambSidebarWidth", String(Math.round(nextWidth)));
    };
    const onUp = () => {
      document.body.classList.remove("resizing-sidebar");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  });
}

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

function formatClock(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0:00";
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60).toString().padStart(2, "0");
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

function readPlaybackState() {
  try {
    return JSON.parse(localStorage.getItem("mekambPlaybackState") || "null") || {};
  } catch {
    return {};
  }
}

function savePlaybackState() {
  const track = state.currentTrack || state.queue[state.queueIndex];
  if (!track) return;
  const position = Number.isFinite(els.audio.currentTime) && els.audio.currentTime > 0
    ? els.audio.currentTime
    : state.restoredPosition;
  localStorage.setItem("mekambPlaybackState", JSON.stringify({
    trackId: track.id,
    position,
    queueIds: state.queue.map((item) => item.id),
    queueIndex: Math.max(0, state.queueIndex),
    shuffle: state.shuffle,
    loop: state.loop,
    volume: els.audio.volume,
    muted: els.audio.muted,
    updatedAt: Date.now(),
  }));
  localStorage.setItem("mekambContinueAlbumKey", albumKey(track));
  localStorage.setItem("mekambShuffle", String(state.shuffle));
  localStorage.setItem("mekambLoopMode", state.loop);
}

function schedulePlaybackSave() {
  if (state.saveTimer) return;
  state.saveTimer = window.setTimeout(() => {
    state.saveTimer = null;
    savePlaybackState();
  }, 800);
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
      const latestTime = Math.max(...sortedTracks.map((track) => Date.parse(track.created_at || "") || 0));
      return { ...group, artist: mostCommonArtist(sortedTracks), tracks: sortedTracks, latestTime };
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

function renderAlbumCard(group) {
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
  text.append(title, meta);

  const actions = document.createElement("div");
  actions.className = "actions";
  const play = document.createElement("button");
  play.className = "icon album-play";
  play.type = "button";
  setButtonIcon(play, "play", "Odtwórz album");
  play.addEventListener("click", (event) => runAction(async () => {
    event.stopPropagation();
    state.queue = [...group.tracks];
    state.queueIndex = 0;
    await playCurrentQueueTrack();
  }));
  actions.append(play);

  item.addEventListener("click", () => showAlbumDetail(group.key));
  item.append(cover, text, actions);
  return item;
}

function renderAlbumDetail(group) {
  clearArtworkUrls();
  setTracksListMode("tracks");
  els.pageTitle.textContent = group.album;
  els.pageSubtitle.textContent = `${group.artist} • ${group.tracks.length} utw.`;
  els.tracksList.innerHTML = "";
  els.tracksList.classList.remove("empty");

  const detail = document.createElement("section");
  detail.className = "album-detail";

  const cover = document.createElement("img");
  cover.className = "album-detail-cover";
  cover.alt = "";
  cover.src = placeholderArtwork();
  loadArtwork(cover, group.tracks[0].id);

  const info = document.createElement("div");
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = "Album";
  const title = document.createElement("h2");
  title.textContent = group.album;
  const meta = document.createElement("p");
  meta.className = "meta";
  meta.textContent = `${group.artist} • ${group.tracks.length} utw.`;
  const controls = document.createElement("div");
  controls.className = "detail-actions";
  const back = document.createElement("button");
  back.className = "quiet";
  back.type = "button";
  back.textContent = "Wróć";
  back.addEventListener("click", () => setPage("albums"));
  const play = document.createElement("button");
  play.className = "icon";
  play.type = "button";
  setButtonIcon(play, "play", "Odtwórz album");
  play.addEventListener("click", () => runAction(async () => {
    state.queue = [...group.tracks];
    state.queueIndex = 0;
    await playCurrentQueueTrack();
  }));
  controls.append(back, play);
  info.append(eyebrow, title, meta, controls);

  const trackList = document.createElement("div");
  trackList.className = "album-detail-tracks";
  group.tracks.forEach((track, index) => {
    const row = renderTrack(track);
    const number = document.createElement("span");
    number.className = "track-number";
    number.textContent = String(index + 1);
    row.prepend(number);
    trackList.appendChild(row);
  });

  detail.append(cover, info, trackList);
  els.tracksList.appendChild(detail);
}

function showAlbumDetail(key) {
  const group = state.currentAlbums.find((album) => album.key === key);
  if (!group) return;
  state.currentPage = "album";
  els.pageTabs.forEach((item) => item.classList.remove("active"));
  els.libraryPanel.classList.remove("hidden");
  renderAlbumDetail(group);
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
  setButtonIcon(play, "play", "Odtwórz");
  play.addEventListener("click", () => runAction(() => playFromVisibleQueue(track.id)));

  const add = document.createElement("button");
  add.className = "icon quiet";
  add.type = "button";
  setButtonIcon(add, "plus", "Dodaj do kolejki");
  add.addEventListener("click", () => {
    addToQueue(track);
    setMessage("Dodano do kolejki.");
  });

  const like = document.createElement("button");
  like.className = "icon quiet";
  like.type = "button";
  setButtonIcon(like, "heart", "Polub");
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
    await api("/health");
  } catch (error) {
    throw error;
  }
}

async function fetchTracks({ q = "", limit = 200 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (q) params.set("q", q);
  const payload = await api(`/tracks?${params}`);
  return payload.items;
}

async function findTracksForRestore(playbackState) {
  const tracks = await fetchTracks({ limit: 600 });
  const byId = new Map(tracks.map((track) => [track.id, track]));
  const queue = (playbackState.queueIds || [])
    .map((id) => byId.get(id))
    .filter(Boolean);
  const track = byId.get(playbackState.trackId) || queue[playbackState.queueIndex || 0] || null;
  if (track && !queue.some((item) => item.id === track.id)) queue.push(track);
  return { track, queue };
}

async function restorePlaybackState() {
  const playbackState = readPlaybackState();
  if (!playbackState.trackId || !state.token) return;
  const { track, queue } = await findTracksForRestore(playbackState);
  if (!track) return;

  state.queue = queue;
  const restoredIndex = queue.findIndex((item) => item.id === track.id);
  state.queueIndex = restoredIndex >= 0
    ? restoredIndex
    : Math.min(Number(playbackState.queueIndex || 0), Math.max(0, queue.length - 1));
  state.currentTrack = track;
  state.restoredTrackId = track.id;
  state.restoredPosition = Number(playbackState.position || 0);
  state.shuffle = Boolean(playbackState.shuffle);
  state.loop = playbackState.loop || "off";
  els.audio.volume = typeof playbackState.volume === "number" ? playbackState.volume : els.audio.volume;
  els.audio.muted = Boolean(playbackState.muted);
  els.nowTitle.textContent = track.title;
  els.nowMeta.textContent = trackMeta(track);
  updateTransport();
  els.currentTime.textContent = formatClock(state.restoredPosition);
  els.durationTime.textContent = formatClock(track.duration_seconds);
  els.seekBar.value = track.duration_seconds
    ? String(Math.round((state.restoredPosition / track.duration_seconds) * 1000))
    : "0";
  updateVolumeControls();
}

async function renderHome() {
  clearArtworkUrls();
  const query = state.searchQuery;
  const [tracks, recentPayload] = await Promise.all([
    fetchTracks({ q: query, limit: 200 }),
    api("/tracks/recent?limit=24").catch(() => ({ items: [] })),
  ]);
  state.visibleTracks = tracks;
  state.currentAlbums = groupTracksByAlbum(tracks);
  setTracksListMode("home");
  els.pageTitle.textContent = query ? `Wyniki dla "${query}"` : "Start";
  els.pageSubtitle.textContent = "Kontynuuj słuchanie i rekomendacje z biblioteki";
  els.tracksList.innerHTML = "";
  els.tracksList.classList.remove("empty");

  const continueKey = localStorage.getItem("mekambContinueAlbumKey") || "";
  const continueAlbum = state.currentAlbums.find((album) => album.key === continueKey);
  if (continueAlbum) {
    els.tracksList.appendChild(renderHomeSection("Kontynuuj słuchanie", [continueAlbum], renderWideAlbumCard));
  }

  const recentTracks = recentPayload.items.map((item) => item.track).filter(Boolean);
  if (recentTracks.length) {
    els.tracksList.appendChild(renderHomeSection("Ostatnio słuchane", recentTracks.slice(0, 8), renderTrack));
  }

  const recommendations = [...state.currentAlbums]
    .sort((left, right) => right.latestTime - left.latestTime)
    .slice(0, 10);
  els.tracksList.appendChild(
    renderHomeSection("Rekomendacje", recommendations, renderAlbumCard, "Brak albumów w bibliotece."),
  );
  return tracks.length;
}

function renderHomeSection(title, items, renderer, emptyText = "") {
  const section = document.createElement("section");
  section.className = "home-section";
  const heading = document.createElement("div");
  heading.className = "section-head";
  const h = document.createElement("h2");
  h.textContent = title;
  heading.appendChild(h);
  const content = document.createElement("div");
  content.className = renderer === renderTrack ? "list" : "home-row";
  if (items.length) {
    items.forEach((item) => content.appendChild(renderer(item)));
  } else {
    content.classList.add("empty");
    content.textContent = emptyText;
  }
  section.append(heading, content);
  return section;
}

function renderWideAlbumCard(group) {
  const card = renderAlbumCard(group);
  card.classList.add("wide-album-card");
  return card;
}

async function loadTracks() {
  if (state.currentPage === "home") return renderHome();

  clearArtworkUrls();
  const query = state.searchQuery;
  if (state.currentPage === "liked") {
    setTracksListMode("tracks");
    els.pageTitle.textContent = "Polubione";
    els.pageSubtitle.textContent = "Twoje zapisane utwory";
    const payload = await api("/tracks/liked?limit=200");
    state.visibleTracks = payload.items.map((item) => item.track);
    renderList(els.tracksList, state.visibleTracks, renderTrack, "Nie ma jeszcze polubionych utworów.");
    return state.visibleTracks.length;
  }

  state.visibleTracks = await fetchTracks({ q: query, limit: state.currentPage === "albums" ? 300 : 100 });
  state.currentAlbums = groupTracksByAlbum(state.visibleTracks);
  if (state.currentPage === "albums") {
    setTracksListMode("albums");
    els.pageTitle.textContent = query ? `Albumy dla "${query}"` : "Albumy";
    els.pageSubtitle.textContent = "Kliknij album, żeby otworzyć stronę albumu";
    renderList(els.tracksList, state.currentAlbums, renderAlbumCard, "Brak albumów dla tego wyszukiwania.");
    return state.visibleTracks.length;
  }

  setTracksListMode("tracks");
  els.pageTitle.textContent = query ? `Utwory dla "${query}"` : "Utwory";
  els.pageSubtitle.textContent = "Lista utworów w bibliotece";
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
  await loadImports();
  return record;
}

async function libraryHasQuery(query) {
  const params = new URLSearchParams({ q: query, limit: "1" });
  const payload = await api(`/tracks?${params}`);
  return payload.items.length > 0;
}

async function showTorrentSuggestions(query) {
  setMessage("Nie ma w bibliotece. Pokazuję sugestie torrentów.");
  const results = await searchTorrentSources(query);
  renderList(els.sourceResults, results, renderSourceResult, "Brak wyników.");
  if (!results.length) {
    setMessage("Nie ma w bibliotece i nie znalazłem wyniku w torrentach.", true);
    return;
  }
}

async function runGlobalSearch() {
  const query = els.trackQuery.value.trim();
  state.searchQuery = query;
  if (query && state.currentPage !== "tracks") {
    state.currentPage = "tracks";
    els.pageTabs.forEach((item) => item.classList.toggle("active", item.dataset.page === "tracks"));
    els.libraryPanel.classList.remove("hidden");
  }
  const renderedCount = await loadTracks();
  if (!query) {
    renderList(els.sourceResults, [], renderSourceResult, "Brak sugestii.");
    return;
  }

  if (renderedCount > 0 || await libraryHasQuery(query)) {
    setMessage("Znaleziono w bibliotece.");
    renderList(els.sourceResults, [], renderSourceResult, "Brak sugestii.");
    return;
  }

  await showTorrentSuggestions(query);
}

async function cancelImport(importId) {
  await api(`/imports/${encodeURIComponent(importId)}/cancel?delete_files=true`, { method: "POST" });
  setMessage("Import usunięty z kolejki.");
  await loadImports();
}

async function retryImport(importId) {
  await api(`/imports/${encodeURIComponent(importId)}/retry?delete_files=true`, { method: "POST" });
  setMessage("Import dodany ponownie.");
  await loadImports();
}

async function likeTrack(trackId) {
  await api(`/tracks/${trackId}/like`, { method: "PUT" });
  setMessage("Utwór polubiony.");
}

async function playTrack(track, options = {}) {
  const position = Number(options.position || 0);
  setMessage("Ładuję plik audio...");
  const response = await apiResponse(`/tracks/${track.id}/stream`);

  if (state.currentAudioUrl) {
    URL.revokeObjectURL(state.currentAudioUrl);
  }
  const contentType = response.headers.get("Content-Type") || track.media_type || "application/octet-stream";
  const blob = new Blob([await response.arrayBuffer()], { type: contentType });
  state.currentAudioUrl = URL.createObjectURL(blob);
  state.currentTrack = track;
  state.restoredTrackId = "";
  state.restoredPosition = 0;
  els.audio.src = state.currentAudioUrl;
  els.nowTitle.textContent = track.title;
  els.nowMeta.textContent = trackMeta(track);
  localStorage.setItem("mekambContinueAlbumKey", albumKey(track));
  updateMediaSession(track);
  await api(`/tracks/${track.id}/plays`, { method: "POST" });
  if (position > 0) {
    await new Promise((resolve) => {
      const applyPosition = () => {
        const duration = els.audio.duration || 0;
        els.audio.currentTime = duration > 0 ? Math.min(position, Math.max(0, duration - 0.5)) : position;
        resolve();
      };
      if (els.audio.readyState >= 1) {
        applyPosition();
      } else {
        els.audio.addEventListener("loadedmetadata", applyPosition, { once: true });
      }
    });
  }
  await els.audio.play();
  savePlaybackState();
  setMessage("");
}

function addToQueue(track) {
  state.queue.push(track);
  if (state.queueIndex === -1) state.queueIndex = 0;
  savePlaybackState();
}

function setQueueFromVisible(startTrackId) {
  const tracks = state.shuffle ? shuffled(state.visibleTracks) : [...state.visibleTracks];
  const selectedIndex = tracks.findIndex((track) => track.id === startTrackId);
  state.queue = tracks;
  state.queueIndex = selectedIndex >= 0 ? selectedIndex : 0;
  savePlaybackState();
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
  const position = track.id === state.restoredTrackId ? state.restoredPosition : 0;
  await playTrack(track, { position });
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
    localStorage.removeItem("mekambContinueAlbumKey");
    localStorage.removeItem("mekambPlaybackState");
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
  setButtonIcon(els.playPause, els.audio.paused ? "play" : "pause", els.audio.paused ? "Odtwórz" : "Pauza");
  setButtonIcon(els.loopToggle, "loop", state.loop === "one" ? "Loop utworu" : "Loop kolejki");
}

function updatePlaybackState() {
  updateTransport();
  if (!("mediaSession" in navigator)) return;
  navigator.mediaSession.playbackState = els.audio.paused ? "paused" : "playing";
}

function updatePlayerProgress() {
  const duration = els.audio.duration || 0;
  const current = els.audio.currentTime || 0;
  els.currentTime.textContent = formatClock(current);
  els.durationTime.textContent = formatClock(duration);
  els.seekBar.value = duration ? String(Math.round((current / duration) * 1000)) : "0";
  els.seekBar.style.setProperty("--progress", `${duration ? (current / duration) * 100 : 0}%`);
}

function updateVolumeControls() {
  els.volumeBar.value = String(els.audio.volume);
  els.volumeBar.style.setProperty("--progress", `${els.audio.volume * 100}%`);
  setButtonIcon(els.muteToggle, els.audio.muted || els.audio.volume === 0 ? "muted" : "volume", "Głośność");
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
    await Promise.all([loadTracks(), loadImports()]);
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
      await loadImports();
    } catch {
      // Manual refresh will show any persistent error.
    }
  }, 5000);
}

async function setPage(page) {
  window.clearTimeout(state.searchTimer);
  state.currentPage = page;
  state.searchQuery = "";
  els.trackQuery.value = "";
  renderList(els.sourceResults, [], renderSourceResult, "Brak sugestii.");
  els.pageTabs.forEach((item) => item.classList.toggle("active", item.dataset.page === page));
  els.libraryPanel.classList.remove("hidden");
  await loadTracks();
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

els.trackQuery.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "a") {
    event.preventDefault();
    els.trackQuery.select();
  }
});

els.trackQuery.addEventListener("input", () => {
  window.clearTimeout(state.searchTimer);
  const query = els.trackQuery.value.trim();
  if (!query) {
    state.searchQuery = "";
    renderList(els.sourceResults, [], renderSourceResult, "Brak sugestii.");
    state.searchTimer = window.setTimeout(() => runAction(loadTracks), 120);
    return;
  }
  if (query.length < 3) return;
  state.searchTimer = window.setTimeout(() => runAction(runGlobalSearch), 650);
});

els.refreshImports.addEventListener("click", async () => {
  try {
    await loadImports();
  } catch (error) {
    setMessage(error.message, true);
  }
});

els.sidebarToggle.addEventListener("click", () => {
  state.sidebarCollapsed = !state.sidebarCollapsed;
  applySidebarState();
});

els.nextTrack.addEventListener("click", () => runAction(playNextTrack));
els.prevTrack.addEventListener("click", () => runAction(playPreviousTrack));
els.playPause.addEventListener("click", () => runAction(togglePlayPause));
els.audio.addEventListener("ended", () => runAction(playNextTrack));
els.audio.addEventListener("play", updatePlaybackState);
els.audio.addEventListener("pause", updatePlaybackState);
els.audio.addEventListener("timeupdate", updatePlayerProgress);
els.audio.addEventListener("timeupdate", schedulePlaybackSave);
els.audio.addEventListener("loadedmetadata", updatePlayerProgress);
els.audio.addEventListener("durationchange", updatePlayerProgress);
els.audio.addEventListener("volumechange", updateVolumeControls);
els.audio.addEventListener("volumechange", schedulePlaybackSave);

els.seekBar.addEventListener("input", () => {
  const duration = els.audio.duration || 0;
  if (!duration) return;
  els.audio.currentTime = (Number(els.seekBar.value) / 1000) * duration;
  updatePlayerProgress();
});

els.volumeBar.addEventListener("input", () => {
  els.audio.volume = Number(els.volumeBar.value);
  els.audio.muted = els.audio.volume === 0;
  updateVolumeControls();
});

els.muteToggle.addEventListener("click", () => {
  els.audio.muted = !els.audio.muted;
  updateVolumeControls();
});

els.shuffleToggle.addEventListener("click", () => {
  state.shuffle = !state.shuffle;
  updateTransport();
  savePlaybackState();
  setMessage(state.shuffle ? "Shuffle włączony." : "Shuffle wyłączony.");
});

els.loopToggle.addEventListener("click", () => {
  state.loop = state.loop === "off" ? "all" : state.loop === "all" ? "one" : "off";
  updateTransport();
  savePlaybackState();
  setMessage(state.loop === "off" ? "Loop wyłączony." : `Loop ${state.loop === "one" ? "utworu" : "kolejki"}.`);
});

els.pageTabs.forEach((tab) => {
  tab.addEventListener("click", async () => {
    try {
      await setPage(tab.dataset.page);
    } catch (error) {
      setMessage(error.message, true);
    }
  });
});

window.addEventListener("beforeunload", savePlaybackState);

async function boot() {
  setupSidebarResize();
  hydrateStaticIcons();
  await loadDesktopApiEndpoints();
  setApiBase(state.apiBase);
  await refreshAll();
  try {
    await restorePlaybackState();
  } catch {
    // Normal library loading will still work if the saved track no longer exists.
  }
  startImportsAutoRefresh();
  updateTransport();
  updatePlayerProgress();
  updateVolumeControls();
  setupMediaSession();
  setupDesktopMediaControls();
}

boot();
