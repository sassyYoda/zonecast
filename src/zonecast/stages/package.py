"""Stage 7 — packaging (PRD FR-8, §8.4).

Turns the render stage's ordered clips into the shippable deliverables:

- ``audio/episode.mp3`` — the clips stitched in order with section-boundary silences,
  loudness-normalized and ID3-tagged (:func:`zonecast.audio.stitch`).
- ``audio/chapters.json`` — Podcasting 2.0 ``<podcast:chapters>``, one chapter per section.
  Start times come from the MEASURED cumulative clip + inserted-silence durations, NOT the
  requested break lengths (a 1.5s break renders ~1.3s), so the marks land on real audio.
- ``manifest.json`` — the episode record (schema §8.4) with full cost accounting: LLM tokens
  from the shared cost tracker, TTS characters from the render manifest, and a dollar estimate
  (LLM estimate + TTS chars × the model's per-char rate).

Resumability (RES-01): a completed package is skipped when all three outputs already exist.
"""

from __future__ import annotations

import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .. import audio
from ..pipeline import Stage, mark_complete
from ..schemas import Costs, Files, Manifest, SourceRef

if TYPE_CHECKING:
    from . import StageContext

_CLIPS_MANIFEST = "audio/clips.json"
_EPISODE_MP3 = "audio/episode.mp3"
_CHAPTERS = "audio/chapters.json"
_MANIFEST = "manifest.json"
_SCRIPT = "script/final.md"
_BLUEPRINT = "blueprint/blueprint.json"
_META = "source/meta.json"
_OFFER = "plan/offer.json"

# ElevenLabs list pricing, USD per character (PRD §15, verified against elevenlabs.io/docs
# 2026-07-15): flagship multilingual_v2 ~$0.10/1k, Flash/Turbo ~$0.05/1k. Model *selection*
# stays in config; this only maps the chosen model to its rate for the dollar estimate.
_TTS_USD_PER_CHAR_FLAGSHIP = 0.10 / 1000
_TTS_USD_PER_CHAR_FLASH = 0.05 / 1000

_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def run(ctx: "StageContext") -> None:
    if _package_already_complete(ctx):
        mark_complete(ctx.episode_dir, Stage.package)
        return

    created_at = datetime.now(timezone.utc).isoformat()

    clips_manifest = ctx.read_json(_CLIPS_MANIFEST)
    audio_dir = (ctx.episode_dir / _CLIPS_MANIFEST).parent
    clips = clips_manifest["clips"]
    if not clips:
        raise ValueError("package: audio/clips.json lists no clips; run render first.")

    section_names = {s["n"]: s["name"] for s in clips_manifest["sections"]}
    clip_paths = [audio_dir / c["file"] for c in clips]
    boundaries = _section_boundaries(clips)

    # Stitch → episode.mp3 (measured duration returned).
    id3 = _id3_tags(ctx)
    duration_actual = audio.stitch(
        clip_paths, boundaries, ctx.settings.config, ctx.episode_dir / _EPISODE_MP3, id3
    )

    # Chapters from measured durations: sum each clip + the measured section-boundary silence.
    chapters = _build_chapters(clips, clip_paths, section_names, ctx)
    ctx.write_json(_CHAPTERS, {"version": "1.2.0", "chapters": chapters})

    manifest = _build_manifest(ctx, clips_manifest, duration_actual, created_at)
    ctx.write_json(_MANIFEST, manifest)

    mark_complete(ctx.episode_dir, Stage.package)


def _package_already_complete(ctx: "StageContext") -> bool:
    return all(ctx.exists(p) for p in (_EPISODE_MP3, _CHAPTERS, _MANIFEST))


def _section_boundaries(clips: list[dict[str, Any]]) -> list[int]:
    """Clip indices that open a new section (``clip[i].section != clip[i-1].section``)."""
    out: list[int] = []
    prev: int | None = None
    for i, clip in enumerate(clips):
        if prev is not None and clip["section"] != prev:
            out.append(i)
        prev = clip["section"]
    return out


