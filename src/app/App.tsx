import { useState, useRef, useEffect, useMemo } from "react";
import {
  Search, Play, Pause, SkipBack, SkipForward,
  Volume2, Heart, Shuffle, Repeat,
  Music, Disc3, ListMusic, Clock, Settings, Key, X, Eye, EyeOff,
} from "lucide-react";

{/* MARKER-MAKE-KIT-INVOKED */}

declare global {
  interface Window {
    mekambDesktop?: {
      isDesktop: boolean;
      fetchApi(request: {
        url: string;
        method?: string;
        headers?: Record<string, string>;
        body?: BodyInit | null;
        timeoutMs?: number;
      }): Promise<{
        ok: boolean;
        status: number;
        statusText: string;
        headers: Record<string, string>;
        body: ArrayBuffer | null;
      }>;
      getConfiguredApiEndpoints(): Promise<string[]>;
      onMediaCommand(callback: (command: string) => void): () => void;
    };
  }
}

type ApiTrack = {
  id: string;
  title: string;
  artist: string | null;
  album: string | null;
  original_filename: string;
  media_type: string | null;
  duration_seconds: number | null;
  size_bytes: number;
  created_at: string;
};

type Track = {
  id: string;
  title: string;
  artist: string;
  album: string;
  duration: string;
  durationSeconds: number;
  liked: boolean;
  albumId: string;
  mediaType: string | null;
  originalFilename: string;
};

type Album = {
  id: string;
  title: string;
  artist: string;
  year: number;
  cover: string;
  coverTrackId: string | null;
  tracks: number;
  color: string;
};

type TorrentResult = {
  name: string;
  torrent_id: string;
  seeders: string;
  leechers: string;
  size_bytes: number;
  uploader: string;
};

type SearchMode = "library" | "torrent";

const ALBUMS = [
  { id: "demo-1", title: "Midnight Frequencies", artist: "Luna Vex", year: 2024, cover: "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=300&h=300&fit=crop&auto=format", tracks: 11, color: "#7c3aed" },
  { id: "demo-2", title: "Neon Requiem", artist: "Static Bloom", year: 2023, cover: "https://images.unsplash.com/photo-1644855640845-ab57a047320e?w=300&h=300&fit=crop&auto=format", tracks: 9, color: "#db2777" },
  { id: "demo-3", title: "Grains of Light", artist: "Pale Vessel", year: 2024, cover: "https://images.unsplash.com/photo-1629923759854-156b88c433aa?w=300&h=300&fit=crop&auto=format", tracks: 13, color: "#0891b2" },
  { id: "demo-4", title: "Stray Voltage", artist: "Coven Drift", year: 2022, cover: "https://images.unsplash.com/photo-1761814684971-fa0e7fd606e2?w=300&h=300&fit=crop&auto=format", tracks: 8, color: "#16a34a" },
  { id: "demo-5", title: "Hollow Hymns", artist: "Morrow Tide", year: 2023, cover: "https://images.unsplash.com/photo-1773430266140-ad5d57a83994?w=300&h=300&fit=crop&auto=format", tracks: 10, color: "#ea580c" },
  { id: "demo-6", title: "Ether Protocol", artist: "Zero Kelvin", year: 2024, cover: "https://images.unsplash.com/photo-1632667113863-24e85951b9d3?w=300&h=300&fit=crop&auto=format", tracks: 12, color: "#ca8a04" },
];

const LIBRARY_TRACKS: Track[] = [
  { id: "demo-track-1", title: "Obsidian Wave", artist: "Luna Vex", album: "Midnight Frequencies", duration: "3:47", durationSeconds: 247, liked: true, albumId: "demo-1", mediaType: null, originalFilename: "01 - Obsidian Wave.mp3" },
];

type Tab = "library" | "albums" | "liked" | "settings";

const SIDEBAR_ITEMS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "library", label: "Library", icon: <ListMusic size={16} /> },
  { id: "albums", label: "Albums", icon: <Disc3 size={16} /> },
  { id: "liked", label: "Liked", icon: <Heart size={16} /> },
  { id: "settings", label: "API Settings", icon: <Settings size={16} /> },
];

function normalizeEndpoint(endpoint: string) {
  return endpoint.trim().replace(/\/+$/, "");
}

function parseEndpoints(value: string) {
  const seen = new Set<string>();
  return value
    .split(/[,\n]/)
    .map(normalizeEndpoint)
    .filter(endpoint => {
      if (!endpoint || seen.has(endpoint)) return false;
      seen.add(endpoint);
      return true;
    });
}

function normalizeAlbumName(album: string) {
  return album.trim().replace(/\s+/g, " ") || "Nieznany album";
}

function albumKey(album: string) {
  return normalizeAlbumName(album).toLocaleLowerCase();
}

function primaryArtist(artist: string) {
  return artist
    .replace(/\s+(feat\.?|ft\.?|featuring)\s+.*$/i, "")
    .split(/\s*,\s*|\s+&\s+|\s+x\s+/i)[0]
    .trim() || artist;
}

function inferTrackNumber(track: Track) {
  const source = `${track.originalFilename || ""} ${track.title || ""}`;
  const match = source.match(/(?:^|[/\\\s._-])(?:cd|disc)?\s*0*(\d{1,3})(?:\s*[-._)]|\s+)/i);
  if (!match) return Number.MAX_SAFE_INTEGER;
  return Number(match[1]);
}

function sortAlbumTracks(tracks: Track[]) {
  return [...tracks].sort((left, right) => {
    const leftNumber = inferTrackNumber(left);
    const rightNumber = inferTrackNumber(right);
    if (leftNumber !== rightNumber) return leftNumber - rightNumber;
    return (left.originalFilename || left.title).localeCompare(right.originalFilename || right.title, undefined, {
      numeric: true,
      sensitivity: "base",
    });
  });
}

