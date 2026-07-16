import shutil
from pathlib import Path

import pytest

from zonecast.config import Config, Settings, load_config, load_env, preflight

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_load_env_strips_double_quotes(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text('KEY="abc"\n')
    assert load_env(p) == {"KEY": "abc"}


def test_load_env_strips_single_quotes(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text("KEY='abc'\n")
    assert load_env(p) == {"KEY": "abc"}


def test_load_env_strips_trailing_whitespace(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text("KEY=abc \n")
    assert load_env(p) == {"KEY": "abc"}


def test_load_env_ignores_comments_and_blanks(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text("# comment\n\nA=1\nB = two \n")
    assert load_env(p) == {"A": "1", "B": "two"}


def test_load_env_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_env(tmp_path / "nope.env") == {}


def test_load_env_preserves_inner_quotes(tmp_path: Path) -> None:
    # Only *surrounding* matching quotes are stripped.
    p = tmp_path / ".env"
    p.write_text('KEY=ab"cd\n')
    assert load_env(p) == {"KEY": 'ab"cd'}


def test_config_yaml_loads_and_validates() -> None:
    cfg = load_config(REPO_ROOT / "config.yaml")
    assert isinstance(cfg, Config)
    assert cfg.script.wpm == 150
    assert cfg.tts.model == "eleven_multilingual_v2"
    assert cfg.script.overview_beat_words_min == 350
    assert cfg.paths.skill_dir == "prompts/skills/explainer-podcast"


def test_preflight_passes_when_ffmpeg_present(monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("ffmpeg") is None:
        monkeypatch.setattr("zonecast.config.shutil.which", lambda name: "/usr/bin/ffmpeg")
    # ANTHROPIC absent is a soft warning; require_elevenlabs defaults False -> no raise.
    preflight()


def test_preflight_raises_when_ffmpeg_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zonecast.config.shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        preflight()


def test_preflight_requires_elevenlabs_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zonecast.config.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    empty = Settings(load_config(REPO_ROOT / "config.yaml"), {})
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
        preflight(require_elevenlabs=True, settings=empty)
