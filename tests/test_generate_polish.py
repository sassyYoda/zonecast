"""Tests for the phase-2b stages: generate (FR-5/FR-5a) and polish (FR-6).

No real API calls — the LLM client is a recording fake returning canned section prose and
StateBlocks. The assertions pin the contract that matters: spoken-word budget enforcement,
STATE threading, immediate per-section persistence + resume, overlapping polish windows, and
a clean deliverable (no STATE comments, no surviving emphasis markers).
"""

from __future__ import annotations

import re
from pathlib import Path

from zonecast.config import Config, Settings, load_config
from zonecast.pipeline import Stage, ensure_episode_dirs, is_complete
from zonecast.schemas import Blueprint, Offer, Section, SpineAnalogy, StateBlock
from zonecast.stages import CreateArgs, StageContext

REPO_ROOT = Path(__file__).resolve().parent.parent


def _settings() -> Settings:
    cfg: Config = load_config(REPO_ROOT / "config.yaml")
    return Settings(cfg, {})


# --- recording fake LLM -------------------------------------------------------------------


class RecordingLLM:
    """Records every text/structured call and returns queued or callable responses.

    ``text_fn(stage, user, call_index) -> str`` produces section prose (generate) or windowed
    polish output; ``state`` is returned for every StateBlock structured call.
    """

    def __init__(self, text_fn, state: StateBlock | None = None) -> None:
        self._text_fn = text_fn
        self._state = state or StateBlock(
            after_section=0, concepts_established=[], live_analogies=[],
            open_loops=[], callbacks_available=[], words_spent=0, words_remaining=0,
        )
        self.text_calls: list[dict] = []
        self.structured_calls: list[dict] = []

    def text(self, stage, system_blocks, user, **kw):  # noqa: ANN001
        idx = len(self.text_calls)
        self.text_calls.append({"stage": stage, "user": user, "kw": kw})
        return self._text_fn(stage, user, idx)

    def structured(self, stage, system_blocks, user, response_model, **kw):  # noqa: ANN001
        self.structured_calls.append({"stage": stage, "user": user, "model": response_model})
        return self._state


# --- fixtures -----------------------------------------------------------------------------


def _section(n: int, budget: int = 750) -> Section:
    return Section(
        n=n, name=f"s{n}", job=f"job{n}", word_budget=budget,
        opens_with_tension="open", closes_opening_tension="close",
        connective_to_next="therefore", recap_beat=True,
    )


def _blueprint(n_sections: int, budget: int = 750) -> Blueprint:
    return Blueprint(
        offer_id=1, title="The Title", driving_question="how?",
        spine_analogy=SpineAnalogy(image="a vandal and a restorer", mapping={"noise": "grime"}),
        sections=[_section(i + 1, budget) for i in range(n_sections)],
    )


def _offer(duration: int = 15) -> Offer:
    return Offer(
        id=1, duration_min=duration, word_budget=duration * 150, depth="overview",
        driving_question="how?", outline_preview=["a"], deliberately_excluded=["x"],
        format_recommendation="solo", style_file=None,
    )


def _ctx(tmp_path: Path, llm, sections: int = 3, budget: int = 750, duration: int = 15) -> StageContext:
    ep = tmp_path / "ep"
    ensure_episode_dirs(ep)
    ctx = StageContext(episode_dir=ep, settings=_settings(), llm=llm, args=CreateArgs(topic="t"))
    ctx.write_json("blueprint/blueprint.json", _blueprint(sections, budget))
    ctx.write_json("plan/offer.json", _offer(duration))
    return ctx


def _prose(words: int) -> str:
    """A section body whose SPOKEN word count is exactly ``words`` — but padded with a STATE
    comment and a speaker tag that a raw len() would wrongly count."""
    return "[HOST] <!-- STATE junk that must not be counted --> " + " ".join(["word"] * words)


# --- generate: persistence + ordering -----------------------------------------------------


def test_generate_persists_each_section_and_state_in_order(tmp_path: Path) -> None:
    import zonecast.stages.generate as generate

    llm = RecordingLLM(lambda stage, user, i: _prose(750))
    ctx = _ctx(tmp_path, llm, sections=3)
    generate.run(ctx)

    for n in (1, 2, 3):
        assert ctx.exists(f"draft/section-{n:02d}.md")
        assert ctx.exists(f"draft/state-{n:02d}.json")
    # STATE word counters are recomputed deterministically from spoken words (750/section).
    st2 = StateBlock.model_validate(ctx.read_json("draft/state-02.json"))
    assert st2.after_section == 2
    assert st2.words_spent == 1500
    assert st2.words_remaining == 2250 - 1500
    assert is_complete(ctx.episode_dir, Stage.generate)