def _build_chapters(
    clips: list[dict[str, Any]],
    clip_paths: list[Path],
    section_names: dict[int, str],
    ctx: "StageContext",
) -> list[dict[str, Any]]:
    """One chapter per section; startTime = measured cumulative clip + silence durations.

    Mirrors :func:`zonecast.audio.stitch`'s interleaving exactly: a section-boundary silence is
    counted before the first clip of every section after the first, so the marks track the real
    audio rather than the requested break lengths.
    """
    audio_cfg = ctx.settings.config.audio
    # Measure the SAME silence stitch inserts (identical make_silence params) once.
    with tempfile.TemporaryDirectory() as tmp:
        silence = audio.make_silence(
            audio_cfg.gap_section_boundary_ms / 1000.0,
            Path(tmp) / "gap.mp3",
            channels=audio_cfg.channels,
        )
        silence_sec = audio.clip_duration_sec(silence)

    chapters: list[dict[str, Any]] = []
    cursor = 0.0
    prev: int | None = None
    for clip, path in zip(clips, clip_paths):
        section = clip["section"]
        if section != prev:
            if prev is not None:
                cursor += silence_sec  # silence inserted before this new section
            chapters.append(
                {"startTime": round(cursor, 3), "title": section_names.get(section, str(section))}
            )
        cursor += audio.clip_duration_sec(path)
        prev = section
    return chapters


def _build_manifest(
    ctx: "StageContext",
    clips_manifest: dict[str, Any],
    duration_actual: float,
    created_at: str,
) -> Manifest:
    meta = ctx.read_json(_META)
    blueprint = ctx.read_json(_BLUEPRINT)

    totals = ctx.llm.costs.totals()
    tts_chars = int(clips_manifest.get("chars_rendered", 0))
    estimated_usd = ctx.llm.costs.estimate_usd() + tts_chars * _tts_rate(
        clips_manifest.get("model_id", "")
    )

    return Manifest(
        episode_id=ctx.episode_dir.name,
        title=blueprint.get("title", meta.get("title", "")),
        duration_target_min=_duration_target(ctx),
        duration_actual_sec=round(duration_actual),
        format="solo",  # two_host is M3
        source=SourceRef(type=meta["type"], ref=meta["ref"]),
        files=Files(mp3=_EPISODE_MP3, chapters=_CHAPTERS, script=_SCRIPT),
        costs=Costs(
            llm_input_tokens=totals["input_tokens"],
            llm_output_tokens=totals["output_tokens"],
            tts_characters=tts_chars,
            estimated_usd=round(estimated_usd, 4),
        ),
        created_at=created_at,
        published=False,
    )


def _tts_rate(model_id: str) -> float:
    """Per-character USD rate for the rendered model (Flash tier is ~half the flagship)."""
    return _TTS_USD_PER_CHAR_FLASH if "flash" in model_id.lower() else _TTS_USD_PER_CHAR_FLAGSHIP


def _duration_target(ctx: "StageContext") -> int:
    """The offered target length in minutes: from the chosen offer, else the request/args."""
    if ctx.exists(_OFFER):
        offer = ctx.read_json(_OFFER)
        if offer.get("duration_min"):
            return int(offer["duration_min"])
    if ctx.args and ctx.args.duration:
        return int(ctx.args.duration)
    if ctx.exists("request.json"):
        req = ctx.read_json("request.json")
        if req.get("duration"):
            return int(req["duration"])
    return 0


def _id3_tags(ctx: "StageContext") -> dict[str, str]:
    """ID3 tags for the episode MP3: title (blueprint), artist Zonecast, album, episode date."""
    blueprint = ctx.read_json(_BLUEPRINT) if ctx.exists(_BLUEPRINT) else {}
    meta = ctx.read_json(_META) if ctx.exists(_META) else {}
    title = blueprint.get("title") or meta.get("title") or ctx.episode_dir.name
    tags = {
        "title": title,
        "artist": "Zonecast",
        "album": ctx.settings.config.feed.title,
    }
    m = _DATE_PREFIX.match(ctx.episode_dir.name)
    if m:
        tags["date"] = m.group(1)
    return tags
