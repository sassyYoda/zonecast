"""ElevenLabs TTS wrapper: paragraph chunker, clip cache, and stitched render (PRD FR-7, §11).

Three concerns live here, all provider-mechanics the render stage orchestrates:

- ``chunk_text`` packs a normalized script into 2k–5k-char requests at paragraph (never
  sentence) boundaries — long single requests degrade prosody and are painful to retry
  (tts-production.md).
- ``clip_cache_key`` / the on-disk ``<key>.mp3`` cache is RES-02: an identical
  ``(voice, model, text)`` triple must never re-bill, so ``resume`` past a killed render pays
  only for the chunks it hadn't finished.
- :class:`TTSClient` renders chunks IN ORDER with request-stitching continuity so prosody
  doesn't reset at chunk seams. Stitching is inherently sequential (each chunk conditions on
  the previous request's id), so rendering stays sequential *by design* — parallelism up to
  ``config.tts.max_parallel_requests`` would only help if we dropped stitching, and we don't.

Stitching invariants baked in from live-doc research + a real spike (do NOT relitigate):
- ``previous_request_ids`` accepts at most ``stitch_max_previous_ids`` (3) ids and they expire
  after ``stitch_id_ttl_sec`` (2h). A stale/missing id falls back to ``previous_text``.
- ``previous_request_ids`` silently overrides ``previous_text`` when both are sent, so we send
  exactly one continuity signal per call.
- The request id comes from a *response header*, which is why we use the raw-response API.
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .config import Settings

# 128 kbps mono-friendly MP3 — plenty for speech, keeps episodes small (tts-production.md).
_OUTPUT_FORMAT = "mp3_44100_128"
# The request id rides on a response header (not the body), hence the raw-response API. The
# name is not surfaced by the SDK — it is passed straight through from httpx — so we probe a
# couple of spellings for robustness. ElevenLabs documents ``request-id``.
_REQUEST_ID_HEADERS = ("request-id", "x-request-id")
# Per-chunk retry budget (PRD §12): 3 attempts total, exponential backoff between them.
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SEC = 1.0
# How much of the previous chunk's text to pass as ``previous_text`` when no live request id is
# available (cache hit or stale ids). The tail is what a stitched request conditions prosody on.
_PREV_TEXT_TAIL_CHARS = 500

# Sentence boundary: end punctuation followed by whitespace. Only used as the FALLBACK split
# when a single paragraph busts the max-chars ceiling — normal splits are at blank lines.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


class TTSRenderError(RuntimeError):
    """Raised when a chunk still fails after ``_MAX_ATTEMPTS`` render attempts (PRD §12)."""


def chunk_text(text: str, min_chars: int, max_chars: int) -> list[str]:
    """Pack ``text`` into ``min_chars``–``max_chars`` chunks at PARAGRAPH boundaries.

    Paragraphs (blank-line separated) are greedily packed up to ``max_chars`` so seams land at
    natural pauses and never mid-sentence. A single paragraph larger than ``max_chars`` is the
    only case that splits finer — at sentence boundaries (the documented fallback). The result
    is never empty for non-empty input: a tiny script yields exactly one (sub-min) chunk.
    """
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current:
            chunks.append(current)
            current = ""

    for para in paragraphs:
        if len(para) > max_chars:
            # Oversized paragraph: flush what we have, then emit sentence-packed sub-chunks so
            # nothing is ever split inside a sentence.
            flush()
            chunks.extend(_split_paragraph(para, max_chars))
            continue
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars:
            current = candidate
        else:
            # Adding this paragraph would bust the ceiling — the current chunk is already as
            # full as it can get (hence >= min in practice), so close it and start fresh.
            flush()
            current = para
    flush()
    return chunks


def _split_paragraph(para: str, max_chars: int) -> list[str]:
    """Greedily pack a too-long paragraph's sentences into <= ``max_chars`` pieces.

    A lone sentence longer than ``max_chars`` is emitted whole — splitting it would break
    mid-sentence, which is worse than an oversized request.
    """
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_SPLIT.split(para):
        if not sentence:
            continue
        candidate = f"{current} {sentence}" if current else sentence
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces


def clip_cache_key(voice_id: str, model_id: str, text: str) -> str:
    """Stable sha256 over ``(voice, model, text)`` — the RES-02 no-double-bill key.

    Any change to voice, model, or a single character of text yields a different key (and thus
    a fresh render); identical inputs always resolve to the same cached clip. NUL separators
    keep field boundaries unambiguous so no concatenation collision is possible.
    """
    h = hashlib.sha256()
    h.update(voice_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(model_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


class TTSClient:
    """ElevenLabs render wrapper with a disk clip cache and request-stitching continuity.

    The underlying SDK client is built lazily (and only when a real render is needed), so a
    fully-cached ``resume`` never touches the network or requires ``ELEVENLABS_API_KEY``.
    ``client``/``time_fn``/``sleep_fn`` are injectable for tests (no real API calls).
    """

    def __init__(
        self,
        settings: "Settings",
        client: Any = None,
        *,
        time_fn: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._client = client
        self._time = time_fn
        self._sleep = sleep_fn
        tts = settings.config.tts
        self._max_ids = tts.stitch_max_previous_ids
        self._ttl_sec = tts.stitch_id_ttl_sec
        # Billable characters actually sent to the API this run (cache hits excluded) — the
        # render stage surfaces this into the manifest for cost accounting.
        self.chars_rendered = 0

    def _ensure_client(self) -> Any:
        if self._client is None:
            from elevenlabs.client import ElevenLabs

            api_key = self.settings.get("ELEVENLABS_API_KEY")
            if not api_key:
                raise TTSRenderError(
                    "ELEVENLABS_API_KEY is required to render new audio but was not found in "
                    "env or .env."
                )
            self._client = ElevenLabs(api_key=api_key)
        return self._client

    def render_chunks(
        self,
        chunks: list[str],
        voice_id: str,
        model_id: str,
        out_dir: Path,
    ) -> list[Path]:
        """Render ``chunks`` IN ORDER to ``out_dir/<key>.mp3``, returning ordered clip paths.

        Sequential by necessity: each chunk conditions prosody on the previous request's id
        (stitching), so this cannot be parallelized without abandoning continuity. A chunk whose
        cache file already exists is reused with NO API call (RES-02). Otherwise it renders with
        the up-to-3 most-recent, non-stale request ids for continuity, falling back to the tail
        of the previous chunk's text when no live id is available.
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        recent_ids: list[tuple[str, float]] = []  # (request_id, created_ts), newest last
        prev_text = ""  # tail of the immediately preceding chunk, for previous_text fallback

        for chunk in chunks:
            key = clip_cache_key(voice_id, model_id, chunk)
            dest = out_dir / f"{key}.mp3"
            if dest.exists():
                # Cache hit — never re-bill (RES-02). No response id to carry forward, so the
                # next chunk's continuity falls back to previous_text.
                paths.append(dest)
                prev_text = chunk[-_PREV_TEXT_TAIL_CHARS:]
                continue

            audio, request_id = self._render_one(
                chunk, voice_id, model_id, recent_ids, prev_text
            )
            dest.write_bytes(audio)
            self.chars_rendered += len(chunk)
            paths.append(dest)
            if request_id:
                recent_ids.append((request_id, self._time()))
            prev_text = chunk[-_PREV_TEXT_TAIL_CHARS:]

        return paths

    def _select_previous_ids(self, recent_ids: list[tuple[str, float]]) -> list[str]:
        """The <= ``_max_ids`` most-recent request ids that are still inside the 2h TTL window.

        Stale ids are dropped (the API would reject or ignore them); when nothing valid remains
        the caller uses ``previous_text`` instead.
        """
        now = self._time()
        fresh = [rid for rid, ts in recent_ids if now - ts < self._ttl_sec]
        return fresh[-self._max_ids:]

    def _render_one(
        self,
        text: str,
        voice_id: str,
        model_id: str,
        recent_ids: list[tuple[str, float]],
        prev_text: str,
    ) -> tuple[bytes, str | None]:
        """Render one chunk with retries; return ``(mp3_bytes, request_id_or_None)``."""
        kwargs: dict[str, Any] = {
            "voice_id": voice_id,
            "text": text,
            "model_id": model_id,
            "output_format": _OUTPUT_FORMAT,
        }
        prev_ids = self._select_previous_ids(recent_ids)
        if prev_ids:
            # Send ids OR text, never both — ids silently override previous_text upstream.
            kwargs["previous_request_ids"] = prev_ids
        elif prev_text:
            kwargs["previous_text"] = prev_text

        client = self._ensure_client()
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                with client.text_to_speech.with_raw_response.convert(**kwargs) as response:
                    audio = b"".join(response.data)
                    request_id = _read_request_id(response.headers)
                return audio, request_id
            except Exception as exc:  # transient network / 429 / 5xx -> backoff and retry
                last_exc = exc
                if attempt < _MAX_ATTEMPTS - 1:
                    self._sleep(_BACKOFF_BASE_SEC * (2**attempt))
        raise TTSRenderError(
            f"TTS render failed after {_MAX_ATTEMPTS} attempts: {last_exc}"
        ) from last_exc


def _read_request_id(headers: dict[str, str]) -> str | None:
    """Pull the stitching request id out of the response headers (case-insensitive)."""
    lowered = {k.lower(): v for k, v in headers.items()}
    for name in _REQUEST_ID_HEADERS:
        value = lowered.get(name)
        if value:
            return value
    return None


__all__ = ["TTSClient", "TTSRenderError", "chunk_text", "clip_cache_key"]