function formatDuration(seconds: number | null | undefined) {
  if (!seconds || seconds >= 8640000) return "0:00";
  const whole = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(whole / 60);
  const rest = String(whole % 60).padStart(2, "0");
  return `${minutes}:${rest}`;
}

function formatBytes(bytes: number | null | undefined) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function mapTrack(track: ApiTrack, likedIds: Set<string>): Track {
  const artist = track.artist || "Nieznany artysta";
  const album = track.album || "Nieznany album";
  return {
    id: track.id,
    title: track.title,
    artist,
    album,
    duration: formatDuration(track.duration_seconds),
    durationSeconds: track.duration_seconds || 0,
    liked: likedIds.has(track.id),
    albumId: albumKey(album),
    mediaType: track.media_type,
    originalFilename: track.original_filename || track.title,
  };
}

function buildAlbums(tracks: Track[]): Album[] {
  const groups = new Map<string, Album>();
  const artistCounts = new Map<string, Map<string, number>>();
  tracks.forEach(track => {
    if (!groups.has(track.albumId)) {
      const fallback = ALBUMS[groups.size % ALBUMS.length];
      groups.set(track.albumId, {
        id: track.albumId,
        title: normalizeAlbumName(track.album),
        artist: primaryArtist(track.artist),
        year: new Date().getFullYear(),
        cover: fallback.cover,
        coverTrackId: track.id,
        tracks: 0,
        color: fallback.color,
      });
      artistCounts.set(track.albumId, new Map());
    }
    const artist = primaryArtist(track.artist);
    const counts = artistCounts.get(track.albumId)!;
    counts.set(artist, (counts.get(artist) || 0) + 1);
    groups.get(track.albumId)!.tracks += 1;
  });
  return [...groups.values()]
    .map(album => {
      const counts = artistCounts.get(album.id);
      const artist = counts
        ? [...counts.entries()].sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))[0]?.[0]
        : album.artist;
      return { ...album, artist: artist || album.artist };
    })
    .sort((left, right) => left.title.localeCompare(right.title, undefined, { sensitivity: "base" }));
}

async function responseFromDesktop(url: string, options: RequestInit & { timeoutMs?: number }) {
  const result = await window.mekambDesktop!.fetchApi({
    url,
    method: options.method || "GET",
    headers: options.headers as Record<string, string>,
    body: options.body,
    timeoutMs: options.timeoutMs,
  });
  return new Response(result.body, {
    status: result.status,
    statusText: result.statusText,
    headers: result.headers,
  });
}

function TrackRow({
  track, index, isActive, isPlaying, isLiked, album, onPlay, onLike,
}: {
  track: Track; index: number; isActive: boolean; isPlaying: boolean; isLiked: boolean;
  album?: Album; onPlay: () => void; onLike: () => void;
}) {
  return (
    <div
      onClick={onPlay}
      className="grid items-center px-3 py-3 rounded-xl cursor-pointer transition-colors duration-150"
      style={{
        gridTemplateColumns: "2rem 1fr 1fr 3rem 3rem",
        background: isActive ? "var(--secondary)" : "transparent",
        border: isActive ? "1px solid var(--border)" : "1px solid transparent",
      }}
      onMouseEnter={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = "var(--secondary)"; }}
      onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = "transparent"; }}
    >
      <span style={{ fontSize: "0.8rem", color: isActive ? "var(--primary)" : "var(--muted-foreground)" }}>
        {isActive && isPlaying ? <Music size={14} style={{ color: "var(--primary)" }} /> : index + 1}
      </span>
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-9 h-9 rounded-lg shrink-0 overflow-hidden" style={{ background: album?.color ?? "var(--muted)" }}>
          <img src={album?.cover} alt={track.album} className="w-full h-full object-cover" />
        </div>
        <div className="min-w-0">
          <p className="truncate" style={{ fontSize: "0.875rem", fontWeight: 500, color: isActive ? "var(--primary)" : "var(--foreground)" }}>{track.title}</p>
          <p className="truncate" style={{ fontSize: "0.75rem", color: "var(--muted-foreground)" }}>{track.artist}</p>
        </div>
      </div>
      <span className="hidden sm:block truncate" style={{ fontSize: "0.8rem", color: "var(--muted-foreground)" }}>{track.album}</span>
      <span className="text-center" style={{ fontSize: "0.8rem", color: "var(--muted-foreground)" }}>{track.duration}</span>
      <div className="flex justify-end">
        <button onClick={e => { e.stopPropagation(); onLike(); }} className="p-1 rounded-md transition-colors duration-150" style={{ color: isLiked ? "var(--primary)" : "var(--muted-foreground)" }}>
          <Heart size={14} fill={isLiked ? "currentColor" : "none"} />
        </button>
      </div>
    </div>
  );
}

function AlbumCard({ album, onPlay }: { album: Album; onPlay: () => void }) {
  return (
    <div
      onClick={onPlay}
      className="flex flex-col gap-3 p-3 rounded-2xl cursor-pointer transition-colors duration-200 group"
      style={{ background: "var(--card)", border: "1px solid var(--border)" }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = "var(--primary)"; }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = "var(--border)"; }}
    >
      <div className="relative rounded-xl overflow-hidden aspect-square" style={{ background: album.color }}>
        <img src={album.cover} alt={album.title} className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" />
        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200" style={{ background: "rgba(0,0,0,0.45)" }}>
          <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background: "var(--primary)" }}>
            <Play size={16} fill="white" style={{ color: "white", marginLeft: "2px" }} />
          </div>
        </div>
      </div>
      <div className="min-w-0">
        <p className="truncate" style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--foreground)" }}>{album.title}</p>
        <p className="truncate" style={{ fontSize: "0.75rem", color: "var(--muted-foreground)" }}>{album.artist} · {album.year}</p>
        <p style={{ fontSize: "0.7rem", color: "var(--muted-foreground)", marginTop: "2px" }}>{album.tracks} tracks</p>
      </div>
    </div>
  );
}

