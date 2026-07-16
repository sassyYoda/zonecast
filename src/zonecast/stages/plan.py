"""Stage 2 — planning / the offer (PRD FR-3, SKILL Pass 1).

One structured LLM call turns the source bundle + constraints into 2–3 offers (Offers schema),
persisted to ``plan/offers.json``. The user then picks one (``--auto`` picks the middle offer),
persisted to ``plan/offer.json``. Both writes are idempotent: a resumed run reuses an existing
``plan/offers.json`` rather than re-billing the planner.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer

from ..pipeline import Stage, mark_complete
from ..prompt import build_system
from ..schemas import Offer, Offers
from . import read_source_bundle

if TYPE_CHECKING:
    from . import StageContext

_OFFERS_PATH = "plan/offers.json"
_OFFER_PATH = "plan/offer.json"


def run(ctx: "StageContext") -> None:
    offers = _load_or_generate_offers(ctx)
    chosen = select_offer(offers, ctx.args.auto)
    ctx.write_json(_OFFER_PATH, chosen)
    mark_complete(ctx.episode_dir, Stage.plan)


def _load_or_generate_offers(ctx: "StageContext") -> Offers:
    # Resume safety: never re-pay for offers we already generated (RES-01).
    if ctx.exists(_OFFERS_PATH):
        return Offers.model_validate(ctx.read_json(_OFFERS_PATH))
    system = build_system("plan", settings=ctx.settings)
    user = _build_user(ctx)
    offers = ctx.llm.structured("plan", system, user, Offers)
    ctx.write_json(_OFFERS_PATH, offers)
    return offers


def _build_user(ctx: "StageContext") -> str:
    args = ctx.args
    bundle = read_source_bundle(ctx)
    lines = [
        "Produce 2–3 offers for this source per Pass 1 of the skill. "
        "Each offer states the duration, depth, the driving question it answers, a 4–6 line "
        "outline preview, and what it deliberately leaves out.",
        "",
        bundle,
        "",
        "Constraints:",
    ]
    if args.duration is not None:
        lines.append(
            f"- Target duration is {args.duration} minutes. Make every offer {args.duration} "
            "minutes long; vary depth and angle across the offers, not length."
        )
    elif args.session:
        lines.append(
            f"- Session context: {args.session}. Size the offers to fit this listening window."
        )
    else:
        # Cold start (no duration, no session): span the listener's real session range (FR-3).
        lines.append(
            "- No duration was given. Span the listener's real session range: roughly one "
            "~15-minute overview, one ~45-minute standard episode, and one ~120-minute deep dive "
            "— do not cluster the offers around a single length."
        )
    if args.depth:
        lines.append(f"- Preferred depth: {args.depth}.")
    lines.append(f"- word_budget for each offer is duration_min × {ctx.settings.config.script.wpm}.")
    lines.append(
        "- style_file must be null for every offer: the styles/ library is empty until M4, and "
        "you must never invent a path."
    )
    return "\n".join(lines)


def select_offer(offers: Offers, auto: bool) -> Offer:
    """Pick an offer. ``--auto`` picks the middle offer (SKILL: "pick the middle one if they've
    said just go"); otherwise present the offers and prompt for a number. Interactive prompting
    needs a TTY and is intentionally thin — the middle-offer path is the tested one."""
    if not offers.offers:
        raise ValueError("planner returned no offers")
    if auto:
        return offers.offers[len(offers.offers) // 2]
    return _prompt_selection(offers)


def _prompt_selection(offers: Offers) -> Offer:
    typer.echo(f"\nOffers for: {offers.topic}\n")
    for o in offers.offers:
        typer.echo(f"  [{o.id}] {o.duration_min} min · {o.depth} · {o.driving_question}")
        for beat in o.outline_preview:
            typer.echo(f"        - {beat}")
    valid = {o.id: o for o in offers.offers}
    while True:
        n = typer.prompt("\nPick an offer by number", type=int)
        if n in valid:
            return valid[n]
        typer.echo(f"'{n}' is not one of {sorted(valid)}.", err=True)
