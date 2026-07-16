"""Stage 6 — TTS render (PRD FR-7, SKILL Pass 5, tts-production.md).

Turns ``script/final.md`` into ordered MP3 clips the packager stitches into an episode. Three
steps:

1. **Normalize** each section's spoken body into audio-ready text with one ``llm.text`` call
   (``build_system("render", …)`` injects tts-production.md): numbers/acronyms/symbols → spoken
   form, markdown stripped. A deterministic post-pass then *guarantees* the delivery-markup
   contract that must not drift — ``[PAUSE:short|long]`` → ``<break>`` and no bracket audio tags
   survive — because on the pinned ``eleven_multilingual_v2`` bracket tags are read aloud while
   SSML ``<break>`` is honored (confirmed by spike). The concatenated result is persisted to
   ``script/tts.txt`` for inspection.
2. **Chunk** each normalized section independently (``chunk_text``) so a chunk never spans a
   section boundary — a prosody reset at a section seam sounds natural, and it keeps a clean
   clip→section mapping for chapters/silences.
3. **Render** every chunk in order through :class:`TTSClient` (stitched, disk-cached), then
   persist ``audio/clips.json``: the ordered clips with their section and source char count, so
   the packager can place section-boundary silences + chapter marks and account TTS cost.

Resumability (RES-01/RES-02): a completed render is skipped when ``clips.json`` lists clips that
all still exist on disk; individual cached clips are never re-billed even on a partial resume.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING

from ..pipeline import Stage, mark_complete
from ..prompt import build_system
from ..tts import TTSClient, chunk_text

if TYPE_CHECKING:
    from . import StageContext

_log = logging.getLogger(__name__)

_FINAL_PATH = "script/final.md"
_TTS_TEXT_PATH = "script/tts.txt"
# Cached per-section normalized text. Normalization is a non-deterministic LLM call, so on a
# re-entry (resume after a mid-render crash, or a retried render) it would otherwise produce a
# *different* tts.txt, changing every chunk's cache key and re-billing both the LLM and every
# already-rendered TTS clip. Caching it keyed to a hash of final.md makes normalization run
# exactly once per script — closing the RES-02 / ACC-02 no-double-bill guarantee.
_NORMALIZED_CACHE = "script/tts_sections.json"
_CLIPS_DIR = "audio/clips"
_CLIPS_MANIFEST = "audio/clips.json"

# "## Section N: name [~budget words]" — capture the number and the trailing header text.
_SECTION_HEADER = re.compile(r"^##\s*Section\s+(\d+):?\s*(.*)$", re.MULTILINE)

# Delivery-markup translation for eleven_multilingual_v2 (tts-production.md, spike-confirmed).
# These are the ONLY delivery markers the model honors; a 1.5s break renders ~1.3s and caps at
# 3s. Bracket audio tags ([pause], [excited], …) are a v3 dialect and are read ALOUD on v2, so
# none may survive into the spoken text.
_PAUSE_TO_BREAK = {
    "short": '<break time="0.5s"/>',
    "long": '<break time="1.5s"/>',
}
_PAUSE_MARKER = re.compile(r"\[PAUSE:(short|long)\]", re.IGNORECASE)
_ANY_PAUSE_MARKER = re.compile(r"\[PAUSE:[^\]]*\]", re.IGNORECASE)
_SPEAKER_TAG = re.compile(r"\[(?:HOST|GUEST)\]")
_EMPHASIS = re.compile(r"(\*{1,3}|_{1,3})(.+?)\1", re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# Long outputs stream through llm.text; give thinking + a full normalized section headroom.
_RENDER_MAX_TOKENS = 16_000


def run(ctx: "StageContext") -> None:
    if _render_already_complete(ctx):
        mark_complete(ctx.episode_dir, Stage.render)
        return

    tts_cfg = ctx.settings.config.tts
    voice_id = tts_cfg.voice_host
    model_id = tts_cfg.model

    sections = _parse_sections(ctx.read_text(_FINAL_PATH))
    if not sections:
        raise ValueError(
            f"render: no '## Section N' headers found in {_FINAL_PATH}; run polish first."
        )

    normalized = _load_or_normalize(ctx, sections)

    # Persist the full audio-ready text (solo narrator) for inspection; blank lines between
    # sections become natural pauses and keep the chunker's paragraph boundaries clean.
    ctx.write_text(_TTS_TEXT_PATH, "\n\n".join(text for _, _, text in normalized) + "\n")

    # Chunk each section independently so no chunk spans a section boundary.
    tagged_chunks: list[tuple[int, str]] = []  # (section_n, chunk_text)
    for n, _name, text in normalized:
        for chunk in chunk_text(text, tts_cfg.chunk_chars_min, tts_cfg.chunk_chars_max):
            tagged_chunks.append((n, chunk))

    out_dir = ctx.episode_dir / _CLIPS_DIR
    client = TTSClient(ctx.settings)
    clip_paths = client.render_chunks(
        [chunk for _, chunk in tagged_chunks], voice_id, model_id, out_dir
    )

    _write_manifest(ctx, sections, tagged_chunks, clip_paths, voice_id, model_id, client)
    mark_complete(ctx.episode_dir, Stage.render)


def _load_or_normalize(
    ctx: "StageContext", sections: list[tuple[int, str, str]]
) -> list[tuple[int, str, str]]:
    """Return per-section normalized text, reusing the on-disk cache when it matches final.md.

    Normalization is a non-deterministic LLM call. Running it again on a resume would yield a
    different tts.txt and re-bill every downstream TTS clip (RES-02) plus the LLM itself
    (ACC-02). The cache is keyed to a hash of final.md, so it is reused across re-entries and
    invalidated only when the script actually changes (e.g. ``redo --stage polish``).
    """
    final_text = ctx.read_text(_FINAL_PATH)
    final_sha = hashlib.sha256(final_text.encode("utf-8")).hexdigest()

    if ctx.exists(_NORMALIZED_CACHE):
        cached = ctx.read_json(_NORMALIZED_CACHE)
        if cached.get("final_sha") == final_sha:
            _log.info("render: reusing cached normalization (%d sections)", len(cached["sections"]))
            return [(s["n"], s["name"], s["text"]) for s in cached["sections"]]

    system = build_system("render", settings=ctx.settings)
    normalized: list[tuple[int, str, str]] = []  # (section_n, name, normalized_text)
    for n, name, body in sections:
        text = _normalize_section(ctx, system, body)
        _check_pause_translation(n, body, text)
        normalized.append((n, name, text))

    ctx.write_json(
        _NORMALIZED_CACHE,
        {
            "final_sha": final_sha,
            "sections": [{"n": n, "name": name, "text": text} for n, name, text in normalized],
        },
    )
    return normalized


def _render_already_complete(ctx: "StageContext") -> bool:
    """True iff a prior render's manifest exists and every clip it lists is still on disk."""
    if not ctx.exists(_CLIPS_MANIFEST):
        return False
    manifest = ctx.read_json(_CLIPS_MANIFEST)
    audio_dir = (ctx.episode_dir / _CLIPS_MANIFEST).parent
    clips = manifest.get("clips", [])
    if not clips:
        return False
    return all((audio_dir / clip["file"]).exists() for clip in clips)


