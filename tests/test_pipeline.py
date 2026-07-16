from pathlib import Path

from zonecast.pipeline import (
    STAGES,
    Stage,
    ensure_episode_dirs,
    episode_id,
    first_incomplete,
    is_complete,
    mark_complete,
)


def test_episode_id_slug_format() -> None:
    assert episode_id("How Transformers Work", "2026-07-16") == "2026-07-16-how-transformers-work"


def test_episode_id_collapses_punctuation() -> None:
    assert episode_id("CRISPR: base-editing!!", "2026-07-16") == "2026-07-16-crispr-base-editing"


def test_ensure_episode_dirs_creates_layout(tmp_path: Path) -> None:
    ep = tmp_path / "2026-07-16-topic"
    ensure_episode_dirs(ep)
    for sub in ("source", "draft", "script", "audio", ".stages"):
        assert (ep / sub).is_dir()


def test_marker_roundtrip(tmp_path: Path) -> None:
    ep = tmp_path / "ep"
    ensure_episode_dirs(ep)
    assert not is_complete(ep, Stage.ingest)
    mark_complete(ep, Stage.ingest)
    assert is_complete(ep, Stage.ingest)


def test_mark_complete_accepts_string_stage(tmp_path: Path) -> None:
    ep = tmp_path / "ep"
    ensure_episode_dirs(ep)
    mark_complete(ep, "plan")
    assert is_complete(ep, "plan")
    assert is_complete(ep, Stage.plan)


def test_first_incomplete_scans_in_order(tmp_path: Path) -> None:
    ep = tmp_path / "ep"
    ensure_episode_dirs(ep)
    assert first_incomplete(ep) is Stage.ingest
    mark_complete(ep, Stage.ingest)
    mark_complete(ep, Stage.plan)
    assert first_incomplete(ep) is Stage.blueprint


def test_first_incomplete_none_when_all_done(tmp_path: Path) -> None:
    ep = tmp_path / "ep"
    ensure_episode_dirs(ep)
    for stage in STAGES:
        mark_complete(ep, stage)
    assert first_incomplete(ep) is None


def test_stage_order() -> None:
    assert [s.value for s in STAGES] == [
        "ingest",
        "plan",
        "blueprint",
        "generate",
        "polish",
        "render",
        "package",
        "publish",
    ]
