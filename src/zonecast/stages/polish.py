"""Stage 5 — the read-aloud polish (PRD FR-6, SKILL Pass 4).

The assembled section drafts are edited in **overlapping** windows of ~3 sections — a long
script exceeds comfortable single-call editing, and the overlap lets the model see each seam
from both sides so signposting and callbacks stay continuous across window boundaries. Each
window applies the Pass-4 checklist: split >30-word sentences, verify boundary signposting,
prune load-bearing-only humor, enforce the redundancy rule, and — critically — rewrite italic
emphasis into word choice, since italics cannot be spoken and are stripped before TTS.

The polished sections are reassembled under canonical ``## Section N`` headers (drawn from the
blueprint, not the model's output) into ``script/final.md`` in the skill's output format. A
defensive cleanup guarantees no STATE comment or surviving ``*emphasis*`` marker reaches the
deliverable, and a self-check logs the final spoken-word count against the duration contract.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from ..pipeline import Stage, mark_complete
from ..prompt import build_system
from ..schemas import Blueprint, Offer
from ..text import spoken_text, spoken_word_count

if TYPE_CHECKING:
    from . import StageContext

_log = logging.getLogger(__name__)

_BLUEPRINT_PATH = "blueprint/blueprint.json"
_OFFER_PATH = "plan/offer.json"
_FINAL_PATH = "script/final.md"

# Editorial window geometry (SKILL Pass 4): three sections per pass, sharing one boundary
# section with the next window so seams are edited from both sides.
_WINDOW_SIZE = 3
_WINDOW_OVERLAP = 1

# Headroom for adaptive thinking + up to three ~1,200-word sections; >8,192 streams (llm.text).
_POLISH_MAX_TOKENS = 16_000

_SECTION_HEADER = re.compile(r"^##\s*Section\s+(\d+)\b.*$", re.MULTILINE)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# Italics/bold cannot be spoken and must not survive into the deliverable (SKILL Pass 4 /
# FR-5a). Strip the markers, keep the enclosed words — the model should already have rewritten
# the emphasis into word choice; this is the belt-and-suspenders guarantee.
_EMPHASIS = re.compile(r"(\*{1,3}|_{1,3})(.+?)\1", re.DOTALL)


def run(ctx: "StageContext") -> None:
    bp = Blueprint.model_validate(ctx.read_json(_BLUEPRINT_PATH))
    offer = Offer.model_validate(ctx.read_json(_OFFER_PATH))
    drafts = _load_drafts(ctx, bp)
    system = build_system("polish", settings=ctx.settings)

    polished: dict[int, str] = {}
    stripped_emphasis = 0
    done: set[int] = set()
    for start, end in _windows(len(bp.sections)):
        owned = [n for n in range(start, end + 1) if n not in done]
        context = [n for n in range(start, end + 1) if n in done]
        user = _build_window_user(bp, drafts, owned, context)
        out = ctx.llm.text("polish", system, user, max_tokens=_POLISH_MAX_TOKENS)

        for n, body in _parse_sections(out).items():
            if n not in owned:
                continue  # a re-emitted context section — the earlier window owns it
            clean, hits = _clean_body(body)
            polished[n] = clean
            stripped_emphasis += hits
        done.update(owned)

    _assemble_and_write(ctx, bp, offer, polished, stripped_emphasis)
    mark_complete(ctx.episode_dir, Stage.polish)


def _load_drafts(ctx: "StageContext", bp: Blueprint) -> dict[int, str]:
    """Read every section draft produced by the generate stage, keyed by section number."""
    drafts: dict[int, str] = {}
    for section in bp.sections:
        rel = f"draft/section-{section.n:02d}.md"
        if not ctx.exists(rel):
            raise FileNotFoundError(
                f"polish: missing {rel}; run the generate stage first (it produces the drafts "
                "this stage edits)."
            )
        drafts[section.n] = ctx.read_text(rel)
    return drafts


def _windows(n_sections: int) -> list[tuple[int, int]]:
    """Overlapping (start, end) 1-based section ranges covering all sections.

    Windows are ``_WINDOW_SIZE`` wide and step by ``size - overlap``, so consecutive windows
    share ``_WINDOW_OVERLAP`` boundary section(s). Every section is *owned* by exactly one
    window; the shared section is trailing context for the later window.
    """
    step = max(1, _WINDOW_SIZE - _WINDOW_OVERLAP)
    windows: list[tuple[int, int]] = []
    start = 1
    while True:
        end = min(start + _WINDOW_SIZE - 1, n_sections)
        windows.append((start, end))
        if end >= n_sections:
            break
        start += step
    return windows


def _build_window_user(
    bp: Blueprint,
    drafts: dict[int, str],
    owned: list[int],
    context: list[int],
) -> str:
    by_n = {s.n: s for s in bp.sections}
    lines = [
        "Apply the Pass-4 read-aloud polish (SKILL) to the sections marked TO POLISH below.",
        "",
        "Episode context:",
        f"- Title: {bp.title}",
        f"- Driving question: {bp.driving_question}",
        f"- Spine analogy: {bp.spine_analogy.image}",
        "",
        "Polish checklist for each TO-POLISH section:",
        "- Split any sentence past ~30 words; spoken sentences average 15-20 words.",
        "- Verify signposting at every section boundary (announce turns and recaps).",
        "- Humor: keep only dry, load-bearing jokes that land on a concept; cut the rest.",
        "- Redundancy rule: every load-bearing idea restated once, minutes apart, re-derived "
        "from a new angle (not verbatim).",
        "- EMPHASIS: rewrite every italic/bold emphasis into word choice or sentence structure. "
        "Italics cannot be spoken and are stripped before TTS, so no '*...*' or '_..._' may "
        "remain — the contrast must live in the words themselves.",
        "- Hold each section near its spoken-word budget; over budget, cut scope, never compress "
        "prose into density.",
        "",
    ]
    if context:
        lines.append(
            "Already-polished neighbouring section(s) for continuity — do NOT re-output these, "
            "just keep the seam consistent with them:"
        )
        for n in context:
            s = by_n[n]
            lines += [f"## Section {n}: {s.name} [~{s.word_budget} words] (CONTEXT ONLY)", drafts[n].strip(), ""]
    lines.append("Sections TO POLISH:")
    for n in owned:
        s = by_n[n]
        lines += [f"## Section {n}: {s.name} [~{s.word_budget} words] (TO POLISH)", drafts[n].strip(), ""]
    lines += [
        "Output each TO-POLISH section as its polished spoken body under a '## Section N: {name} "
        "[~{budget} words]' header, in ascending order. Keep [HOST] tags and [PAUSE:short|long] "
        "markers. Do NOT include any STATE block/comment, the episode metadata header, or the "
        "CONTEXT-ONLY sections.",
    ]
    return "\n".join(lines)


def _parse_sections(text: str) -> dict[int, str]:
    """Split a polish response into ``{section_number: body}`` by its ``## Section N`` headers."""
    matches = list(_SECTION_HEADER.finditer(text))
    out: dict[int, str] = {}
    for i, m in enumerate(matches):
        n = int(m.group(1))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[n] = text[m.end():end].strip()
    return out


