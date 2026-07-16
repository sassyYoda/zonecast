import shutil
from pathlib import Path

from typer.testing import CliRunner

from zonecast.cli import app

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / "prompts" / "skills" / "explainer-podcast" / "references" / "listener.example.md"

runner = CliRunner()


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("create", "resume", "redo", "list", "publish", "profile", "feed"):
        assert cmd in result.output


def test_profile_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["profile", "--help"])
    assert result.exit_code == 0
    assert "init" in result.output
    assert "edit" in result.output


def _tmp_skill_dir(tmp_path: Path) -> Path:
    """A skill dir with only the example present (no listener.md yet)."""
    refs = tmp_path / "references"
    refs.mkdir(parents=True)
    shutil.copyfile(EXAMPLE, refs / "listener.example.md")
    return tmp_path


def test_profile_init_copies_example(tmp_path: Path) -> None:
    skill = _tmp_skill_dir(tmp_path)
    result = runner.invoke(app, ["profile", "init", "--skill-dir", str(skill)])
    assert result.exit_code == 0
    target = skill / "references" / "listener.md"
    assert target.exists()
    assert target.read_text() == EXAMPLE.read_text()


def test_profile_init_is_idempotent(tmp_path: Path) -> None:
    skill = _tmp_skill_dir(tmp_path)
    runner.invoke(app, ["profile", "init", "--skill-dir", str(skill)])
    target = skill / "references" / "listener.md"
    # Simulate the user editing their private profile.
    target.write_text("# my edits\n")
    result = runner.invoke(app, ["profile", "init", "--skill-dir", str(skill)])
    assert result.exit_code == 0
    assert "already exists" in result.output
    # Second run must NOT clobber the user's edits.
    assert target.read_text() == "# my edits\n"


def test_create_prints_plan(tmp_path: Path, monkeypatch) -> None:
    # ffmpeg may be absent in CI; stub the preflight check so create's shell still runs.
    monkeypatch.setattr("zonecast.config.shutil.which", lambda name: "/usr/bin/ffmpeg")
    result = runner.invoke(app, ["create", "how transformers work", "--duration", "15", "--auto"])
    assert result.exit_code == 0
    assert "how-transformers-work" in result.output
    assert "auto" in result.output
