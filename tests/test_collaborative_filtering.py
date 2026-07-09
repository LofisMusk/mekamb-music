from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.db.models import LikedTrack, TrackNeighbor, TrackPlay
from app.workers import collaborative_filtering_worker as cf
from app.workers.collaborative_filtering_worker import (
    _add_like_cooccurrence,
    _count_pairs,
    _normalize_neighbors,
    _split_sessions,
)


def _at(minutes: float) -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minutes)


# ── Pure helper tests ────────────────────────────────────────────────────────


def test_session_split_breaks_on_gap():
    a, b, c, d = uuid4(), uuid4(), uuid4(), uuid4()
    plays = [(a, _at(0)), (b, _at(5)), (c, _at(45)), (d, _at(50))]

    sessions = _split_sessions(plays, gap_minutes=30, max_len=200)

    assert sessions == [[a, b], [c, d]]


def test_session_split_respects_max_length():
    ids = [uuid4() for _ in range(6)]
    plays = [(tid, _at(i)) for i, tid in enumerate(ids)]

    sessions = _split_sessions(plays, gap_minutes=30, max_len=3)

    assert sessions == [ids[:3]]


def test_pair_counts_use_sliding_window_not_full_session():
    ids = [uuid4() for _ in range(5)]
    session = [list(ids)]

    counts = _count_pairs(session, window=3)

    # Within window (distance 2): track[0] & track[2] counted.
    assert counts[(ids[0], ids[2])] == 1.0
    assert counts[(ids[2], ids[0])] == 1.0
    # Outside window (distance 4): track[0] & track[4] NOT counted.
    assert counts[(ids[0], ids[4])] == 0.0
    # Distance 3 (== window) is included.
    assert counts[(ids[0], ids[3])] == 1.0


def test_pair_counts_accumulate_into_shared_map():
    a, b = uuid4(), uuid4()
    shared: defaultdict[tuple[UUID, UUID], float] = defaultdict(float)
    _count_pairs([[a, b]], window=3, pair_counts=shared)
    _count_pairs([[a, b]], window=3, pair_counts=shared)

    assert shared[(a, b)] == 2.0
    assert shared[(b, a)] == 2.0


def test_neighbor_score_normalizes_by_popularity():
    mega = uuid4()  # played 1000x
    other = uuid4()  # played 1000x, co-occurs once with mega
    mid_a = uuid4()  # played 5x
    mid_b = uuid4()  # played 5x, co-occurs 4x with mid_a

    pair_counts = {
        (mega, other): 1.0,
        (other, mega): 1.0,
        (mid_a, mid_b): 4.0,
        (mid_b, mid_a): 4.0,
    }
    track_totals = {mega: 1000, other: 1000, mid_a: 5, mid_b: 5}

    result = _normalize_neighbors(pair_counts, track_totals, top_k=30)

    mega_score = result[mega][0][1]
    mid_score = result[mid_a][0][1]
    assert mid_score > mega_score


def test_top_k_enforced():
    seed = uuid4()
    neighbors = [uuid4() for _ in range(50)]
    pair_counts: dict[tuple[UUID, UUID], float] = {}
    track_totals: dict[UUID, int] = {seed: 100}
    for i, nid in enumerate(neighbors):
        pair_counts[(seed, nid)] = float(i + 1)
        track_totals[nid] = 1

    result = _normalize_neighbors(pair_counts, track_totals, top_k=30)

    assert len(result[seed]) == 30
    # Kept the highest-count neighbors (score is monotonic in count here since
    # every neighbor total is 1 and seed total is constant).
    kept_counts = {co for _, _, co in result[seed]}
    assert kept_counts == {float(c) for c in range(21, 51)}


def test_like_cooccurrence_bonus_is_bounded_and_symmetric():
    a, b, c = uuid4(), uuid4(), uuid4()
    pair_counts: defaultdict[tuple[UUID, UUID], float] = defaultdict(float)

    _add_like_cooccurrence(
        {"alice": [a, b, c]},
        bonus=0.5,
        max_likes=2,  # cap -> only a,b paired
        pair_counts=pair_counts,
    )

    assert pair_counts[(a, b)] == 0.5
    assert pair_counts[(b, a)] == 0.5
    # c was truncated away by the cap.
    assert pair_counts[(a, c)] == 0.0


# ── DB-driven once-function tests (fake session, matching repo convention) ────


