"""Episode working directory + stage checkpointing (PRD §9 layout, §11–12 resumability).

Every stage writes a completion marker so ``resume`` can skip finished work and never re-pay
for it (RES-01). Markers are empty files under ``<episode_dir>/.stages/<stage>.done`` — the
simplest scheme that is atomic per stage and trivially inspectable.
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path


class Stage(str, Enum):
    """The eight pipeline stages, in execution order (PRD §5)."""

    ingest = "ingest"
    plan = "plan"
    blueprint = "blueprint"
    generate = "generate"
    polish = "polish"
    render = "render"
    package = "package"
    publish = "publish"


# Ordered stage sequence for `first_incomplete` scans and `create`/`resume`.
STAGES: tuple[Stage, ...] = tuple(Stage)

# Per-episode working subdirectories (PRD §9).
_SUBDIRS = ("source", "draft", "script", "audio")
_MARKER_DIR = ".stages"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    """Lowercase, hyphenate, and trim ``text`` to a filesystem-safe slug."""
    return _SLUG_STRIP.sub("-", text.lower()).strip("-")


def episode_id(topic: str, date_str: str) -> str:
    """Build a deterministic episode id like ``2026-07-16-how-transformers-work``.

    ``date_str`` (``YYYY-MM-DD``) is passed in, never read from the clock, so the id is
    reproducible for tests and for resume.
    """
    return f"{date_str}-{_slugify(topic)}"


def episode_dir(episodes_root: str | Path, ep_id: str) -> Path:
    """Return the working directory path for ``ep_id`` under ``episodes_root``."""
    return Path(episodes_root) / ep_id


def ensure_episode_dirs(ep_dir: str | Path) -> Path:
    """Create the episode dir, its stage subdirs, and the marker dir. Idempotent."""
    root = Path(ep_dir)
    for sub in _SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / _MARKER_DIR).mkdir(parents=True, exist_ok=True)
    return root


def _marker(ep_dir: str | Path, stage: Stage | str) -> Path:
    name = stage.value if isinstance(stage, Stage) else str(stage)
    return Path(ep_dir) / _MARKER_DIR / f"{name}.done"


def mark_complete(ep_dir: str | Path, stage: Stage | str) -> None:
    """Write the completion marker for ``stage``."""
    marker = _marker(ep_dir, stage)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


def is_complete(ep_dir: str | Path, stage: Stage | str) -> bool:
    """True if ``stage``'s completion marker exists."""
    return _marker(ep_dir, stage).exists()


def first_incomplete(
    ep_dir: str | Path,
    stages: tuple[Stage, ...] = STAGES,
) -> Stage | None:
    """Return the first stage in ``stages`` without a completion marker, or ``None`` if all
    are complete (the resume entry point)."""
    for stage in stages:
        if not is_complete(ep_dir, stage):
            return stage
    return None