def test_generate_threads_previous_section_and_state(tmp_path: Path) -> None:
    import zonecast.stages.generate as generate

    # Give each section unique, findable prose so we can prove section 2 saw section 1's text.
    def text_fn(stage, user, i):
        return f"[HOST] UNIQUE_SECTION_MARKER_{i} " + " ".join(["word"] * 750)

    llm = RecordingLLM(text_fn)
    ctx = _ctx(tmp_path, llm, sections=3)
    generate.run(ctx)

    # text calls interleave: draft-1 (i0), draft-2 (i2), draft-3 (i4) — state calls are structured.
    draft_users = [c["user"] for c in llm.text_calls]
    # Section 2's draft prompt must contain the FULL previous section text (from call i0).
    assert "UNIQUE_SECTION_MARKER_0" in draft_users[1]
    # ...and the spine analogy mapping is injected into EVERY section call (FR-5 hard rule).
    for u in draft_users:
        assert "a vandal and a restorer" in u
        assert "noise -> grime" in u
    # Section 1 has no previous text; section 2 receives a serialized STATE block.
    assert "FIRST section" in draft_users[0]
    assert "Current STATE" in draft_users[1]


# --- generate: FR-5a spoken-word budget ---------------------------------------------------


def test_generate_measures_spoken_words_not_raw_len(tmp_path: Path) -> None:
    import zonecast.stages.generate as generate

    # Raw string is thousands of chars, but spoken count is exactly 750 == budget -> NO retry.
    llm = RecordingLLM(lambda stage, user, i: _prose(750))
    ctx = _ctx(tmp_path, llm, sections=1, budget=750)
    generate.run(ctx)

    # One draft call + zero corrective retries (padding did not fool the budget check).
    assert len(llm.text_calls) == 1


def test_generate_offbudget_section_triggers_exactly_one_retry(tmp_path: Path) -> None:
    import zonecast.stages.generate as generate

    # 500 spoken words vs a 750 budget == 33% under (> 20% tolerance) -> exactly one retry.
    calls: list[int] = []

    def text_fn(stage, user, i):
        calls.append(i)
        return _prose(500)

    llm = RecordingLLM(text_fn)
    ctx = _ctx(tmp_path, llm, sections=1, budget=750)
    generate.run(ctx)

    # Draft + one corrective retry only — never an infinite budget loop.
    assert len(llm.text_calls) == 2
    assert "off)" in llm.text_calls[1]["user"]  # the deviation is stated back to the model


# --- generate: resume ---------------------------------------------------------------------


def test_generate_resume_skips_written_section(tmp_path: Path) -> None:
    import zonecast.stages.generate as generate

    llm = RecordingLLM(lambda stage, user, i: _prose(750))
    ctx = _ctx(tmp_path, llm, sections=3)
    # Section 1 already drafted on a previous (killed) run — must not be re-billed.
    ctx.write_text("draft/section-01.md", _prose(750))
    ctx.write_json("draft/state-01.json", StateBlock(
        after_section=1, concepts_established=["c"], live_analogies=[],
        open_loops=[], callbacks_available=[], words_spent=750, words_remaining=1500,
    ))

    generate.run(ctx)

    # Only sections 2 and 3 draft-called (2 text calls), never section 1.
    assert len(llm.text_calls) == 2
    # Section 2's prompt reloaded section 1's persisted text + STATE for continuity.
    assert "words_spent" in llm.text_calls[0]["user"]
    assert is_complete(ctx.episode_dir, Stage.generate)


# --- polish -------------------------------------------------------------------------------


def _run_generate_drafts(ctx: StageContext, sections: int, spoken: int = 750) -> None:
    """Seed draft/section-NN.md as if generate had run, so polish has input."""
    for n in range(1, sections + 1):
        ctx.write_text(f"draft/section-{n:02d}.md", _prose(spoken))


def _polish_text_fn(stage, user, i):
    """Echo each TO-POLISH section back under a header, injecting a stray *emphasis* + STATE
    comment that the polish stage must scrub from the deliverable."""
    owned = re.findall(r"## Section (\d+):.*\(TO POLISH\)", user)
    parts = []
    for n in owned:
        body = (
            f"[HOST] polished section {n} with *italic* emphasis "
            "<!-- STATE leak --> " + " ".join(["word"] * 445)
        )
        parts.append(f"## Section {n}: whatever\n{body}")
    return "\n".join(parts)