def _parse_sections(final_md: str) -> list[tuple[int, str, str]]:
    """Split ``final.md`` into ordered ``(n, name, body)`` by its ``## Section N`` headers.

    The title + metadata block before the first section header is dropped — it is not spoken.
    """
    matches = list(_SECTION_HEADER.finditer(final_md))
    out: list[tuple[int, str, str]] = []
    for i, m in enumerate(matches):
        n = int(m.group(1))
        name = m.group(2).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(final_md)
        body = final_md[m.end():end].strip()
        out.append((n, name, body))
    return out


def _normalize_section(ctx: "StageContext", system: list, body: str) -> str:
    """LLM-normalize one section body, then deterministically enforce the TTS-markup contract."""
    user = _build_normalize_user(body)
    raw = ctx.llm.text("render", system, user, fast=True, max_tokens=_RENDER_MAX_TOKENS)
    return _enforce_tts_markup(raw)


def _build_normalize_user(body: str) -> str:
    return "\n".join(
        [
            "Convert this section of the script into audio-ready text for text-to-speech, "
            "following the TTS Production reference in your instructions.",
            "",
            "Rules:",
            "- Rewrite numbers, math, acronyms, and symbols as they should be SPOKEN (never as "
            "notation the model would mispronounce).",
            "- Strip all markdown, citations, URLs, and bracketed asides — nothing but spoken "
            "words and the delivery markup below may remain.",
            "- Drop [HOST]/[GUEST] speaker tags (this is a solo narrator).",
            "- Translate the script's pause markers to SSML breaks: [PAUSE:short] -> "
            '<break time="0.5s"/> and [PAUSE:long] -> <break time="1.5s"/>. Keep the <break> '
            "tags verbatim in your output — they are for the TTS engine, not to be spoken or "
            "removed.",
            "- Never emit bracket audio tags like [pause] or [excited]; on this model they are "
            "read aloud as words.",
            "- Do NOT reintroduce markdown or emphasis markers.",
            "",
            "Output ONLY the audio-ready text.",
            "",
            "Section text:",
            body,
        ]
    )


