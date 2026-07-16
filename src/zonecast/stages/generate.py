"""Stage 4 — section-by-section drafting (PRD FR-5, SKILL Pass 3).

Walks the blueprint's sections IN ORDER. Each section is drafted with one prose call
(``llm.text``) whose user message carries the whole arc (title, driving question, spine
analogy + its concept→analog mapping — never dropped, FR-5), this section's spec, the FULL
text of the previous section (voice continuity), and the running STATE block. A second small
structured call refreshes the :class:`StateBlock` that threads continuity and callbacks into
the next section (SKILL Pass 3).

Every section is persisted to ``draft/section-NN.md`` and its STATE to ``draft/state-NN.json``
*immediately* after generation, so a killed run resumes without re-billing finished sections
(FR-5 / RES-01). Budget is enforced on **spoken words only** (FR-5a) — measuring the raw file
inflates the count by ~15% (speaker tags, STATE comments, markers) and silently misses the
contract, the exact bug that hid a −24.5% beat in the hand-run test.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..pipeline import Stage, mark_complete
from ..prompt import build_system
from ..schemas import Blueprint, Offer, Section, StateBlock
from ..text import spoken_word_count

if TYPE_CHECKING:
    from . import StageContext

_log = logging.getLogger(__name__)

_BLUEPRINT_PATH = "blueprint/blueprint.json"
_OFFER_PATH = "plan/offer.json"

# Generous headroom: adaptive thinking tokens share the max_tokens budget with the ~1,200-word
# (~1,600-token) section prose, and >8,192 routes llm.text through the streaming path (long
# outputs would otherwise risk the non-streaming timeout).
_GENERATE_MAX_TOKENS = 16_000


def _section_path(n: int) -> str:
    return f"draft/section-{n:02d}.md"


def _state_path(n: int) -> str:
    return f"draft/state-{n:02d}.json"


def run(ctx: "StageContext") -> None:
    bp = Blueprint.model_validate(ctx.read_json(_BLUEPRINT_PATH))
    offer = Offer.model_validate(ctx.read_json(_OFFER_PATH))
    system = build_system("generate", settings=ctx.settings)
    script_cfg = ctx.settings.config.script
    target_words = offer.duration_min * script_cfg.wpm
    tolerance = script_cfg.budget_tolerance_pct / 100

    state: StateBlock | None = None
    prev_text = ""  # full text of the previous section; empty for section 1
    words_spent = 0

    for section in bp.sections:
        spath = _section_path(section.n)
        stpath = _state_path(section.n)

        # Resume: a section whose draft already exists is finished work — reload it as the
        # previous-section context (and its STATE) and never re-bill it (FR-5).
        if ctx.exists(spath):
            prev_text = ctx.read_text(spath)
            words_spent += spoken_word_count(prev_text)
            if ctx.exists(stpath):
                state = StateBlock.model_validate(ctx.read_json(stpath))
            continue

        prose = _draft_section(ctx, system, bp, offer, section, prev_text, state, tolerance)
        # Persist the section BEFORE the state call so a crash between the two still leaves the
        # (expensive) prose on disk for resume.
        ctx.write_text(spath, prose)
        words_spent += spoken_word_count(prose)

        state = _update_state(ctx, system, bp, section, prose, state, words_spent, target_words)
        ctx.write_json(stpath, state)
        prev_text = prose

    mark_complete(ctx.episode_dir, Stage.generate)


def _draft_section(
    ctx: "StageContext",
    system: list,
    bp: Blueprint,
    offer: Offer,
    section: Section,
    prev_text: str,
    state: StateBlock | None,
    tolerance: float,
) -> str:
    """Draft one section, with a single corrective retry if it lands outside the spoken-word
    budget tolerance. After the one retry the result is accepted and a warning is logged —
    generation never blocks the pipeline on an off-budget beat (FR-5)."""
    user = _build_draft_user(bp, offer, section, prev_text, state)
    prose = ctx.llm.text("generate", system, user, max_tokens=_GENERATE_MAX_TOKENS)

    deviation = _budget_deviation(prose, section.word_budget)
    if deviation <= tolerance:
        return prose

    spoken = spoken_word_count(prose)
    retry_user = user + (
        f"\n\nYour draft was {spoken} spoken words against a {section.word_budget}-word budget "
        f"({deviation * 100:.0f}% off). Redraft this same section to hit ~{section.word_budget} "
        "spoken words — adjust scope, not prose density (dense prose is unlistenable). Count "
        "spoken words only: speaker tags, [PAUSE] markers, and headers do not count."
    )
    retried = ctx.llm.text("generate", system, retry_user, max_tokens=_GENERATE_MAX_TOKENS)

    final_dev = _budget_deviation(retried, section.word_budget)
    if final_dev > tolerance:
        _log.warning(
            "section %d still %.0f%% off budget (%d spoken vs %d) after one corrective retry; "
            "accepting",
            section.n,
            final_dev * 100,
            spoken_word_count(retried),
            section.word_budget,
        )
    return retried


def _budget_deviation(markdown: str, word_budget: int) -> float:
    """Fractional deviation of the section's spoken-word count from its budget (FR-5a)."""
    if word_budget <= 0:
        return 0.0
    return abs(spoken_word_count(markdown) - word_budget) / word_budget


