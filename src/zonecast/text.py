"""Spoken-text extraction (PRD FR-5a).

`spoken_text` is the single, authoritative basis for every word count and for TTS
input. Counting a raw draft inflates the total by ~15% (speaker tags, markers,
headers, and metadata are not spoken), which silently misses the duration contract
while appearing to hit it. Every budget check in the pipeline routes through here.
"""

from __future__ import annotations

import re

# Order matters. HTML comments (incl. multi-line STATE blocks) are removed wholesale
# first, before any line-based filtering, since a line-oriented pass cannot see across
# the newlines inside a block comment.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SPEAKER_TAG = re.compile(r"\[(?:HOST|GUEST)\]")
_PAUSE_MARKER = re.compile(r"\[PAUSE:[^\]]*\]", re.IGNORECASE)
# Markdown emphasis markers cannot be spoken and must not survive into TTS text
# (SKILL.md Pass 4 / tts-production.md). Strip the markers, keep the enclosed words.
_EMPHASIS = re.compile(r"(\*{1,3}|_{1,3})(.+?)\1", re.DOTALL)
_WHITESPACE = re.compile(r"\s+")


def spoken_text(markdown: str) -> str:
    """Return only what a narrator would actually say.

    Strips, in order: HTML comments, markdown headers (``#`` lines), the metadata
    header block (``**Field:**`` lines), ``[HOST]``/``[GUEST]`` speaker tags,
    ``[PAUSE:*]`` markers, and markdown emphasis markers; then collapses whitespace.
    """
    text = _HTML_COMMENT.sub("", markdown)

    kept_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        # Section headers / title.
        if stripped.startswith("#"):
            continue
        # Metadata header lines, e.g. "**Driving question:** ...".
        if stripped.startswith("**"):
            continue
        kept_lines.append(line)
    text = "\n".join(kept_lines)

    text = _SPEAKER_TAG.sub("", text)
    text = _PAUSE_MARKER.sub("", text)
    text = _EMPHASIS.sub(r"\2", text)

    return _WHITESPACE.sub(" ", text).strip()


def spoken_word_count(markdown: str) -> int:
    """Count spoken words in ``markdown`` (the only valid basis for budget checks)."""
    spoken = spoken_text(markdown)
    if not spoken:
        return 0
    return len(spoken.split())
