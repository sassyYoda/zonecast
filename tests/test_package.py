"""Tests for the phase-3 packaging half: the ffmpeg helpers (audio.py) and the package stage.

No API and no network — fixtures are real, tiny silent MP3s produced by the installed ffmpeg,
so ``clip_duration_sec``/``stitch`` exercise the actual binaries the pipeline shells out to. The
package stage runs against a hand-built episode dir (clips.json + real clips + blueprint/meta),
asserting the three deliverables exist and that chapter marks and cost accounting are correct.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zonecast import audio
from zonecast.config import Config, Settings, load_config
from zonecast.pipeline import Stage, ensure_episode_dirs, is_complete
from zonecast.schemas import Manifest
from zonecast.stages import CreateArgs, StageContext
from zonecast.stages import package as package_stage

REPO_ROOT = Path(__file__).resolve().parent.parent


def _settings() -> Settings:
    cfg: Config = load_config(REPO_ROOT / "config.yaml")
    return Settings(cfg, {})


def _tiny_clip(path: Path, seconds: float = 1.0) -> Path:
    """A real silent MP3 fixture via the installed ffmpeg."""
    return audio.make_silence(seconds, path)


# --- audio.clip_duration_sec --------------------------------------------------------------


def test_clip_duration_sec_measures_one_second(tmp_path: Path) -> None:
    clip = _tiny_clip(tmp_path / "one.mp3", 1.0)
    assert abs(audio.clip_duration_sec(clip) - 1.0) < 0.15


# --- audio.stitch -------------------------------------------------------------------------


def test_stitch_inserts_silence_at_section_boundary(tmp_path: Path) -> None:
    clips = [
        _tiny_clip(tmp_path / "a.mp3", 1.0),
        _tiny_clip(tmp_path / "b.mp3", 1.0),
        _tiny_clip(tmp_path / "c.mp3", 1.0),
    ]
    out = tmp_path / "episode.mp3"
    # A single section boundary before clip index 2 -> one inserted silence.
    duration = audio.stitch(
        clips, [2], _settings().config, out, {"title": "T", "artist": "Zonecast"}
    )

    assert out.exists()
    clip_total = sum(audio.clip_duration_sec(c) for c in clips)
    # Output is longer than the raw clips by roughly the inserted 1.5s section gap.
    assert duration > clip_total + 0.5
    assert abs(audio.clip_duration_sec(out) - duration) < 0.05


# --- package stage ------------------------------------------------------------------------


class _FakeCosts:
    def totals(self) -> dict[str, int]:
        return {"input_tokens": 1200, "output_tokens": 800}

    def estimate_usd(self) -> float:
        return 0.25


class _FakeLLM:
    costs = _FakeCosts()


def _package_ctx(tmp_path: Path) -> StageContext:
    ep = tmp_path / "2026-07-16-how-transformers-work"
    ensure_episode_dirs(ep)
    ctx = StageContext(
        episode_dir=ep,
        settings=_settings(),
        llm=_FakeLLM(),
        args=CreateArgs(topic="how transformers work", duration=15),
    )

    # Two sections, three clips (section 1 has two clips, section 2 has one).
    clips_dir = ep / "audio" / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for i, secs in enumerate([1.0, 1.0, 1.0]):
        name = f"clip{i}.mp3"
        _tiny_clip(clips_dir / name, secs)
        files.append(name)

    ctx.write_json(
        "audio/clips.json",
        {
            "voice_id": "V",
            "model_id": ctx.settings.config.tts.model,  # eleven_multilingual_v2
            "output_format": "mp3_44100_128",
            "chars_rendered": 5000,
            "sections": [{"n": 1, "name": "Setup"}, {"n": 2, "name": "Payoff"}],
            "clips": [
                {"file": f"clips/{files[0]}", "section": 1, "chars": 2000},
                {"file": f"clips/{files[1]}", "section": 1, "chars": 2000},
                {"file": f"clips/{files[2]}", "section": 2, "chars": 1000},
            ],
        },
    )
    ctx.write_json("blueprint/blueprint.json", {"title": "How Transformers Work"})
    ctx.write_json("source/meta.json", {"type": "topic", "ref": "how transformers work", "title": "x"})
    return ctx


def test_package_stage_produces_deliverables(tmp_path: Path) -> None:
    ctx = _package_ctx(tmp_path)
    package_stage.run(ctx)

    assert ctx.exists("audio/episode.mp3")
    assert ctx.exists("audio/chapters.json")
    assert ctx.exists("manifest.json")
    assert is_complete(ctx.episode_dir, Stage.package)

    # Chapters: one per section, first at 0, strictly increasing, from measured durations.
    chapters = ctx.read_json("audio/chapters.json")["chapters"]
    assert [c["title"] for c in chapters] == ["Setup", "Payoff"]
    assert chapters[0]["startTime"] == 0
    starts = [c["startTime"] for c in chapters]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)
    # Payoff opens after two ~1s clips plus the inserted ~1.3s section silence.
    assert chapters[1]["startTime"] > 2.5


def test_package_manifest_validates_and_accounts_cost(tmp_path: Path) -> None:
    ctx = _package_ctx(tmp_path)
    package_stage.run(ctx)

    manifest = Manifest.model_validate(ctx.read_json("manifest.json"))
    assert manifest.episode_id == "2026-07-16-how-transformers-work"
    assert manifest.title == "How Transformers Work"
    assert manifest.duration_target_min == 15
    assert manifest.duration_actual_sec > 2  # three ~1s clips + a section gap
    assert manifest.format == "solo"
    assert manifest.source.type == "topic"
    assert manifest.files.mp3 == "audio/episode.mp3"

    # Cost: LLM tokens straight from the tracker; TTS chars from clips.json; the estimate is the
    # LLM estimate ($0.25) plus 5000 chars × $0.10/1k = $0.50 for multilingual_v2 -> $0.75.
    assert manifest.costs.llm_input_tokens == 1200
    assert manifest.costs.llm_output_tokens == 800
    assert manifest.costs.tts_characters == 5000
    assert manifest.costs.estimated_usd == pytest.approx(0.75, abs=1e-6)


def test_package_stage_resume_skips_when_outputs_exist(tmp_path: Path) -> None:
    ctx = _package_ctx(tmp_path)
    package_stage.run(ctx)
    mp3 = ctx.episode_dir / "audio" / "episode.mp3"
    stamp = mp3.stat().st_mtime_ns

    # Second run: all three outputs present -> skipped, the mp3 is not re-stitched.
    package_stage.run(ctx)
    assert mp3.stat().st_mtime_ns == stamp
    assert is_complete(ctx.episode_dir, Stage.package)
