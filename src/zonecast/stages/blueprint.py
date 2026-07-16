"""Stage 3 — the blueprint (PRD FR-4, SKILL Pass 2).

One structured LLM call turns the chosen offer + source bundle into a section-by-section
Blueprint. The result is validated against the duration-scoped section bands and the ±10%
budget-sum contract; a single corrective retry is issued with the specific violations before
giving up (and persisting the rejected blueprint for inspection, §12).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import ScriptConfig
from ..pipeline import Stage, mark_complete
from ..prompt import build_system
from ..schemas import Blueprint, Offer
from . import read_source_bundle

if TYPE_CHECKING:
    from . import StageContext

_BLUEPRINT_PATH = "blueprint/blueprint.json"
_REJECTED_PATH = "blueprint/blueprint.rejected.json"

# Budget sum must land within this fraction of duration_min × wpm (FR-4).
_BUDGET_TOLERANCE = 0.10


def section_band(duration_min: int, script_cfg: ScriptConfig) -> tuple[int, int]:
    """Return the (lo, hi) per-section spoken-word band for ``duration_min`` (FR-4).

    Overview episodes (``duration_min <= overview_max_duration_min``, default 20) use the small
    beat band; everything longer — including the 21–29 min gap — uses the standard section band.
    The 800-word standard floor is arithmetically impossible inside a ~2,250-word overview, which
    is exactly why the band is duration-scoped. Phase 3/4 reuse this helper for enforcement.
    """
    if duration_min <= script_cfg.overview_max_duration_min:
        return (script_cfg.overview_beat_words_min, script_cfg.overview_beat_words_max)
    return (script_cfg.section_words_min, script_cfg.section_words_max)


def validate_blueprint(bp: Blueprint, offer: Offer, script_cfg: ScriptConfig) -> list[str]:
    """Return a list of human-readable validation violations (empty == valid)."""
    violations: list[str] = []
    if not bp.sections:
        return ["blueprint has no sections"]

    lo, hi = section_band(offer.duration_min, script_cfg)
    for s in bp.sections:
        if not (lo <= s.word_budget <= hi):
            violations.append(
                f"section {s.n} ('{s.name}') word_budget {s.word_budget} is outside the "
                f"[{lo}, {hi}] band for a {offer.duration_min}-minute episode"
            )
        # Schema already restricts the type to but/therefore; assert the chain is present so a
        # malformed-but-parseable value can't slip through (FR-4).
        if s.connective_to_next not in ("but", "therefore"):
            violations.append(
                f"section {s.n} connective_to_next '{s.connective_to_next}' must be "
                "'but' or 'therefore', never 'and then'"
            )

    total = sum(s.word_budget for s in bp.sections)
    target = offer.duration_min * script_cfg.wpm
    tol = target * _BUDGET_TOLERANCE
    if abs(total - target) > tol:
        violations.append(
            f"section budgets sum to {total} words; must be within ±{int(_BUDGET_TOLERANCE * 100)}% "
            f"of {target} (i.e. {int(target - tol)}–{int(target + tol)})"
        )
    return violations


def run(ctx: "StageContext") -> None:
    offer = Offer.model_validate(ctx.read_json("plan/offer.json"))
    system = build_system("blueprint", settings=ctx.settings)
    base_user = _build_user(ctx, offer)
    script_cfg = ctx.settings.config.script

    user = base_user
    violations: list[str] = []
    # Initial attempt + one corrective retry (FR-4).
    for _ in range(2):
        bp = ctx.llm.structured("blueprint", system, user, Blueprint)
        violations = validate_blueprint(bp, offer, script_cfg)
        if not violations:
            ctx.write_json(_BLUEPRINT_PATH, bp)
            mark_complete(ctx.episode_dir, Stage.blueprint)
            return
        user = base_user + "\n\nYour previous blueprint was rejected. Fix these problems:\n" + "\n".join(
            f"- {v}" for v in violations
        )

    # Persist the last rejected blueprint for inspection before failing loudly (§12).
    ctx.write_json(_REJECTED_PATH, bp)
    raise ValueError(
        "blueprint failed validation after one corrective retry:\n"
        + "\n".join(f"- {v}" for v in violations)
        + f"\nRejected blueprint saved to {ctx.episode_dir / _REJECTED_PATH}"
    )


def _build_user(ctx: "StageContext", offer: Offer) -> str:
    bundle = read_source_bundle(ctx)
    lo, hi = section_band(offer.duration_min, ctx.settings.config.script)
    target = offer.duration_min * ctx.settings.config.script.wpm
    return "\n".join(
        [
            "Turn this chosen offer into a section-by-section blueprint per Pass 2 of the skill: "
            "an ordered list of sections (each with one job, a spoken-word budget, its opening and "
            "closing tension, a but/therefore connective to the next, and a recap-beat flag), plus "
            "the spine analogy and its explicit concept→analog mapping.",
            "",
            "Chosen offer:",
            offer.model_dump_json(indent=2),
            "",
            "Hard budget constraints:",
            f"- This is a {offer.duration_min}-minute episode: each section's word_budget must be "
            f"between {lo} and {hi} spoken words.",
            f"- The section word_budgets must sum to within ±10% of {target} words "
            f"({offer.duration_min} min × {ctx.settings.config.script.wpm} wpm).",
            "- Every section's connective_to_next is 'but' or 'therefore', never 'and then'.",
            "",
            bundle,
        ]
    )
