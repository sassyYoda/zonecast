"""Tests for the phase-2 stages: ingest, plan, blueprint, and the run_pipeline dispatcher.

No real API calls — the LLM client is a fake returning canned Offers/Blueprint.
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from zonecast.config import Config, Settings, load_config
from zonecast.pipeline import (
    Stage,
    ensure_episode_dirs,
    is_complete,
    mark_complete,
    run_pipeline,
)
from zonecast.schemas import Blueprint, Offer, Offers, Section, SpineAnalogy
from zonecast.stages import CreateArgs, StageContext
from zonecast.stages.blueprint import section_band, validate_blueprint
from zonecast.stages.plan import select_offer

REPO_ROOT = Path(__file__).resolve().parent.parent


def _settings() -> Settings:
    cfg: Config = load_config(REPO_ROOT / "config.yaml")
    return Settings(cfg, {})


class FakeLLM:
    """Returns queued responses keyed by response_model; records how many calls it saw."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def structured(self, stage, system_blocks, user, response_model, **kw):  # noqa: ANN001
        self.calls += 1
        return self._responses.pop(0)


def _ctx(tmp_path: Path, args: CreateArgs, llm: object | None = None) -> StageContext:
    ep = tmp_path / "ep"
    ensure_episode_dirs(ep)
    return StageContext(episode_dir=ep, settings=_settings(), llm=llm, args=args)


# --- offers/blueprint fixtures ------------------------------------------------------------


def _offers() -> Offers:
    return Offers(
        topic="how transformers work",
        offers=[
            Offer(
                id=1, duration_min=15, word_budget=2250, depth="overview",
                driving_question="q1", outline_preview=["a", "b"],
                deliberately_excluded=["x"], format_recommendation="solo", style_file=None,
            ),
            Offer(
                id=2, duration_min=45, word_budget=6750, depth="standard",
                driving_question="q2", outline_preview=["a", "b"],
                deliberately_excluded=["x"], format_recommendation="solo", style_file=None,
            ),
            Offer(
                id=3, duration_min=120, word_budget=18000, depth="deep",
                driving_question="q3", outline_preview=["a", "b"],
                deliberately_excluded=["x"], format_recommendation="two_host", style_file=None,
            ),
        ],
    )


def _section(n: int, budget: int, conn: str = "therefore") -> Section:
    return Section(
        n=n, name=f"s{n}", job="job", word_budget=budget,
        opens_with_tension="open", closes_opening_tension="close",
        connective_to_next=conn, recap_beat=True,
    )


def _blueprint(budgets: list[int], offer_id: int = 1) -> Blueprint:
    return Blueprint(
        offer_id=offer_id, title="t", driving_question="q",
        spine_analogy=SpineAnalogy(image="a room", mapping={"concept": "analog"}),
        sections=[_section(i + 1, b) for i, b in enumerate(budgets)],
    )


# --- ingest -------------------------------------------------------------------------------


def test_ingest_topic_writes_meta(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, CreateArgs(topic="how transformers work"))
    import zonecast.stages.ingest as ingest

    ingest.run(ctx)
    meta = ctx.read_json("source/meta.json")
    assert meta == {"type": "topic", "ref": "how transformers work", "title": "how transformers work"}
    assert is_complete(ctx.episode_dir, Stage.ingest)


