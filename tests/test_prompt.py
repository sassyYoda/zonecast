from pathlib import Path

import pytest

from zonecast.config import Config, Settings, load_config
from zonecast.prompt import build_system, stage_files

REPO_ROOT = Path(__file__).resolve().parent.parent

# Distinctive on-disk sentences; if these appear in the assembled prompt, the files were
# genuinely read from disk (not hard-coded).
SKILL_MARKER = "motivation is the bottleneck, not explanation quality"
STYLE_GUIDE_MARKER = "Style Guide: Distilled Craft of the Great Explainers"
TTS_MARKER = "TTS Production Reference"
LISTENER_MARKER = "Listener Profile"


@pytest.fixture
def settings() -> Settings:
    cfg: Config = load_config(REPO_ROOT / "config.yaml")
    # Absolute paths so tests don't depend on the process cwd.
    cfg.paths.skill_dir = str(REPO_ROOT / cfg.paths.skill_dir)
    cfg.paths.styles_dir = str(REPO_ROOT / cfg.paths.styles_dir)
    return Settings(cfg, {})


def _texts(blocks: list[dict]) -> str:
    return "\n".join(b["text"] for b in blocks)


def _cache_markers(blocks: list[dict]) -> list[dict]:
    return [b for b in blocks if "cache_control" in b]


def test_blueprint_includes_skill_listener_and_style_guide(settings: Settings) -> None:
    blocks = build_system("blueprint", settings=settings)
    joined = _texts(blocks)
    assert SKILL_MARKER in joined  # proves disk load of SKILL.md
    assert LISTENER_MARKER in joined
    assert STYLE_GUIDE_MARKER in joined


def test_blueprint_has_exactly_one_cache_marker_on_last_stable_block(settings: Settings) -> None:
    blocks = build_system("blueprint", settings=settings)
    markers = _cache_markers(blocks)
    assert len(markers) == 1
    assert markers[0]["cache_control"] == {"type": "ephemeral"}
    # Last stable block is the style guide.
    assert STYLE_GUIDE_MARKER in markers[0]["text"]


def test_ingest_excludes_style_guide(settings: Settings) -> None:
    blocks = build_system("ingest", settings=settings)
    joined = _texts(blocks)
    assert SKILL_MARKER in joined
    assert LISTENER_MARKER in joined
    assert STYLE_GUIDE_MARKER not in joined
    # Marker falls on listener (last stable present for a non-style stage).
    markers = _cache_markers(blocks)
    assert len(markers) == 1
    assert LISTENER_MARKER in markers[0]["text"]


def test_render_includes_tts_production_not_style_guide(settings: Settings) -> None:
    blocks = build_system("render", settings=settings)
    joined = _texts(blocks)
    assert TTS_MARKER in joined
    assert STYLE_GUIDE_MARKER not in joined
    assert len(_cache_markers(blocks)) == 1


def test_style_file_appended_when_present(settings: Settings, tmp_path: Path) -> None:
    style = tmp_path / "ml-theory.md"
    style.write_text("# Field addendum: canonical analogies for ML theory\n")
    blocks = build_system("blueprint", style_file=str(style), settings=settings)
    joined = _texts(blocks)
    assert "canonical analogies for ML theory" in joined
    # Cache marker stays on the stable prefix, not the appended field file.
    assert STYLE_GUIDE_MARKER in _cache_markers(blocks)[0]["text"]


def test_missing_style_file_is_tolerated(settings: Settings) -> None:
    # Nullable through M1–M3: a bogus path must not raise.
    blocks = build_system("blueprint", style_file="does-not-exist", settings=settings)
    assert STYLE_GUIDE_MARKER in _texts(blocks)


def test_stage_files_lists_used_paths(settings: Settings) -> None:
    files = stage_files("blueprint", settings=settings)
    names = [p.name for p in files]
    assert names == ["SKILL.md", "listener.md", "style-guide.md"]
    render_names = [p.name for p in stage_files("render", settings=settings)]
    assert "tts-production.md" in render_names
    assert "style-guide.md" not in render_names
