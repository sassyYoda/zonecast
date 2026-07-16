"""Configuration and environment loading (PRD FR-11, §12 preflight)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LLMConfig(_Base):
    provider: str
    model_quality: str
    model_fast: str
    max_retries_json: int


class TTSConfig(_Base):
    provider: str
    model: str
    model_fast: str
    voice_host: str
    voice_guest: str
    chunk_chars_min: int
    chunk_chars_max: int
    stitch_max_previous_ids: int
    stitch_id_ttl_sec: int
    max_parallel_requests: int


class ScriptConfig(_Base):
    wpm: int
    budget_tolerance_pct: int
    # Duration-scoped section budgets (PRD FR-4): the 800-word floor is arithmetically
    # impossible inside a 2,250-word overview contract, so bands are selected by duration.
    overview_max_duration_min: int
    standard_min_duration_min: int
    section_words_min: int
    section_words_max: int
    overview_beat_words_min: int
    overview_beat_words_max: int


class AudioConfig(_Base):
    format: str
    bitrate: str
    channels: int
    loudnorm: str
    gap_speaker_change_ms: int
    gap_section_boundary_ms: int


class PathsConfig(_Base):
    skill_dir: str
    styles_dir: str
    episodes_dir: str


class FeedConfig(_Base):
    title: str
    description: str
    author: str
    language: str
    feed_path: str


class Config(_Base):
    llm: LLMConfig
    tts: TTSConfig
    script: ScriptConfig
    audio: AudioConfig
    paths: PathsConfig
    feed: FeedConfig


def load_config(path: str | Path = "config.yaml") -> Config:
    """Read and validate ``config.yaml`` into a :class:`Config`."""
    data = yaml.safe_load(Path(path).read_text())
    return Config.model_validate(data)


def load_env(path: str | Path = ".env") -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines from a dotenv file.

    Strips surrounding matching quotes (single or double) and whitespace from each
    value. This is not cosmetic: an ElevenLabs key stored as ``"sk_..."`` with literal
    quotes was being sent to the API verbatim, quotes and all. ``KEY="abc"`` -> ``abc``,
    ``KEY='abc'`` -> ``abc``, ``KEY=abc `` -> ``abc``. Missing file yields ``{}``.
    """
    p = Path(path)
    if not p.exists():
        return {}

    env: dict[str, str] = {}
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env[key] = value
    return env


class Settings:
    """Combined view of ``config.yaml`` and process/dotenv environment."""

    def __init__(self, config: Config, env: dict[str, str]) -> None:
        self.config = config
        self.env = env

    def get(self, key: str, default: str | None = None) -> str | None:
        """Resolve a secret from the process environment first, then ``.env``."""
        return os.environ.get(key) or self.env.get(key, default)


_settings: Settings | None = None


def get_settings(
    config_path: str | Path = "config.yaml",
    env_path: str | Path = ".env",
    *,
    reload: bool = False,
) -> Settings:
    """Return a cached :class:`Settings`, loading it on first use."""
    global _settings
    if _settings is None or reload:
        _settings = Settings(load_config(config_path), load_env(env_path))
    return _settings


def preflight(require_elevenlabs: bool = False, settings: Settings | None = None) -> None:
    """Validate the runtime before a stage runs (PRD §12).

    - ``ffmpeg`` must be on PATH (hard error with install hint).
    - ``ANTHROPIC_API_KEY`` is a soft warning if unresolved: an active ``ant`` CLI
      profile can still authorize calls, so absence is not fatal here.
    - ``ELEVENLABS_API_KEY`` is a hard error when ``require_elevenlabs`` is set.

    Never prints or raises key values.
    """
    if settings is None:
        settings = get_settings()

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg not found on PATH. Install it and retry:\n"
            "  macOS:  brew install ffmpeg\n"
            "  Debian: sudo apt-get install ffmpeg"
        )

    if not settings.get("ANTHROPIC_API_KEY"):
        print(
            "warning: ANTHROPIC_API_KEY not set in env or .env; "
            "relying on an active Anthropic CLI profile."
        )

    if require_elevenlabs and not settings.get("ELEVENLABS_API_KEY"):
        raise RuntimeError(
            "ELEVENLABS_API_KEY is required for rendering but was not found in env or .env. "
            "Add it to .env (ELEVENLABS_API_KEY=...)."
        )
