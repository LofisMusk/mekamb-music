"""
Collaborative filtering worker — buduje globalna, cross-userowa tabele sasiadow
trackow (track_neighbors) na podstawie session-based item-item co-occurrence.

Algorytm (item-item co-occurrence, cross-user):
1. Wczytaj WSZYSTKIE wiersze TrackPlay (wszystkie api_key_id), posortowane po
   (api_key_id, played_at).
2. Pogrupuj po api_key_id, potem podziel plays kazdego uzytkownika na sesje —
   nowa sesja gdy przerwa miedzy kolejnymi played_at przekracza
   collaborative_session_gap_minutes. Kazda sesja przyciety do
   collaborative_max_session_tracks.
3. Dla kazdej sesji zliczaj co-occurrence tylko dla par w oknie przesuwnym
   collaborative_cooccurrence_window (symetrycznie). Pary z ROZNYCH uzytkownikow
   akumuluja sie do JEDNEGO wspoldzielonego pair_counts — to czyni sygnal
   cross-userowym.
4. Dodaj bonus za co-like: pary trackow polubione przez tego samego uzytkownika.
5. track_totals[a] = liczba wszystkich plays tracka a (wszyscy uzytkownicy).
6. neighbor_score(a,b) = pair_counts[(a,b)] / sqrt(total[a] * total[b]).
7. Zostaw top collaborative_top_k sasiadow per track.
8. W JEDNEJ transakcji: DELETE wszystkich TrackNeighbor, potem bulk-insert nowych.

Uruchamiany jako background asyncio task w FastAPI (run_collaborative_recompute_loop),
lub standalone: python -m app.workers.collaborative_filtering_worker
"""
from __future__ import annotations

import asyncio
import logging
import math
from collections import defaultdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select

from app.core.config import settings
from app.db.models import LikedTrack, TrackNeighbor, TrackPlay, utcnow
from app.db.session import AsyncSessionLocal, init_db

logger = logging.getLogger(__name__)


# ── Pure, DB-free helpers (unit-testable without a session) ──────────────────


def _split_sessions(
    plays: list[tuple[UUID, datetime]],
    *,
    gap_minutes: int,
    max_len: int,
) -> list[list[UUID]]:
    """Split one user's time-ordered plays into sessions.

    ``plays`` is a list of ``(track_id, played_at)`` already ordered by
    ``played_at``. A new session starts whenever the gap between consecutive
    plays exceeds ``gap_minutes``. Each session is truncated (first ``max_len``
    tracks kept) so a pathologically long session can't blow up pair counting.
    """
    sessions: list[list[UUID]] = []
    current: list[tuple[UUID, datetime]] = []
    gap = gap_minutes * 60.0
    previous_at: datetime | None = None
    for track_id, played_at in plays:
        if previous_at is not None:
            delta = (played_at - previous_at).total_seconds()
            if delta > gap:
                sessions.append([tid for tid, _ in current])
                current = []
        current.append((track_id, played_at))
        previous_at = played_at
    if current:
        sessions.append([tid for tid, _ in current])
    # Truncate over-long sessions to the first ``max_len`` tracks.
    return [session[:max_len] for session in sessions if session]


def _count_pairs(
    sessions: list[list[UUID]],
    *,
    window: int,
    pair_counts: defaultdict[tuple[UUID, UUID], float] | None = None,
) -> defaultdict[tuple[UUID, UUID], float]:
    """Accumulate symmetric co-occurrence counts within a sliding ``window``.

    Only pairs whose index distance is ``<= window`` are counted (so a whole
    multi-hour session doesn't dilute the signal). Both ``(a, b)`` and
    ``(b, a)`` are incremented so the resulting map is symmetric. Self-pairs
    (a == b) are skipped.

    Pass an existing ``pair_counts`` to keep aggregating across many callers —
    which is exactly how counts from DIFFERENT users end up in one shared map.
    """
    if pair_counts is None:
        pair_counts = defaultdict(float)
    for session in sessions:
        length = len(session)
        for i in range(length):
            a = session[i]
            upper = min(length, i + window + 1)
            for j in range(i + 1, upper):
                b = session[j]
                if a == b:
                    continue
                pair_counts[(a, b)] += 1.0
                pair_counts[(b, a)] += 1.0
    return pair_counts


def _add_like_cooccurrence(
    likes_by_user: dict[str, list[UUID]],
    *,
    bonus: float,
    max_likes: int,
    pair_counts: defaultdict[tuple[UUID, UUID], float],
) -> None:
    """Add a same-user co-like bonus for every unordered pair of a user's likes.

    Bounded to avoid an O(likes^2) blowup: a user with more than ``max_likes``
    likes has the list truncated to the first ``max_likes`` entries before
    pairing (chosen == ``collaborative_max_session_tracks`` for consistency with
    session capping). Symmetric; self-pairs skipped.
    """
    for track_ids in likes_by_user.values():
        capped = track_ids[:max_likes]
        length = len(capped)
        for i in range(length):
            a = capped[i]
            for j in range(i + 1, length):
                b = capped[j]
                if a == b:
                    continue
                pair_counts[(a, b)] += bonus
                pair_counts[(b, a)] += bonus


