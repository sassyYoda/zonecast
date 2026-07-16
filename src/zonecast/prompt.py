"""System-prompt assembly from the skill assets (PRD FR-2).

Every LLM call builds its system prompt by reading the skill markdown from disk *at call
time*. The files under ``prompts/skills/explainer-podcast/`` are the product's quality spec
and its prompt assets — editing them must change behavior with zero code change. Nothing here
caches file contents at import; :func:`build_system` re-reads on every call. This is a hard
requirement (CLAUDE.md, FR-2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Settings, get_settings

# Skill files, relative to ``config.paths.skill_dir``.
_SKILL = "SKILL.md"
_LISTENER = "references/listener.md"
_STYLE_GUIDE = "references/style-guide.md"
_ANTI = "references/anti-patterns.md"
_TTS = "references/tts-production.md"

# Stages that inject the craft style guide (FR-2: "stages 3–5" = blueprint/generate/polish).
_STYLE_GUIDE_STAGES = frozenset({"blueprint", "generate", "polish"})
# Stages that inject the anti-pattern reference — the concrete "how not to sound generated"
# examples belong where prose is actually written and edited, not at blueprint time.
_ANTI_STAGES = frozenset({"generate", "polish"})
# Stage that injects the TTS-production reference (FR-2: "stage 6" = render normalization).
_TTS_STAGES = frozenset({"render"})

# The stable prefix that is worth caching across the many per-section calls: SKILL + listener
# + style-guide + anti-patterns. The single ephemeral cache_control marker lands on the last of
# these present for the stage, so the prefix caches across the many section-generation calls.
_STABLE_PREFIX = (_SKILL, _LISTENER, _STYLE_GUIDE, _ANTI)


def _skill_relpaths(stage: str) -> list[str]:
    """Ordered skill files for ``stage``, relative to the skill dir (no field style file)."""
    rel = [_SKILL, _LISTENER]
    if stage in _STYLE_GUIDE_STAGES:
        rel.append(_STYLE_GUIDE)
    if stage in _ANTI_STAGES:
        rel.append(_ANTI)
    if stage in _TTS_STAGES:
        rel.append(_TTS)
    return rel


def _resolve_style_file(style_file: str | None, settings: Settings) -> Path | None:
    """Resolve an optional field style file to an existing path, or ``None``.

    Accepts an explicit path, a path/slug under ``styles/``, or a bare slug (``.md`` appended).
    Nullable through M1–M3, so a missing or absent file is tolerated silently (FR-3/FR-10).
    """
    if not style_file:
        return None
    styles_dir = Path(settings.config.paths.styles_dir)
    candidates = [Path(style_file), styles_dir / style_file]
    if not style_file.endswith(".md"):
        candidates.append(styles_dir / f"{style_file}.md")
    return next((c for c in candidates if c.exists()), None)


def stage_files(
    stage: str,
    style_file: str | None = None,
    settings: Settings | None = None,
) -> list[Path]:
    """Return the ordered list of files that :func:`build_system` would read for ``stage``.

    Exposed for testing and observability; includes the resolved field style file when present.
    """
    if settings is None:
        settings = get_settings()
    skill_dir = Path(settings.config.paths.skill_dir)
    paths = [skill_dir / rel for rel in _skill_relpaths(stage)]
    resolved = _resolve_style_file(style_file, settings)
    if resolved is not None:
        paths.append(resolved)
    return paths


def build_system(
    stage: str,
    style_file: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Assemble the Anthropic ``system`` content blocks for ``stage``.

    One text block per skill file, read fresh from disk. Exactly one ``cache_control``
    ephemeral marker is placed on the last block of the stable prefix (SKILL + listener +
    style-guide) so the ~7.5k-token prefix caches across the many section-generation calls.
    The field style file, when present, is appended after the marker. Nothing volatile
    (episode id, timestamp) belongs here.
    """
    if settings is None:
        settings = get_settings()
    skill_dir = Path(settings.config.paths.skill_dir)

    rel_files = _skill_relpaths(stage)
    # Last stable-prefix file present for this stage: where the cache marker goes.
    stable_present = [rel for rel in rel_files if rel in _STABLE_PREFIX]
    cache_marker_rel = stable_present[-1] if stable_present else rel_files[-1]

    blocks: list[dict[str, Any]] = []
    for rel in rel_files:
        block: dict[str, Any] = {"type": "text", "text": (skill_dir / rel).read_text()}
        if rel == cache_marker_rel:
            block["cache_control"] = {"type": "ephemeral"}
        blocks.append(block)

    resolved = _resolve_style_file(style_file, settings)
    if resolved is not None:
        # Field style guide is injected *alongside*, never instead of, the core files (CLAUDE.md).
        blocks.append({"type": "text", "text": resolved.read_text()})

    return blocks