def _update_state(
    ctx: "StageContext",
    system: list,
    bp: Blueprint,
    section: Section,
    prose: str,
    prev_state: StateBlock | None,
    words_spent: int,
    target_words: int,
) -> StateBlock:
    """Refresh the running STATE block after a section (SKILL Pass 3).

    The narrative fields (concepts, analogies, open loops, callbacks) come from the model; the
    word counters are overwritten with the deterministic spoken-word tally so continuity budget
    figures can never drift from what was actually written (FR-5a)."""
    user = _build_state_user(bp, section, prose, prev_state)
    state = ctx.llm.structured("generate", system, user, StateBlock)
    return state.model_copy(
        update={
            "after_section": section.n,
            "words_spent": words_spent,
            "words_remaining": max(0, target_words - words_spent),
        }
    )


def _build_draft_user(
    bp: Blueprint,
    offer: Offer,
    section: Section,
    prev_text: str,
    state: StateBlock | None,
) -> str:
    lines = [
        f"Draft section {section.n} of {len(bp.sections)} for this episode, following Pass 3 of "
        "the skill. Write only this section's spoken body.",
        "",
        "Episode arc (hold continuity with the whole thing):",
        f"- Title: {bp.title}",
        f"- Driving question: {bp.driving_question}",
        f"- Duration: {offer.duration_min} min ({offer.depth})",
        "",
        # FR-5 hard rule: the spine analogy and its mapping are injected into EVERY section call
        # so no beat floats free of the metaphor the whole episode maps back onto.
        "Spine analogy — map every abstraction in this section back onto it; never drop it:",
        f"- Image: {bp.spine_analogy.image}",
        "- Mapping (concept -> analog):",
    ]
    lines += [f"    - {concept} -> {analog}" for concept, analog in bp.spine_analogy.mapping.items()]
    lines += ["", "Full section list (for orientation only):"]
    for s in bp.sections:
        here = "  <-- WRITE THIS ONE" if s.n == section.n else ""
        lines.append(f"  {s.n}. {s.name} [{s.word_budget}w] — {s.job}{here}")
    lines += [
        "",
        f"Spec for section {section.n}:",
        f"- Name: {section.name}",
        f"- Job (the one thing it must land): {section.job}",
        f"- Spoken-word budget: {section.word_budget} (count spoken words only)",
        f"- Opens with this tension: {section.opens_with_tension}",
        f"- Resolves/answers by close: {section.closes_opening_tension}",
        f"- Connective into the next section: '{section.connective_to_next}' (never 'and then')",
        f"- Land a recap beat in this section: {'yes' if section.recap_beat else 'no'}",
        "",
    ]
    if prev_text.strip():
        lines += [
            "FULL TEXT of the previous section — match its voice and pick up where it leaves "
            "off; do not repeat it:",
            prev_text.strip(),
            "",
        ]
    else:
        lines += [
            "This is the FIRST section: open the episode with a hook per the style guide "
            "(no preamble, no 'in this episode').",
            "",
        ]
    if state is not None:
        lines += [
            "Current STATE (what the listener already holds — honor open loops and reach for the "
            "available callbacks):",
            state.model_dump_json(indent=2),
            "",
        ]
    lines += [
        "Output ONLY this section's spoken prose. Use [HOST] speaker tags and, sparingly, "
        "[PAUSE:short|long] markers at genuine beats. Do NOT emit the section header, any STATE "
        "block, or metadata. No markdown emphasis (*...* or _..._) — carry emphasis in word "
        "choice, since italics cannot be spoken.",
    ]
    return "\n".join(lines)


def _build_state_user(
    bp: Blueprint,
    section: Section,
    prose: str,
    prev_state: StateBlock | None,
) -> str:
    prior = prev_state.model_dump_json(indent=2) if prev_state else "(none — first section)"
    return "\n".join(
        [
            f"You just drafted section {section.n} ('{section.name}') of the episode "
            f"'{bp.title}'. Update the running STATE block (SKILL Pass 3) that threads continuity "
            "into the next section.",
            "",
            "Previous STATE:",
            prior,
            "",
            "The section you just wrote:",
            prose.strip(),
            "",
            "Produce the updated StateBlock: accumulate concepts_established and live_analogies; "
            "move now-answered questions out of open_loops and add newly opened ones; list every "
            "callback_available (image, phrase, or joke planted so far). The word counters "
            "(words_spent / words_remaining) are recomputed by the pipeline, so approximate them.",
        ]
    )