def test_ingest_pdf_extracts_text(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    doc = fitz.open()
    page = doc.new_page()
    # Multi-line so nothing clips off the page width; comfortably over the min-chars threshold.
    body = "\n".join(["Attention is all you need, from the ground up."] * 20)
    page.insert_text((72, 72), body)
    doc.set_metadata({"title": "Attention Paper", "author": "Vaswani et al."})
    doc.save(pdf)
    doc.close()

    ctx = _ctx(tmp_path, CreateArgs(pdf=pdf))
    import zonecast.stages.ingest as ingest

    ingest.run(ctx)
    assert "Attention is all you need" in ctx.read_text("source/paper.md")
    meta = ctx.read_json("source/meta.json")
    assert meta["type"] == "pdf"
    assert meta["title"] == "Attention Paper"


def test_ingest_pdf_empty_raises_actionable(tmp_path: Path) -> None:
    pdf = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page()  # no text
    doc.save(pdf)
    doc.close()

    ctx = _ctx(tmp_path, CreateArgs(pdf=pdf))
    import zonecast.stages.ingest as ingest

    with pytest.raises(ValueError, match="arXiv abstract URL"):
        ingest.run(ctx)


def test_ingest_requires_exactly_one_source(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, CreateArgs(topic="a", url="http://x"))
    import zonecast.stages.ingest as ingest

    with pytest.raises(ValueError, match="exactly one source"):
        ingest.run(ctx)


# --- plan ---------------------------------------------------------------------------------


def test_plan_auto_picks_middle_offer(tmp_path: Path) -> None:
    llm = FakeLLM([_offers()])
    ctx = _ctx(tmp_path, CreateArgs(topic="how transformers work", auto=True), llm=llm)
    ctx.write_json("source/meta.json", {"type": "topic", "ref": "how transformers work", "title": "t"})

    import zonecast.stages.plan as plan

    plan.run(ctx)
    assert ctx.exists("plan/offers.json")
    chosen = ctx.read_json("plan/offer.json")
    assert chosen["id"] == 2  # middle of three
    assert is_complete(ctx.episode_dir, Stage.plan)


def test_plan_reuses_existing_offers_on_resume(tmp_path: Path) -> None:
    # offers.json already on disk -> the planner LLM must not be called again (no re-billing).
    llm = FakeLLM([])  # empty: any call would IndexError
    ctx = _ctx(tmp_path, CreateArgs(topic="t", auto=True), llm=llm)
    ctx.write_json("source/meta.json", {"type": "topic", "ref": "t", "title": "t"})
    ctx.write_json("plan/offers.json", _offers())

    import zonecast.stages.plan as plan

    plan.run(ctx)
    assert llm.calls == 0
    assert ctx.read_json("plan/offer.json")["id"] == 2


def test_select_offer_auto_middle() -> None:
    assert select_offer(_offers(), auto=True).id == 2


# --- blueprint: section_band --------------------------------------------------------------


@pytest.mark.parametrize(
    "duration,expected",
    [
        (15, (350, 1000)),   # overview band
        (20, (350, 1000)),   # boundary: still overview
        (25, (800, 1200)),   # 21-29 takes the standard band
        (45, (800, 1200)),   # standard
        (120, (800, 1200)),  # standard
    ],
)
def test_section_band(duration: int, expected: tuple[int, int]) -> None:
    assert section_band(duration, _settings().config.script) == expected


# --- blueprint: validation ----------------------------------------------------------------


def test_validate_blueprint_accepts_valid_overview() -> None:
    offer = _offers().offers[0]  # 15 min -> target 2250, band [350,1000]
    bp = _blueprint([750, 750, 750])  # sums to 2250
    assert validate_blueprint(bp, offer, _settings().config.script) == []


def test_validate_blueprint_flags_budget_sum() -> None:
    offer = _offers().offers[0]  # target 2250, tolerance +-225 -> [2025,2475]
    bp = _blueprint([350, 350])  # sums to 700, far under
    violations = validate_blueprint(bp, offer, _settings().config.script)
    assert any("sum" in v for v in violations)


def test_validate_blueprint_flags_out_of_band_section() -> None:
    offer = _offers().offers[0]  # overview band [350,1000]
    bp = _blueprint([1500, 750])  # first section over the 1000 ceiling; sum 2250 is fine
    violations = validate_blueprint(bp, offer, _settings().config.script)
    assert any("band" in v for v in violations)


def test_blueprint_run_retries_then_succeeds(tmp_path: Path) -> None:
    bad = _blueprint([100, 100])   # out of band and under budget
    good = _blueprint([750, 750, 750])
    llm = FakeLLM([bad, good])
    ctx = _ctx(tmp_path, CreateArgs(topic="t", auto=True), llm=llm)
    ctx.write_json("plan/offer.json", _offers().offers[0])
    ctx.write_json("source/meta.json", {"type": "topic", "ref": "t", "title": "t"})

    import zonecast.stages.blueprint as blueprint

    blueprint.run(ctx)
    assert llm.calls == 2  # initial + one corrective retry
    assert ctx.exists("blueprint/blueprint.json")
    assert is_complete(ctx.episode_dir, Stage.blueprint)


def test_blueprint_run_raises_after_retry(tmp_path: Path) -> None:
    bad = _blueprint([100, 100])
    llm = FakeLLM([bad, bad])
    ctx = _ctx(tmp_path, CreateArgs(topic="t", auto=True), llm=llm)
    ctx.write_json("plan/offer.json", _offers().offers[0])
    ctx.write_json("source/meta.json", {"type": "topic", "ref": "t", "title": "t"})

    import zonecast.stages.blueprint as blueprint

    with pytest.raises(ValueError, match="failed validation"):
        blueprint.run(ctx)
    # The rejected blueprint is persisted for inspection (§12).
    assert ctx.exists("blueprint/blueprint.rejected.json")
    assert not is_complete(ctx.episode_dir, Stage.blueprint)


# --- run_pipeline -------------------------------------------------------------------------


def test_run_pipeline_skips_completed_and_runs_rest(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path, CreateArgs(topic="t", auto=True))
    mark_complete(ctx.episode_dir, Stage.ingest)

    called: list[str] = []

    import zonecast.stages.blueprint as blueprint
    import zonecast.stages.ingest as ingest
    import zonecast.stages.plan as plan

    def _fail(_ctx):  # ingest is already complete -> must not run
        raise AssertionError("completed stage was re-run")

    monkeypatch.setattr(ingest, "run", _fail)
    monkeypatch.setattr(plan, "run", lambda _ctx: called.append("plan"))
    monkeypatch.setattr(blueprint, "run", lambda _ctx: called.append("blueprint"))

    run_pipeline(ctx, [Stage.ingest, Stage.plan, Stage.blueprint])
    assert called == ["plan", "blueprint"]


def test_run_pipeline_unimplemented_stage_raises(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, CreateArgs(topic="t"))
    # publish is the first stage not yet built (package landed in phase 3).
    with pytest.raises(NotImplementedError, match="publish"):
        run_pipeline(ctx, [Stage.publish])