def test_polish_windows_overlap(tmp_path: Path) -> None:
    import zonecast.stages.polish as polish

    llm = RecordingLLM(_polish_text_fn)
    # 5 x 450 = 2,250 == 15 min x 150, so the self-check lands in tolerance.
    ctx = _ctx(tmp_path, llm, sections=5, budget=450, duration=15)
    _run_generate_drafts(ctx, 5)
    polish.run(ctx)

    # 5 sections, window 3 / overlap 1 -> windows (1,2,3) then (3,4,5): two calls sharing sec 3.
    assert len(llm.text_calls) == 2
    w0, w1 = llm.text_calls[0]["user"], llm.text_calls[1]["user"]
    # Window 0 polishes 1-3; window 1 polishes 4-5 with section 3 as trailing CONTEXT.
    assert "## Section 1:" in w0 and "## Section 3:" in w0 and "## Section 5:" not in w0
    assert "## Section 5:" in w1 and "## Section 3:" in w1  # <- the overlap section appears in both
    assert "(CONTEXT ONLY)" in w1


def test_polish_writes_clean_final_in_output_format(tmp_path: Path) -> None:
    import zonecast.stages.polish as polish

    llm = RecordingLLM(_polish_text_fn)
    ctx = _ctx(tmp_path, llm, sections=5, budget=450, duration=15)
    _run_generate_drafts(ctx, 5)
    polish.run(ctx)

    final = ctx.read_text("script/final.md")
    # Output format: metadata header block + canonical section headers.
    assert final.startswith("# The Title")
    assert "**Driving question:** how?" in final
    assert "**Spine analogy:** a vandal and a restorer" in final
    assert "**Duration target:** 15 min (~2,250 words) | **Format:** solo" in final
    for n in range(1, 6):
        assert f"## Section {n}: s{n} [~450 words]" in final
    # The deliverable is scrubbed: no STATE comments, no surviving emphasis markers.
    assert "<!--" not in final
    assert "*italic*" not in final
    assert "italic" in final  # the WORD is kept; only the markers were stripped
    # No emphasis markers survive in the spoken text (metadata's **bold** header lines are not
    # spoken and are excluded by spoken_text).
    from zonecast.text import spoken_text

    assert "*" not in spoken_text(final)
    assert is_complete(ctx.episode_dir, Stage.polish)


# --- anti-pattern gates (style-guide §9, lever 2) -----------------------------------------


def test_section_violations_flags_stock_opener_and_missing_build() -> None:
    from zonecast.stages.polish import _section_violations

    stock = "[HOST] Here's a thing that shouldn't be possible. It works. You ask. It answers."
    assert any("stock opener" in v for v in _section_violations(stock))

    short_only = "[HOST] It works. You ask it. It answers you. It never stored a thing. Neat. Small."
    assert any("long build" in v for v in _section_violations(short_only))

    good = (
        "[HOST] Picture a wall of white tiles, thousands of them, and every item you add walks "
        "up and throws a fixed number of darts that each black out one tile wherever a plain hash "
        "rule happens to send them. That's the whole memory. No names anywhere."
    )
    assert _section_violations(good) == []


def test_polish_repairs_a_stock_opener_section(tmp_path: Path) -> None:
    import zonecast.stages.polish as polish

    long_build = (
        "Picture a wall of white tiles, thousands of them, and every item you add walks up and "
        "throws a fixed number of darts that each black out one tile wherever a plain hash rule "
        "sends them, and then leaves without ever writing its name down anywhere at all."
    )

    def text_fn(stage, user, i):  # noqa: ANN001
        if "Problems to fix:" in user:  # the corrective re-polish call
            owned = re.findall(r"## Section (\d+):", user)
            n = owned[0]
            return f"## Section {n}: whatever\n[HOST] {long_build} That's it."
        owned = re.findall(r"## Section (\d+):.*\(TO POLISH\)", user)
        # First pass emits a stock opener and only short sentences -> both gates fail.
        return "\n".join(
            f"## Section {n}: whatever\n[HOST] Here's a thing that shouldn't be possible. "
            "It works. You ask. It answers. Small too." for n in owned
        )

    llm = RecordingLLM(text_fn)
    ctx = _ctx(tmp_path, llm, sections=1, budget=450, duration=3)
    _run_generate_drafts(ctx, 1)
    polish.run(ctx)

    # The window call violated both gates, so exactly one corrective re-polish fired.
    assert any("Problems to fix:" in c["user"] for c in llm.text_calls)
    final = ctx.read_text("script/final.md")
    assert "shouldn't be possible" not in final           # stock opener gone
    assert "throws a fixed number of darts" in final       # the repaired long build landed