def _clean_body(body: str) -> tuple[str, int]:
    """Strip any surviving STATE comment and emphasis markers; return (clean, markers_removed)."""
    body = _HTML_COMMENT.sub("", body)
    body, hits = _EMPHASIS.subn(r"\2", body)
    return body.strip(), hits


def _assemble_and_write(
    ctx: "StageContext",
    bp: Blueprint,
    offer: Offer,
    polished: dict[int, str],
    stripped_emphasis: int,
) -> None:
    fmt = "two-host" if ctx.args.two_host else "solo"
    target_words = offer.duration_min * ctx.settings.config.script.wpm

    parts = [
        f"# {bp.title}",
        "",
        f"**Driving question:** {bp.driving_question}",
        f"**Duration target:** {offer.duration_min} min (~{target_words:,} words) | "
        f"**Format:** {fmt}",
        f"**Spine analogy:** {bp.spine_analogy.image}",
        "",
    ]
    for section in bp.sections:
        body = polished.get(section.n)
        if body is None:
            raise ValueError(
                f"polish: section {section.n} was never produced by any editing window "
                "(model omitted it from every response)."
            )
        parts += [f"## Section {section.n}: {section.name} [~{section.word_budget} words]", "", body, ""]

    final_md = "\n".join(parts).rstrip() + "\n"
    ctx.write_text(_FINAL_PATH, final_md)

    _self_check(final_md, offer, ctx, stripped_emphasis)


def _self_check(
    final_md: str,
    offer: Offer,
    ctx: "StageContext",
    stripped_emphasis: int,
) -> None:
    """Log the two Pass-4 sanity gates: spoken-word count vs contract, and emphasis survival."""
    script_cfg = ctx.settings.config.script
    target = offer.duration_min * script_cfg.wpm
    tolerance = script_cfg.budget_tolerance_pct / 100
    spoken = spoken_word_count(final_md)
    deviation = abs(spoken - target) / target if target else 0.0

    level = logging.WARNING if deviation > tolerance else logging.INFO
    _log.log(
        level,
        "polish self-check: final.md is %d spoken words vs %d target (%.0f%% off, tolerance "
        "%.0f%%)",
        spoken,
        target,
        deviation * 100,
        tolerance * 100,
    )

    if stripped_emphasis:
        # The model left markers the defensive pass had to strip — flag it, the deliverable is
        # still clean but the polish prompt under-performed.
        _log.warning(
            "polish self-check: stripped %d emphasis marker(s) the model failed to rewrite into "
            "word choice",
            stripped_emphasis,
        )
    survivors = len(_EMPHASIS.findall(spoken_text(final_md)))
    _log.info("polish self-check: %d surviving emphasis marker(s) in the spoken text", survivors)
