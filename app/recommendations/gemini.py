from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from uuid import UUID

import httpx

from app.db.models import Track

logger = logging.getLogger(__name__)


class GeminiRecommendationUnavailable(RuntimeError):
    pass


class GeminiRateLimited(GeminiRecommendationUnavailable):
    pass


@dataclass(frozen=True)
class GeminiCandidate:
    track: Track
    score: float
    reasons: list[str]


@dataclass(frozen=True)
class GeminiRerankResult:
    ordered_ids: list[UUID]
    notes: dict[UUID, str]


class GeminiRecommendationClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip())

    async def rerank(
        self,
        *,
        seed: Track,
        candidates: list[GeminiCandidate],
        redis=None,
    ) -> GeminiRerankResult:
        if not self.is_configured or not candidates:
            raise GeminiRecommendationUnavailable("Gemini is not configured.")

        cache_key = _rerank_cache_key(model=self.model, seed=seed, candidates=candidates)
        if redis is not None:
            try:
                cached = await redis.get(cache_key)
                if cached:
                    logger.debug("Gemini rerank cache hit: %s", cache_key)
                    return _deserialize_rerank_result(cached)
            except Exception as exc:
                logger.warning("Redis get failed (ignored): %s", exc)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": _prompt(seed=seed, candidates=candidates)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.15,
                "responseMimeType": "application/json",
            },
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, params={"key": self.api_key}, json=payload)
        except httpx.HTTPError as exc:
            raise GeminiRecommendationUnavailable(str(exc)) from exc

        if response.status_code == 429:
            raise GeminiRateLimited("Gemini rate limit reached.")
        if response.status_code >= 400:
            raise GeminiRecommendationUnavailable(
                f"Gemini returned HTTP {response.status_code}."
            )

        try:
            text = _response_text(response.json())
            parsed = json.loads(text)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GeminiRecommendationUnavailable("Gemini returned an invalid rerank payload.") from exc

        allowed_ids = {str(candidate.track.id): candidate.track.id for candidate in candidates}
        ordered_ids: list[UUID] = []
        for raw_id in parsed.get("track_ids", []):
            track_id = allowed_ids.get(str(raw_id))
            if track_id is not None and track_id not in ordered_ids:
                ordered_ids.append(track_id)

        notes: dict[UUID, str] = {}
        raw_notes = parsed.get("notes", {})
        if isinstance(raw_notes, dict):
            for raw_id, note in raw_notes.items():
                track_id = allowed_ids.get(str(raw_id))
                if track_id is not None and isinstance(note, str) and note.strip():
                    notes[track_id] = note.strip()[:160]

        if not ordered_ids:
            raise GeminiRecommendationUnavailable("Gemini returned no usable track ids.")
        result = GeminiRerankResult(ordered_ids=ordered_ids, notes=notes)

        if redis is not None:
            try:
                await redis.setex(
                    cache_key, self.cache_ttl_seconds, _serialize_rerank_result(result)
                )
                logger.debug("Gemini rerank cache set: %s (TTL=%ds)", cache_key, self.cache_ttl_seconds)
            except Exception as exc:
                logger.warning("Redis set failed (ignored): %s", exc)

        return result


def _prompt(*, seed: Track, candidates: list[GeminiCandidate]) -> str:
    candidate_payload = [
        {
            "id": str(item.track.id),
            "title": item.track.title,
            "artist": item.track.artist,
            "album": item.track.album,
            "duration_seconds": item.track.duration_seconds,
            "local_score": item.score,
            "local_reasons": item.reasons,
        }
        for item in candidates
    ]
    return (
        "You are reranking autoplay candidates for a private local music library. "
        "Use the local_score as the main signal, then improve flow, artist diversity, "
        "and session continuity. Do not invent tracks or IDs. "
        "Return compact JSON only: {\"track_ids\":[...],\"notes\":{\"id\":\"short reason\"}}.\n\n"
        f"Seed track: {json.dumps(_track_payload(seed), ensure_ascii=False)}\n"
        f"Candidates: {json.dumps(candidate_payload, ensure_ascii=False)}"
    )


def _track_payload(track: Track) -> dict[str, object]:
    return {
        "id": str(track.id),
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "duration_seconds": track.duration_seconds,
    }


def _rerank_cache_key(*, model: str, seed: Track, candidates: list[GeminiCandidate]) -> str:
    candidate_ids = sorted(str(candidate.track.id) for candidate in candidates)
    digest = hashlib.sha1(",".join(candidate_ids).encode("utf-8")).hexdigest()
    return f"gemini:rerank:{model}:{seed.id}:{digest}"


def _serialize_rerank_result(result: GeminiRerankResult) -> str:
    return json.dumps(
        {
            "ordered_ids": [str(track_id) for track_id in result.ordered_ids],
            "notes": {str(track_id): note for track_id, note in result.notes.items()},
        }
    )


def _deserialize_rerank_result(raw: str) -> GeminiRerankResult:
    data = json.loads(raw)
    return GeminiRerankResult(
        ordered_ids=[UUID(value) for value in data["ordered_ids"]],
        notes={UUID(key): value for key, value in data.get("notes", {}).items()},
    )


def _response_text(payload: dict[str, object]) -> str:
    candidates = payload["candidates"]
    first = candidates[0]
    content = first["content"]
    parts = content["parts"]
    text = parts[0]["text"]
    if not isinstance(text, str):
        raise TypeError("Gemini text part is not a string.")
    return text
