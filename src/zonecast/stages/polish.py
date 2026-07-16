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

# Anti-pattern gates enforced deterministically after polish (style-guide §9 / anti-patterns.md).
# The checklist alone doesn't reliably shift these two — they're model defaults — so we scan the
# output and re-polish offending sections once. Stock openers, checked only against a section's
# first words (a generic hook that would fit any topic is the tell; a specific concrete opener
# like "Picture a wall of white tiles" is fine, so we ban the generic phrasings, not "picture").
_BANNED_OPENERS = (
    "here's a thing that shouldn't be possible",
    "here's something that shouldn't be possible",
    "here's the thing",
    "imagine a world",
    "what if i told you",
    "picture this",
    "let me tell you",
    "in a world where",
)
_OPENER_SCAN_CHARS = 140
# Machines avoid the long build; each section needs at least one clause-stacked sentence that
# earns its length, set against short ones (the anti-metronome rule).
_MIN_LONG_BUILD_WORDS = 28
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _section_violations(body: str) -> list[str]:
    """Return anti-pattern gate failures for one polished section body (empty = clean)."""
    spoken = spoken_text(body)
    violations: list[str] = []
    head = spoken[:_OPENER_SCAN_CHARS].lower()
    for opener in _BANNED_OPENERS:
        if opener in head:
            violations.append(
                f"stock opener {opener!r} — a generic hook that fits any topic. Open instead on "
                "the specific concrete image, number, or scene of THIS subject."
            )
            break
    lengths = [len(s.split()) for s in _SENTENCE_SPLIT.split(spoken) if s.strip()]
    if lengths and max(lengths) < _MIN_LONG_BUILD_WORDS:
        violations.append(
            f"no real long build (longest sentence is {max(lengths)} words) — add one genuinely "
            "long, clause-stacked sentence of ~30-40 words that earns its length by walking "
            "through a process or piling up a case, then break to something short."
        )
    return violations


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

    # Deterministic anti-pattern gates (style-guide §9): re-polish any section that opens on a
    # stock hook or lacks a real long build. One corrective round, then accept and log — the same
    # shape as the generate budget retry.
    by_n = {s.n: s for s in bp.sections}
    for n in sorted(polished):
        violations = _section_violations(polished[n])
        if not violations:
            continue
        _log.warning("polish: section %d anti-pattern gate: %s — one corrective re-polish", n, violations)
        retry = ctx.llm.text(
            "polish", system, _build_repair_user(bp, by_n[n], polished[n], violations),
            max_tokens=_POLISH_MAX_TOKENS,
        )
        clean, hits = _clean_body(_parse_sections(retry).get(n, retry))
        polished[n] = clean
        stripped_emphasis += hits
        remaining = _section_violations(clean)
        if remaining:
            _log.warning("polish: section %d still %s after one retry — accepting", n, remaining)

    _assemble_and_write(ctx, bp, offer, polished, stripped_emphasis)
    mark_complete(ctx.episode_dir, Stage.polish)


def _build_repair_user(bp: Blueprint, section, body: str, violations: list[str]) -> str:
    """Prompt to re-polish one section, fixing named anti-pattern violations, content intact."""
    return "\n".join([
        f'This polished section of "{bp.title}" has specific anti-pattern problems. Rewrite ONLY '
        "this section to fix them. Keep the same content and teaching, keep the [HOST] tag and any "
        "[PAUSE:short|long] markers, and stay near the same length.",
        "",
        "Problems to fix:",
        *[f"- {v}" for v in violations],
        "",
        f"## Section {section.n}: {section.name} [~{section.word_budget} words]",
        body.strip(),
        "",
        "Output just the rewritten section body under its '## Section N: ...' header — no episode "
        "metadata, no STATE, no commentary.",
    ])


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
        "- OPENING: never open a section on a generic hook that would fit any topic ('here's a "
        "thing that shouldn't be possible', 'imagine a world', 'picture this', 'what if I told "
        "you'). Open on the specific concrete image, number, or scene of THIS subject.",
        "- RHYTHM: each section must contain at least one genuinely long, clause-stacked sentence "
        "(~30-40 words) that earns its length, set against short ones. Avoid medium-everything and "
        "avoid the long-sentence-then-fragment metronome; see anti-patterns.md.",
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

    # Report any anti-pattern gate that survived the corrective retry, per section.
    residual = {
        n: v
        for n, v in (
            (m.group(1), _section_violations(body))
            for m, body in _iter_section_bodies(final_md)
        )
        if v
    }
    if residual:
        _log.warning("polish self-check: anti-pattern gates still failing after retry: %s", residual)


def _iter_section_bodies(final_md: str):
    """Yield (header_match, body) for each ## Section block in the assembled script."""
    matches = list(_SECTION_HEADER.finditer(final_md))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(final_md)
        yield m, final_md[m.end():end]
