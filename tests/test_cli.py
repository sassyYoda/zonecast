import re
import shutil
from pathlib import Path

from typer.testing import CliRunner

from zonecast.cli import app
from zonecast.schemas import Blueprint, Offer, Offers, Section, SpineAnalogy, StateBlock

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


class _FakeCosts:
    def estimate_usd(self) -> float:
        return 0.0


class _FakeLLM:
    """Stands in for LLMClient in the CLI wiring test — never touches the network."""

    def __init__(self, *args, **kwargs) -> None:
        self.costs = _FakeCosts()

    def structured(self, stage, system_blocks, user, response_model, **kw):  # noqa: ANN001
        if response_model is Offers:
            mk = lambda i, d: Offer(  # noqa: E731
                id=i, duration_min=d, word_budget=d * 150, depth="overview",
                driving_question="q", outline_preview=["a"], deliberately_excluded=["x"],
                format_recommendation="solo", style_file=None,
            )
            return Offers(topic="how transformers work", offers=[mk(1, 15), mk(2, 15), mk(3, 15)])
        if response_model is Blueprint:
            sec = lambda n: Section(  # noqa: E731
                n=n, name=f"s{n}", job="job", word_budget=750,
                opens_with_tension="o", closes_opening_tension="c",
                connective_to_next="therefore", recap_beat=True,
            )
            return Blueprint(
                offer_id=2, title="t", driving_question="q",
                spine_analogy=SpineAnalogy(image="room", mapping={"c": "a"}),
                sections=[sec(1), sec(2), sec(3)],  # 3 x 750 = 2250 == 15 min x 150
            )
        if response_model is StateBlock:
            return StateBlock(
                after_section=0, concepts_established=[], live_analogies=[],
                open_loops=[], callbacks_available=[], words_spent=0, words_remaining=0,
            )
        raise AssertionError(f"unexpected response_model {response_model}")

    def text(self, stage, system_blocks, user, **kw):  # noqa: ANN001
        # 750 spoken words/section hits each budget exactly (no corrective retry) and sums to
        # the 2,250-word contract, so the polish self-check stays in tolerance.
        body = "[HOST] " + "word " * 750
        if stage == "generate":
            return body
        if stage == "polish":
            owned = re.findall(r"## Section (\d+):.*\(TO POLISH\)", user)
            return "\n".join(f"## Section {n}: polished\n{body}" for n in owned)
        raise AssertionError(f"unexpected text stage {stage}")


def test_create_runs_pipeline_through_polish(tmp_path: Path, monkeypatch) -> None:
    # ffmpeg may be absent in CI; stub the preflight check so create's shell still runs.
    monkeypatch.setattr("zonecast.config.shutil.which", lambda name: "/usr/bin/ffmpeg")
    # Redirect episode output into tmp and swap in the fake (no-API) LLM client.
    from zonecast.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings.config.paths, "episodes_dir", str(tmp_path))
    monkeypatch.setattr("zonecast.cli.LLMClient", _FakeLLM)

    result = runner.invoke(app, ["create", "how transformers work", "--duration", "15", "--auto"])
    assert result.exit_code == 0, result.output
    assert "how-transformers-work" in result.output
    assert "auto" in result.output

    ep_dirs = list(tmp_path.iterdir())
    assert len(ep_dirs) == 1
    ep = ep_dirs[0]
    assert (ep / "source" / "meta.json").exists()
    assert (ep / "plan" / "offers.json").exists()
    assert (ep / "plan" / "offer.json").exists()
    assert (ep / "blueprint" / "blueprint.json").exists()
    # generate + polish are now wired: drafts, state, and the final script all land.
    assert (ep / "draft" / "section-01.md").exists()
    assert (ep / "draft" / "state-01.json").exists()
    final = ep / "script" / "final.md"
    assert final.exists()
    assert "Script ready" in result.output
    text = final.read_text()
    assert text.startswith("# t")            # metadata title header
    assert "## Section 1: s1" in text        # canonical section headers
    assert "<!--" not in text                # no STATE comments in the deliverable