def _enforce_tts_markup(text: str) -> str:
    """Deterministically guarantee the eleven_multilingual_v2 delivery-markup contract.

    Idempotent belt-and-suspenders over the LLM normalization: translate any surviving
    ``[PAUSE:short|long]`` marker to its ``<break>`` tag, and scrub the artifacts that must
    never reach v2 (speaker tags, STATE comments, markdown emphasis). ``<break>`` tags already
    present are preserved. Also the standalone translation helper the render test pins.
    """
    text = _HTML_COMMENT.sub("", text)
    text = _PAUSE_MARKER.sub(lambda m: _PAUSE_TO_BREAK[m.group(1).lower()], text)
    # Any malformed pause marker that slipped the mapping is dropped rather than read aloud.
    text = _ANY_PAUSE_MARKER.sub("", text)
    text = _SPEAKER_TAG.sub("", text)
    text = _EMPHASIS.sub(r"\2", text)
    # Collapse the whitespace a stripped tag may leave, but keep paragraph breaks (blank lines)
    # since the chunker splits on them.
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _check_pause_translation(n: int, body: str, normalized: str) -> None:
    """Warn if the number of ``<break>`` tags drifts far from the input's ``[PAUSE:*]`` count.

    A large mismatch means normalization dropped or invented pauses — the deliverable is still
    valid (markup, not words), but the prompt under-performed and it is worth flagging.
    """
    wanted = len(_ANY_PAUSE_MARKER.findall(body))
    got = normalized.count("<break")
    if wanted and abs(got - wanted) > max(1, wanted // 2):
        _log.warning(
            "render: section %d has %d <break> tag(s) for %d [PAUSE:*] marker(s) in the source",
            n,
            got,
            wanted,
        )


def _write_manifest(
    ctx: "StageContext",
    sections: list[tuple[int, str, str]],
    tagged_chunks: list[tuple[int, str]],
    clip_paths: list,
    voice_id: str,
    model_id: str,
    client: TTSClient,
) -> None:
    """Persist ``audio/clips.json`` — the packager's contract for ordering, section boundaries,
    and cost. Clip paths are stored relative to the manifest's dir (``audio/``)."""
    audio_dir = (ctx.episode_dir / _CLIPS_MANIFEST).parent
    clips = [
        {
            "file": str(path.relative_to(audio_dir)),
            "section": n,
            "chars": len(chunk),
        }
        for (n, chunk), path in zip(tagged_chunks, clip_paths)
    ]
    manifest = {
        "voice_id": voice_id,
        "model_id": model_id,
        "output_format": "mp3_44100_128",
        "chars_rendered": client.chars_rendered,
        "sections": [{"n": n, "name": name} for n, name, _ in sections],
        "clips": clips,
    }
    ctx.write_json(_CLIPS_MANIFEST, manifest)