function TorrentRow({
  result, index, isImporting, onImport,
}: {
  result: TorrentResult; index: number; isImporting: boolean; onImport: () => void;
}) {
  return (
    <div
      className="grid items-center px-3 py-3 rounded-xl transition-colors duration-150"
      style={{
        gridTemplateColumns: "2rem 1fr 5rem 5rem 6rem",
        background: "transparent",
        border: "1px solid transparent",
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--secondary)"; }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
    >
      <span style={{ fontSize: "0.8rem", color: "var(--muted-foreground)" }}>{index + 1}</span>
      <div className="min-w-0">
        <p className="truncate" style={{ fontSize: "0.875rem", fontWeight: 500, color: "var(--foreground)" }}>{result.name}</p>
        <p className="truncate" style={{ fontSize: "0.75rem", color: "var(--muted-foreground)" }}>{result.uploader} · {formatBytes(result.size_bytes)}</p>
      </div>
      <span className="text-center" style={{ fontSize: "0.8rem", color: "var(--muted-foreground)" }}>{result.seeders}</span>
      <span className="text-center" style={{ fontSize: "0.8rem", color: "var(--muted-foreground)" }}>{result.leechers}</span>
      <div className="flex justify-end">
        <button
          onClick={onImport}
          disabled={isImporting}
          className="px-3 py-1.5 rounded-lg transition-all duration-150 hover:opacity-90 active:scale-95"
          style={{ background: "var(--primary)", color: "white", fontSize: "0.75rem", fontWeight: 600, opacity: isImporting ? 0.6 : 1 }}
        >
          {isImporting ? "Importing" : "Import"}
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("library");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("library");
  const [torrentResults, setTorrentResults] = useState<TorrentResult[]>([]);
  const [torrentSearching, setTorrentSearching] = useState(false);
  const [importingTorrentIds, setImportingTorrentIds] = useState<Set<string>>(new Set());
  const [libraryTracks, setLibraryTracks] = useState<Track[]>([]);
  const [selectedAlbumId, setSelectedAlbumId] = useState<string | null>(null);
  const [albumCovers, setAlbumCovers] = useState<Record<string, string>>({});
  const [currentTrack, setCurrentTrack] = useState<Track | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [volume, setVolume] = useState(72);
  const [liked, setLiked] = useState<Set<string>>(new Set());
  const [shuffle, setShuffle] = useState(false);
  const [repeat, setRepeat] = useState(false);

  // API settings state
  const [apiKey, setApiKey] = useState(localStorage.getItem("mekambMusicToken") || "");
  const [apiEndpoint, setApiEndpoint] = useState(localStorage.getItem("mekambMusicApiEndpoints") || "https://api.music-service.io/v1");
  const [streamQuality, setStreamQuality] = useState<"low" | "medium" | "high" | "lossless">("high");
  const [showApiKey, setShowApiKey] = useState(false);
  const [apiSaved, setApiSaved] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const activeEndpointRef = useRef(localStorage.getItem("mekambMusicApiBase") || "");

  const albums = useMemo(() => buildAlbums(libraryTracks), [libraryTracks]);
  const albumsWithCovers = useMemo(
    () => albums.map(album => ({ ...album, cover: albumCovers[album.id] || album.cover })),
    [albums, albumCovers],
  );
  const albumById = useMemo(() => new Map(albumsWithCovers.map(album => [album.id, album])), [albumsWithCovers]);

  useEffect(() => {
    window.mekambDesktop?.getConfiguredApiEndpoints().then(endpoints => {
      if (!localStorage.getItem("mekambMusicApiEndpoints") && endpoints.length) {
        setApiEndpoint(endpoints.join(","));
      }
    });
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.volume = volume / 100;
  }, [volume]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onTimeUpdate = () => {
      const duration = audio.duration || currentTrack?.durationSeconds || 0;
      setProgress(duration ? (audio.currentTime / duration) * 100 : 0);
    };
    const onEnded = () => {
      if (repeat) {
        audio.currentTime = 0;
        audio.play();
        return;
      }
      skipNext();
    };
    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("ended", onEnded);
    return () => {
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("ended", onEnded);
    };
  }, [currentTrack, repeat, libraryTracks]);

  useEffect(() => {
    const unsubscribe = window.mekambDesktop?.onMediaCommand(command => {
      if (command === "play-pause") togglePlayPause();
      if (command === "next") skipNext();
      if (command === "previous") skipPrev();
      if (command === "stop") {
        audioRef.current?.pause();
        if (audioRef.current) audioRef.current.currentTime = 0;
        setIsPlaying(false);
      }
    });
    return () => unsubscribe?.();
  }, [currentTrack, libraryTracks, isPlaying]);

  useEffect(() => {
    if (!("mediaSession" in navigator) || !currentTrack) return;
    if (typeof MediaMetadata !== "undefined") {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: currentTrack.title,
        artist: currentTrack.artist,
        album: currentTrack.album,
      });
    }
    navigator.mediaSession.playbackState = isPlaying ? "playing" : "paused";
  }, [currentTrack, isPlaying]);

  const apiRequest = async (path: string, options: RequestInit & { timeoutMs?: number } = {}, allowRetry = true) => {
    const endpoints = parseEndpoints(apiEndpoint);
    const candidates = [activeEndpointRef.current, ...endpoints].filter(Boolean);
    const uniqueCandidates = [...new Set(candidates)];
    if (!uniqueCandidates.length) throw new Error("Missing API endpoint.");

    const headers = {
      ...(options.headers as Record<string, string> || {}),
      ...(path === "/health" ? {} : { Authorization: `Bearer ${apiKey}` }),
    };

    for (const endpoint of uniqueCandidates) {
      const url = new URL(path, endpoint).toString();
      try {
        const response = window.mekambDesktop?.fetchApi
          ? await responseFromDesktop(url, { ...options, headers })
          : await fetch(url, { ...options, headers });
        if (response.ok || !allowRetry || ![502, 503, 504].includes(response.status)) {
          activeEndpointRef.current = endpoint;
          localStorage.setItem("mekambMusicApiBase", endpoint);
          return response;
        }
      } catch (error) {
        if (!allowRetry) throw error;
      }
    }
    throw new Error("API unavailable.");
  };

  const apiJson = async <T,>(path: string, options?: RequestInit) => {
    const response = await apiRequest(path, options);
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
    if (response.status === 204) return null as T;
    return response.json() as Promise<T>;
  };

  const loadArtworkUrl = async (trackId: string) => {
    const response = await apiRequest(`/tracks/${trackId}/artwork`);
    if (!response.ok) throw new Error("Artwork unavailable.");
    return URL.createObjectURL(await response.blob());
  };

  const loadLibrary = async () => {
    if (!apiKey) return;
    const likedPayload = await apiJson<{ items: { track: ApiTrack }[] }>("/tracks/liked?limit=200");
    const likedIds = new Set(likedPayload.items.map(item => item.track.id));
    const params = new URLSearchParams({ limit: "200" });
    const payload = await apiJson<{ items: ApiTrack[] }>(`/tracks?${params}`);
    const tracks = payload.items.map(track => mapTrack(track, likedIds));
    setLiked(likedIds);
    setLibraryTracks(tracks);
    setCurrentTrack(current => current && tracks.some(track => track.id === current.id) ? current : tracks[0] || null);
  };

  const searchTorrents = async (query: string) => {
    const normalizedQuery = query.trim();
    if (!normalizedQuery || !apiKey) {
      setTorrentResults([]);
      return;
    }
    setTorrentSearching(true);
    try {
      const params = new URLSearchParams({ q: normalizedQuery });
      const payload = await apiJson<{ items: TorrentResult[] }>(`/sources/piratebay/search?${params}`);
      setTorrentResults(
        [...payload.items]
          .sort((left, right) => Number(right.seeders || 0) - Number(left.seeders || 0))
          .slice(0, 25),
      );
    } finally {
      setTorrentSearching(false);
    }
  };

  const importTorrent = async (torrentId: string) => {
    setImportingTorrentIds(previous => new Set(previous).add(torrentId));
    try {
      await apiJson(`/imports/piratebay/${encodeURIComponent(torrentId)}`, { method: "POST" });
    } finally {
      setImportingTorrentIds(previous => {
        const next = new Set(previous);
        next.delete(torrentId);
        return next;
      });
    }
  };

  useEffect(() => {
    loadLibrary().catch(() => undefined);
  }, []);

  useEffect(() => {
    if (searchMode !== "torrent") return;
    const timeout = window.setTimeout(() => {
      searchTorrents(searchQuery).catch(() => {
        setTorrentResults([]);
        setTorrentSearching(false);
      });
    }, 450);
    return () => window.clearTimeout(timeout);
  }, [searchMode, searchQuery, apiKey, apiEndpoint]);

  useEffect(() => {
    let canceled = false;
    const createdUrls: string[] = [];

    async function loadAlbumCovers() {
      const entries = await Promise.all(
        albums.map(async album => {
          if (!album.coverTrackId) return null;
          try {
            const url = await loadArtworkUrl(album.coverTrackId);
            createdUrls.push(url);
            return [album.id, url] as const;
          } catch {
            return null;
          }
        }),
      );
      if (canceled) {
        createdUrls.forEach(url => URL.revokeObjectURL(url));
        return;
      }
      setAlbumCovers(previous => {
        Object.values(previous).forEach(url => URL.revokeObjectURL(url));
        return Object.fromEntries(entries.filter(Boolean) as [string, string][]);
      });
    }

    if (albums.length && apiKey) loadAlbumCovers();

    return () => {
      canceled = true;
    };
  }, [albums.map(album => `${album.id}:${album.coverTrackId}`).join("|"), apiKey]);

  const filteredTracks = libraryTracks.filter(t =>
    t.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    t.artist.toLowerCase().includes(searchQuery.toLowerCase()) ||
    t.album.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredAlbums = albumsWithCovers.filter(a =>
    a.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    a.artist.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const playTrack = async (track: Track) => {
    setCurrentTrack(track);
    setProgress(0);
    const response = await apiRequest(`/tracks/${track.id}/stream`);
    if (!response.ok) throw new Error(`${response.status}: Stream unavailable.`);
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    const blob = new Blob([await response.arrayBuffer()], { type: response.headers.get("Content-Type") || track.mediaType || "application/octet-stream" });
    audioUrlRef.current = URL.createObjectURL(blob);
    if (audioRef.current) {
      audioRef.current.src = audioUrlRef.current;
      await audioRef.current.play();
    }
    setIsPlaying(true);
    apiJson(`/tracks/${track.id}/plays`, { method: "POST" }).catch(() => undefined);
  };

  const togglePlayPause = async () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (!audio.src && currentTrack) {
      await playTrack(currentTrack);
      return;
    }
    if (audio.paused) {
      await audio.play();
      setIsPlaying(true);
    } else {
      audio.pause();
      setIsPlaying(false);
    }
  };

  const skipNext = () => {
    const tracks = shuffle ? [...libraryTracks].sort(() => Math.random() - 0.5) : libraryTracks;
    const active = currentTrack || tracks[0];
    if (!active || !tracks.length) return;
    const idx = tracks.findIndex(t => t.id === active.id);
    playTrack(tracks[(idx + 1) % tracks.length]).catch(() => undefined);
  };

  const skipPrev = () => {
    const active = currentTrack || libraryTracks[0];
    if (!active || !libraryTracks.length) return;
    const idx = libraryTracks.findIndex(t => t.id === active.id);
    playTrack(libraryTracks[(idx - 1 + libraryTracks.length) % libraryTracks.length]).catch(() => undefined);
  };

  const toggleLike = (id: string) => {
    const nextLiked = new Set(liked);
    const willLike = !nextLiked.has(id);
    willLike ? nextLiked.add(id) : nextLiked.delete(id);
    setLiked(nextLiked);
    setLibraryTracks(tracks => tracks.map(track => track.id === id ? { ...track, liked: willLike } : track));
    apiJson(`/tracks/${id}/like`, { method: willLike ? "PUT" : "DELETE" }).catch(() => undefined);
  };

  const handleSaveApi = () => {
    localStorage.setItem("mekambMusicToken", apiKey);
    localStorage.setItem("mekambMusicApiEndpoints", apiEndpoint);
    activeEndpointRef.current = "";
    loadLibrary().catch(() => undefined);
    setApiSaved(true);
    setTimeout(() => setApiSaved(false), 2000);
  };

  const displayCurrentTrack = currentTrack || LIBRARY_TRACKS[0];
  const currentAlbum = albumById.get(displayCurrentTrack.albumId) || ALBUMS[0];
  const selectedAlbum = selectedAlbumId ? albumById.get(selectedAlbumId) : null;
  const selectedAlbumTracks = selectedAlbum ? sortAlbumTracks(libraryTracks.filter(track => track.albumId === selectedAlbum.id)) : [];

  const likedTracks = libraryTracks.filter(t => liked.has(t.id)).filter(t =>
    t.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    t.artist.toLowerCase().includes(searchQuery.toLowerCase()) ||
    t.album.toLowerCase().includes(searchQuery.toLowerCase())
  );
  const likedAlbums = albumsWithCovers.filter(a => new Set(likedTracks.map(t => t.albumId)).has(a.id)).filter(a =>
    a.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    a.artist.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const elapsedSeconds = Math.floor(progress / 100 * (displayCurrentTrack.durationSeconds || 0));

  return (
    <div className="size-full flex flex-col overflow-hidden" style={{ fontFamily: "'Inter', sans-serif", background: "var(--background)", color: "var(--foreground)" }}>
      <audio ref={audioRef} />

      {/* Body: sidebar + content */}
      <div className="flex flex-1 overflow-hidden min-h-0">

        {/* Sidebar */}
        <aside
          className="shrink-0 flex flex-col overflow-hidden"
          style={{ width: "200px", background: "var(--card)", borderRight: "1px solid var(--border)" }}
        >
          {/* Search */}
          <div className="px-3 pt-4 pb-3" style={{ borderBottom: "1px solid var(--border)" }}>
            <div className="grid grid-cols-2 gap-1 mb-2">
              {(["library", "torrent"] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => {
                    setSearchMode(mode);
                    if (mode === "torrent") setSelectedAlbumId(null);
                  }}
                  className="py-1.5 rounded-lg transition-colors duration-150"
                  style={{
                    background: searchMode === mode ? "var(--primary)" : "var(--input-background)",
                    color: searchMode === mode ? "white" : "var(--muted-foreground)",
                    border: "1px solid",
                    borderColor: searchMode === mode ? "var(--primary)" : "var(--border)",
                    fontSize: "0.72rem",
                    fontWeight: 600,
                    textTransform: "capitalize",
                  }}
                >
                  {mode === "library" ? "Library" : "Torrent"}
                </button>
              ))}
            </div>
            <div
              className="flex items-center gap-2 px-3 py-2 rounded-lg"
              style={{ background: "var(--input-background)", border: "1px solid var(--border)" }}
            >
              <Search size={13} style={{ color: "var(--muted-foreground)", flexShrink: 0 }} />
              <input
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder={searchMode === "library" ? "Search…" : "Search torrents…"}
                autoComplete="off"
                autoCorrect="off"
                spellCheck={false}
                className="flex-1 bg-transparent outline-none min-w-0 placeholder:opacity-40"
                style={{ color: "var(--foreground)", fontSize: "0.8rem" }}
              />
              {searchQuery && (
                <button onClick={() => setSearchQuery("")} style={{ color: "var(--muted-foreground)" }}>
                  <X size={12} />
                </button>
              )}
            </div>
          </div>

          {/* Nav items */}
          <nav className="flex flex-col gap-0.5 p-2 flex-1">
            {SIDEBAR_ITEMS.map(item => (
              <button
                key={item.id}
                onClick={() => {
                  setActiveTab(item.id);
                  if (item.id !== "albums") setSelectedAlbumId(null);
                }}
                className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-left w-full transition-colors duration-150"
                style={{
                  background: activeTab === item.id ? "var(--secondary)" : "transparent",
                  color: activeTab === item.id ? "var(--primary)" : "var(--muted-foreground)",
                  fontSize: "0.85rem",
                  fontWeight: activeTab === item.id ? 600 : 400,
                  borderLeft: activeTab === item.id ? "2px solid var(--primary)" : "2px solid transparent",
                }}
                onMouseEnter={e => { if (activeTab !== item.id) (e.currentTarget as HTMLElement).style.background = "var(--secondary)"; (e.currentTarget as HTMLElement).style.color = "var(--foreground)"; }}
                onMouseLeave={e => { if (activeTab !== item.id) { (e.currentTarget as HTMLElement).style.background = "transparent"; (e.currentTarget as HTMLElement).style.color = "var(--muted-foreground)"; } }}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto min-h-0 min-w-0 px-6 py-5" style={{ scrollbarWidth: "none" }}>

          {/* Torrent Search */}
          {searchMode === "torrent" && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 style={{ fontFamily: "'Outfit', sans-serif", fontSize: "1.1rem", fontWeight: 700 }}>
                  {searchQuery ? `Torrent results for "${searchQuery}"` : "Torrent Search"}
                </h2>
                <span style={{ fontSize: "0.75rem", color: "var(--muted-foreground)" }}>
                  {torrentSearching ? "Searching" : `${torrentResults.length} results`}
                </span>
              </div>
              <div className="grid items-center px-3 py-2 mb-1 rounded-lg" style={{ gridTemplateColumns: "2rem 1fr 5rem 5rem 6rem", fontSize: "0.7rem", color: "var(--muted-foreground)", letterSpacing: "0.08em", textTransform: "uppercase", fontWeight: 600 }}>
                <span>#</span><span>Title</span><span className="text-center">Seed</span><span className="text-center">Leech</span><span />
              </div>
              {searchQuery.trim() ? (
                <div className="flex flex-col gap-0.5">
                  {torrentResults.map((result, i) => (
                    <TorrentRow
                      key={result.torrent_id}
                      result={result}
                      index={i}
                      isImporting={importingTorrentIds.has(result.torrent_id)}
                      onImport={() => importTorrent(result.torrent_id).catch(() => undefined)}
                    />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 gap-3" style={{ color: "var(--muted-foreground)" }}>
                  <Search size={36} style={{ opacity: 0.3 }} />
                  <p style={{ fontSize: "0.875rem" }}>Search torrents to import music</p>
                </div>
              )}
            </div>
          )}

          {/* Library */}
          {searchMode === "library" && activeTab === "library" && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 style={{ fontFamily: "'Outfit', sans-serif", fontSize: "1.1rem", fontWeight: 700 }}>
                  {searchQuery ? `Results for "${searchQuery}"` : "Your Library"}
                </h2>
                <span style={{ fontSize: "0.75rem", color: "var(--muted-foreground)" }}>{filteredTracks.length} songs</span>
              </div>
              <div className="grid items-center px-3 py-2 mb-1 rounded-lg" style={{ gridTemplateColumns: "2rem 1fr 1fr 3rem 3rem", fontSize: "0.7rem", color: "var(--muted-foreground)", letterSpacing: "0.08em", textTransform: "uppercase", fontWeight: 600 }}>
                <span>#</span><span>Title</span><span className="hidden sm:block">Album</span>
                <span className="flex justify-center"><Clock size={12} /></span><span />
              </div>
              <div className="flex flex-col gap-0.5">
                {filteredTracks.map((track, i) => (
                  <TrackRow key={track.id} album={albumById.get(track.albumId)} track={track} index={i} isActive={track.id === currentTrack?.id} isPlaying={isPlaying} isLiked={liked.has(track.id)} onPlay={() => playTrack(track).catch(() => undefined)} onLike={() => toggleLike(track.id)} />
                ))}
              </div>
            </div>
          )}

          {/* Albums */}
          {searchMode === "library" && activeTab === "albums" && (
            <div>
              <div className="flex items-center justify-between mb-5">
                <h2 style={{ fontFamily: "'Outfit', sans-serif", fontSize: "1.1rem", fontWeight: 700 }}>
                  {selectedAlbum ? selectedAlbum.title : searchQuery ? `Results for "${searchQuery}"` : "Albums"}
                </h2>
                <span style={{ fontSize: "0.75rem", color: "var(--muted-foreground)" }}>
                  {selectedAlbum ? `${selectedAlbumTracks.length} songs` : `${filteredAlbums.length} albums`}
                </span>
              </div>
              {selectedAlbum ? (
                <div>
                  <div className="flex items-end gap-5 mb-5">
                    <div className="w-40 h-40 rounded-2xl overflow-hidden shrink-0" style={{ background: selectedAlbum.color, border: "1px solid var(--border)" }}>
                      <img src={selectedAlbum.cover} alt={selectedAlbum.title} className="w-full h-full object-cover" />
                    </div>
                    <div className="min-w-0 pb-1">
                      <button
                        onClick={() => setSelectedAlbumId(null)}
                        className="mb-3 px-3 py-1.5 rounded-lg transition-colors duration-150"
                        style={{ background: "var(--input-background)", color: "var(--muted-foreground)", fontSize: "0.75rem", border: "1px solid var(--border)" }}
                      >
                        Albums
                      </button>
                      <p className="truncate" style={{ fontSize: "0.75rem", color: "var(--muted-foreground)", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>Album</p>
                      <h3 className="truncate" style={{ fontFamily: "'Outfit', sans-serif", fontSize: "2rem", fontWeight: 700, color: "var(--foreground)" }}>{selectedAlbum.title}</h3>
                      <p className="truncate" style={{ fontSize: "0.875rem", color: "var(--muted-foreground)" }}>{selectedAlbum.artist} · {selectedAlbum.tracks} tracks</p>
                      <button
                        onClick={() => { const first = selectedAlbumTracks[0]; if (first) playTrack(first).catch(() => undefined); }}
                        className="mt-4 px-5 py-2.5 rounded-xl transition-all duration-150 hover:opacity-90 active:scale-95"
                        style={{ background: "var(--primary)", color: "white", fontSize: "0.875rem", fontWeight: 600 }}
                      >
                        Play Album
                      </button>
                    </div>
                  </div>
                  <div className="grid items-center px-3 py-2 mb-1 rounded-lg" style={{ gridTemplateColumns: "2rem 1fr 1fr 3rem 3rem", fontSize: "0.7rem", color: "var(--muted-foreground)", letterSpacing: "0.08em", textTransform: "uppercase", fontWeight: 600 }}>
                    <span>#</span><span>Title</span><span className="hidden sm:block">Album</span>
                    <span className="flex justify-center"><Clock size={12} /></span><span />
                  </div>
                  <div className="flex flex-col gap-0.5">
                    {selectedAlbumTracks.map((track, i) => (
                      <TrackRow key={track.id} album={albumById.get(track.albumId)} track={track} index={i} isActive={track.id === currentTrack?.id} isPlaying={isPlaying} isLiked={liked.has(track.id)} onPlay={() => playTrack(track).catch(() => undefined)} onLike={() => toggleLike(track.id)} />
                    ))}
                  </div>
                </div>
              ) : (
                <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))" }}>
                  {filteredAlbums.map(album => (
                    <AlbumCard key={album.id} album={album} onPlay={() => setSelectedAlbumId(album.id)} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Liked */}
          {searchMode === "library" && activeTab === "liked" && (
            <div className="flex flex-col gap-8">
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 style={{ fontFamily: "'Outfit', sans-serif", fontSize: "1.1rem", fontWeight: 700 }}>Liked Songs</h2>
                  <span style={{ fontSize: "0.75rem", color: "var(--muted-foreground)" }}>{likedTracks.length} songs</span>
                </div>
                {likedTracks.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 gap-3" style={{ color: "var(--muted-foreground)" }}>
                    <Heart size={36} style={{ opacity: 0.3 }} />
                    <p style={{ fontSize: "0.875rem" }}>No liked songs yet</p>
                  </div>
                ) : (
                  <div className="flex flex-col gap-0.5">
                    {likedTracks.map((track, i) => (
                      <TrackRow key={track.id} album={albumById.get(track.albumId)} track={track} index={i} isActive={track.id === currentTrack?.id} isPlaying={isPlaying} isLiked={liked.has(track.id)} onPlay={() => playTrack(track).catch(() => undefined)} onLike={() => toggleLike(track.id)} />
                    ))}
                  </div>
                )}
              </div>
              <div>
                <div className="flex items-center justify-between mb-5">
                  <h2 style={{ fontFamily: "'Outfit', sans-serif", fontSize: "1.1rem", fontWeight: 700 }}>Liked Albums</h2>
                  <span style={{ fontSize: "0.75rem", color: "var(--muted-foreground)" }}>{likedAlbums.length} albums</span>
                </div>
                {likedAlbums.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 gap-3" style={{ color: "var(--muted-foreground)" }}>
                    <Disc3 size={36} style={{ opacity: 0.3 }} />
                    <p style={{ fontSize: "0.875rem" }}>No liked albums yet</p>
                  </div>
                ) : (
                  <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))" }}>
                    {likedAlbums.map(album => (
                      <AlbumCard key={album.id} album={album} onPlay={() => { setActiveTab("albums"); setSelectedAlbumId(album.id); }} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* API Settings */}
          {searchMode === "library" && activeTab === "settings" && (
            <div className="max-w-lg">
              <div className="flex items-center gap-3 mb-6">
                <Key size={20} style={{ color: "var(--primary)" }} />
                <h2 style={{ fontFamily: "'Outfit', sans-serif", fontSize: "1.1rem", fontWeight: 700 }}>API Settings</h2>
              </div>

              <div className="flex flex-col gap-5">
                {/* API Key */}
                <div className="flex flex-col gap-2">
                  <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--muted-foreground)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                    API Key
                  </label>
                  <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl" style={{ background: "var(--input-background)", border: "1px solid var(--border)" }}>
                    <input
                      type={showApiKey ? "text" : "password"}
                      value={apiKey}
                      onChange={e => setApiKey(e.target.value)}
                      placeholder="sk-••••••••••••••••••••••"
                      autoComplete="off"
                      className="flex-1 bg-transparent outline-none placeholder:opacity-30 min-w-0"
                      style={{ color: "var(--foreground)", fontSize: "0.875rem", fontFamily: "monospace" }}
                    />
                    <button onClick={() => setShowApiKey(v => !v)} style={{ color: "var(--muted-foreground)", flexShrink: 0 }}>
                      {showApiKey ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                  <p style={{ fontSize: "0.72rem", color: "var(--muted-foreground)" }}>Your secret API key. Never share this publicly.</p>
                </div>

                {/* Endpoint */}
                <div className="flex flex-col gap-2">
                  <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--muted-foreground)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                    API Endpoint
                  </label>
                  <input
                    type="text"
                    value={apiEndpoint}
                    onChange={e => setApiEndpoint(e.target.value)}
                    autoComplete="off"
                    className="px-3 py-2.5 rounded-xl outline-none"
                    style={{ background: "var(--input-background)", border: "1px solid var(--border)", color: "var(--foreground)", fontSize: "0.875rem", fontFamily: "monospace" }}
                  />
                </div>

                {/* Stream Quality */}
                <div className="flex flex-col gap-2">
                  <label style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--muted-foreground)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                    Stream Quality
                  </label>
                  <div className="grid grid-cols-4 gap-2">
                    {(["low", "medium", "high", "lossless"] as const).map(q => (
                      <button
                        key={q}
                        onClick={() => setStreamQuality(q)}
                        className="py-2 rounded-lg transition-colors duration-150"
                        style={{
                          background: streamQuality === q ? "var(--primary)" : "var(--input-background)",
                          color: streamQuality === q ? "white" : "var(--muted-foreground)",
                          border: "1px solid",
                          borderColor: streamQuality === q ? "var(--primary)" : "var(--border)",
                          fontSize: "0.75rem",
                          fontWeight: 500,
                          textTransform: "capitalize",
                        }}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Divider */}
                <div style={{ height: "1px", background: "var(--border)" }} />

                {/* Save */}
                <div className="flex items-center gap-3">
                  <button
                    onClick={handleSaveApi}
                    className="px-5 py-2.5 rounded-xl transition-all duration-150 hover:opacity-90 active:scale-95"
                    style={{ background: "var(--primary)", color: "white", fontSize: "0.875rem", fontWeight: 600 }}
                  >
                    {apiSaved ? "Saved!" : "Save Settings"}
                  </button>
                  <button
                    onClick={() => { setApiKey(""); setApiEndpoint("https://api.music-service.io/v1"); setStreamQuality("high"); }}
                    className="px-5 py-2.5 rounded-xl transition-colors duration-150"
                    style={{ background: "var(--input-background)", color: "var(--muted-foreground)", fontSize: "0.875rem", border: "1px solid var(--border)" }}
                  >
                    Reset
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Playback Bar */}
      <footer className="shrink-0 px-6 py-4 flex flex-col gap-3" style={{ background: "var(--card)", borderTop: "1px solid var(--border)" }}>
        {/* Progress */}
        <div className="flex items-center gap-3">
          <span style={{ fontSize: "0.7rem", color: "var(--muted-foreground)", minWidth: "2.5rem", textAlign: "right" }}>
            {formatDuration(elapsedSeconds)}
          </span>
          <div
            className="flex-1 h-1 rounded-full relative cursor-pointer group"
            style={{ background: "var(--muted)" }}
            onClick={e => {
              const audio = audioRef.current;
              const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
              const nextProgress = ((e.clientX - r.left) / r.width) * 100;
              setProgress(nextProgress);
              if (audio?.duration) audio.currentTime = audio.duration * (nextProgress / 100);
            }}
          >
            <div className="h-full rounded-full" style={{ width: `${progress}%`, background: "var(--primary)" }} />
          </div>
          <span style={{ fontSize: "0.7rem", color: "var(--muted-foreground)", minWidth: "2.5rem" }}>{displayCurrentTrack.duration}</span>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          {/* Track info */}
          <div className="flex items-center gap-3 w-56 shrink-0">
            <div className="w-10 h-10 rounded-lg overflow-hidden shrink-0" style={{ background: currentAlbum?.color ?? "var(--muted)" }}>
              <img src={currentAlbum?.cover} alt={displayCurrentTrack.album} className="w-full h-full object-cover" />
            </div>
            <div className="min-w-0">
              <p className="truncate" style={{ fontSize: "0.8rem", fontWeight: 600 }}>{displayCurrentTrack.title}</p>
              <p className="truncate" style={{ fontSize: "0.7rem", color: "var(--muted-foreground)" }}>{displayCurrentTrack.artist}</p>
            </div>
            <button onClick={() => toggleLike(displayCurrentTrack.id)} style={{ color: liked.has(displayCurrentTrack.id) ? "var(--primary)" : "var(--muted-foreground)", flexShrink: 0 }}>
              <Heart size={15} fill={liked.has(displayCurrentTrack.id) ? "currentColor" : "none"} />
            </button>
          </div>

          {/* Playback */}
          <div className="flex-1 flex items-center justify-center gap-5">
            <button onClick={() => setShuffle(s => !s)} style={{ color: shuffle ? "var(--primary)" : "var(--muted-foreground)" }}><Shuffle size={16} /></button>
            <button onClick={skipPrev} className="hover:opacity-80" style={{ color: "var(--foreground)" }}><SkipBack size={20} fill="currentColor" /></button>
            <button
              onClick={() => togglePlayPause().catch(() => undefined)}
              className="w-10 h-10 rounded-full flex items-center justify-center transition-all duration-150 hover:scale-105 active:scale-95"
              style={{ background: "var(--primary)", color: "white" }}
            >
              {isPlaying ? <Pause size={18} fill="white" /> : <Play size={18} fill="white" style={{ marginLeft: "2px" }} />}
            </button>
            <button onClick={skipNext} className="hover:opacity-80" style={{ color: "var(--foreground)" }}><SkipForward size={20} fill="currentColor" /></button>
            <button onClick={() => setRepeat(r => !r)} style={{ color: repeat ? "var(--primary)" : "var(--muted-foreground)" }}><Repeat size={16} /></button>
          </div>

          {/* Volume */}
          <div className="flex items-center gap-2 w-40 shrink-0 justify-end">
            <Volume2 size={15} style={{ color: "var(--muted-foreground)" }} />
            <div
              className="flex-1 h-1 rounded-full cursor-pointer"
              style={{ background: "var(--muted)" }}
              onClick={e => { const r = (e.currentTarget as HTMLElement).getBoundingClientRect(); setVolume(Math.round(((e.clientX - r.left) / r.width) * 100)); }}
            >
              <div className="h-full rounded-full" style={{ width: `${volume}%`, background: "var(--primary)" }} />
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