def _normalize_neighbors(
    pair_counts: dict[tuple[UUID, UUID], float],
    track_totals: dict[UUID, int],
    *,
    top_k: int,
) -> dict[UUID, list[tuple[UUID, float, float]]]:
    """Popularity-normalize pair counts and keep the top-K neighbors per track.

    Returns ``{track_id: [(neighbor_id, score, co_play_count), ...]}`` with each
    list sorted by score descending and truncated to ``top_k``. The denominator
    ``sqrt(total[a] * total[b])`` is guarded against zero/missing totals.
    """
    grouped: defaultdict[UUID, list[tuple[UUID, float, float]]] = defaultdict(list)
    for (a, b), count in pair_counts.items():
        if count <= 0:
            continue
        total_a = track_totals.get(a, 0)
        total_b = track_totals.get(b, 0)
        denominator = math.sqrt(total_a * total_b)
        if denominator <= 0:
            # A track appearing in pair_counts should have >=1 play, but guard
            # anyway (e.g. counts sourced purely from likes with no plays).
            continue
        score = count / denominator
        grouped[a].append((b, score, count))

    result: dict[UUID, list[tuple[UUID, float, float]]] = {}
    for track_id, neighbors in grouped.items():
        neighbors.sort(key=lambda item: item[1], reverse=True)
        result[track_id] = neighbors[:top_k]
    return result


# ── DB-driven orchestration ──────────────────────────────────────────────────


async def run_collaborative_recompute_once() -> dict[str, int]:
    """Full recompute + replace of the global track_neighbors table."""
    async with AsyncSessionLocal() as session:
        # 1. All plays across all users, ordered by (api_key_id, played_at).
        #    (Composite index ix_track_plays_api_key_id_played_at from 0007 helps,
        #    but we also order in Python defensively.)
        play_rows = list(
            await session.execute(
                select(TrackPlay.api_key_id, TrackPlay.track_id, TrackPlay.played_at)
                .order_by(TrackPlay.api_key_id, TrackPlay.played_at)
            )
        )

        # 2. Group by user, split into sessions.
        plays_by_user: defaultdict[str, list[tuple[UUID, datetime]]] = defaultdict(list)
        for api_key_id, track_id, played_at in play_rows:
            plays_by_user[api_key_id].append((track_id, played_at))

        pair_counts: defaultdict[tuple[UUID, UUID], float] = defaultdict(float)
        sessions_scanned = 0
        for user_plays in plays_by_user.values():
            user_plays.sort(key=lambda item: item[1])
            sessions = _split_sessions(
                user_plays,
                gap_minutes=settings.collaborative_session_gap_minutes,
                max_len=settings.collaborative_max_session_tracks,
            )
            sessions_scanned += len(sessions)
            # 3. Cross-user aggregation: pairs from every user's session land in
            #    the SAME shared pair_counts dict.
            _count_pairs(
                sessions,
                window=settings.collaborative_cooccurrence_window,
                pair_counts=pair_counts,
            )

        # 4. Same-user co-like bonus.
        like_rows = list(
            await session.execute(select(LikedTrack.api_key_id, LikedTrack.track_id))
        )
        likes_by_user: defaultdict[str, list[UUID]] = defaultdict(list)
        for api_key_id, track_id in like_rows:
            likes_by_user[api_key_id].append(track_id)
        _add_like_cooccurrence(
            likes_by_user,
            bonus=settings.collaborative_like_cooccurrence_bonus,
            max_likes=settings.collaborative_max_session_tracks,
            pair_counts=pair_counts,
        )

        # 5. Global per-track play totals.
        total_rows = list(
            await session.execute(
                select(TrackPlay.track_id, func.count(TrackPlay.id)).group_by(
                    TrackPlay.track_id
                )
            )
        )
        track_totals: dict[UUID, int] = {track_id: int(total) for track_id, total in total_rows}

        # 6 + 7. Normalize by popularity, keep top-K per track.
        neighbors_by_track = _normalize_neighbors(
            pair_counts,
            track_totals,
            top_k=settings.collaborative_top_k,
        )

        # 8. Replace the whole table in one transaction (delete + bulk insert),
        #    so a rerun REPLACES rather than ACCUMULATES rows.
        await session.execute(delete(TrackNeighbor))
        computed_at = utcnow()
        pairs_written = 0
        for track_id, neighbors in neighbors_by_track.items():
            for neighbor_id, score, co_play_count in neighbors:
                session.add(
                    TrackNeighbor(
                        track_id=track_id,
                        neighbor_track_id=neighbor_id,
                        score=float(score),
                        co_play_count=int(co_play_count),
                        computed_at=computed_at,
                    )
                )
                pairs_written += 1

        await session.commit()

    stats = {
        "tracks_with_neighbors": len(neighbors_by_track),
        "pairs_written": pairs_written,
        "sessions_scanned": sessions_scanned,
    }
    logger.info("Collaborative filtering worker: %s", stats)
    return stats


async def run_collaborative_recompute_loop() -> None:
    """Nieskończona pętla — uruchamiana jako FastAPI background task."""
    while True:
        await asyncio.sleep(settings.collaborative_recompute_interval_seconds)
        try:
            stats = await run_collaborative_recompute_once()
            logger.info("Collaborative recompute loop stats: %s", stats)
        except Exception as exc:
            logger.error("Collaborative filtering worker loop error: %s", exc, exc_info=True)


async def _main() -> None:
    await init_db()
    stats = await run_collaborative_recompute_once()
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