class FakeCollabSession:
    """Mimics the exact query shapes ``run_collaborative_recompute_once`` issues:
    a select over (api_key_id, track_id, played_at); a select over
    (api_key_id, track_id) for likes; a grouped count of plays per track; a
    ``delete(TrackNeighbor)``; and ``add`` of new TrackNeighbor rows.

    Matches the fake-session convention used by the engine/worker tests — no
    real database required.
    """

    def __init__(self, plays: list[TrackPlay], likes: list[LikedTrack]):
        self.plays = plays
        self.likes = likes
        self.neighbors: list[TrackNeighbor] = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        text = str(stmt)
        # DELETE FROM track_neighbors
        if text.strip().upper().startswith("DELETE"):
            self.neighbors.clear()
            return None
        if "track_plays" in text and "count" in text.lower():
            totals: defaultdict[UUID, int] = defaultdict(int)
            for play in self.plays:
                totals[play.track_id] += 1
            return [(track_id, count) for track_id, count in totals.items()]
        if "liked_tracks" in text:
            return [(like.api_key_id, like.track_id) for like in self.likes]
        # Default: the plays select (api_key_id, track_id, played_at)
        return [(p.api_key_id, p.track_id, p.played_at) for p in self.plays]

    def add(self, item):
        if isinstance(item, TrackNeighbor):
            self.neighbors.append(item)

    async def commit(self):
        self.commits += 1


def _play(api_key_id: str, track_id: UUID, at: datetime) -> TrackPlay:
    return TrackPlay(
        id=uuid4(),
        api_key_id=api_key_id,
        track_id=track_id,
        played_at=at,
        completed=True,
        source="api",
    )


@pytest.fixture
def patch_session(monkeypatch: pytest.MonkeyPatch):
    def _apply(session: FakeCollabSession) -> FakeCollabSession:
        monkeypatch.setattr(cf, "AsyncSessionLocal", lambda: session)
        return session

    return _apply


@pytest.mark.asyncio
async def test_run_collaborative_recompute_once_replaces_not_accumulates(patch_session):
    x, y = uuid4(), uuid4()
    plays = [
        _play("alice", x, _at(0)),
        _play("alice", y, _at(2)),
    ]
    session = FakeCollabSession(plays, [])
    patch_session(session)

    first = await cf.run_collaborative_recompute_once()
    count_after_first = len(session.neighbors)
    second = await cf.run_collaborative_recompute_once()
    count_after_second = len(session.neighbors)

    assert first["pairs_written"] > 0
    assert count_after_first == count_after_second == second["pairs_written"]
    assert session.commits == 2


@pytest.mark.asyncio
async def test_cross_user_cooccurrence_counted_regardless_of_api_key_id(patch_session):
    x, y = uuid4(), uuid4()

    # Case 1: only Alice plays the pair.
    single = FakeCollabSession(
        [_play("alice", x, _at(0)), _play("alice", y, _at(1))],
        [],
    )
    patch_session(single)
    await cf.run_collaborative_recompute_once()
    single_neighbor = next(n for n in single.neighbors if n.track_id == x)

    # Case 2: Alice AND Bob each play the same pair close together, PLUS a
    # background of solo plays so the shared (x, y) pair isn't the only signal.
    z = uuid4()
    both = FakeCollabSession(
        [
            _play("alice", x, _at(0)),
            _play("alice", y, _at(1)),
            _play("bob", x, _at(0)),
            _play("bob", y, _at(1)),
            # Carol co-plays x with an unrelated track z, inflating x's popularity
            # equally in both worlds is avoided — this only exists in case 2 to
            # show the (x, y) neighbor still wins on the shared aggregate count.
            _play("carol", x, _at(0)),
            _play("carol", z, _at(1)),
        ],
        [],
    )
    patch_session(both)
    await cf.run_collaborative_recompute_once()
    both_neighbor = next(
        n for n in both.neighbors if n.track_id == x and n.neighbor_track_id == y
    )

    # Two DIFFERENT api_key_ids each playing (x, y) contribute to ONE shared
    # aggregate co-occurrence count — Alice + Bob together yield a co_play_count
    # of 2, strictly higher than a single user's 1. This is the crux of
    # cross-user aggregation: the neighbor table is global, not per-api-key.
    assert single_neighbor.co_play_count == 1
    assert both_neighbor.co_play_count == 2
