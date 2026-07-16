"""Pydantic v2 models mirroring PRD §8 data schemas.

Every model forbids extra fields so they are safe to use as Anthropic structured-output
schemas (``output_config.format``) later. Defaults are avoided where a schema needs to be
unambiguous; genuinely optional fields (per FR-3) are typed ``Optional`` and nullable.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- §8.1 offers.json ---------------------------------------------------------------


class Offer(_Base):
    id: int
    duration_min: int
    word_budget: int
    depth: str
    driving_question: str
    outline_preview: list[str]
    deliberately_excluded: list[str]
    format_recommendation: str
    # Nullable through M1–M3: styles/ is empty at cold start (FR-3). Must be null when no
    # matching style file exists — the planner never invents a path.
    style_file: Optional[str]


class Offers(_Base):
    topic: str
    offers: list[Offer]


# --- §8.2 blueprint.json ------------------------------------------------------------


class SpineAnalogy(_Base):
    image: str
    mapping: dict[str, str]


class Section(_Base):
    n: int
    name: str
    job: str
    word_budget: int
    opens_with_tension: str
    closes_opening_tension: str
    # Reject "and_then" at the type level (FR-4): every section must earn a but/therefore
    # link to the next, never a flat "and then".
    connective_to_next: Literal["but", "therefore"]
    recap_beat: bool


class Blueprint(_Base):
    offer_id: int
    title: str
    driving_question: str
    spine_analogy: SpineAnalogy
    sections: list[Section]


# --- §8.3 state-NN.json -------------------------------------------------------------


class LiveAnalogy(_Base):
    image: str
    maps_to: str


class StateBlock(_Base):
    after_section: int
    concepts_established: list[str]
    live_analogies: list[LiveAnalogy]
    open_loops: list[str]
    callbacks_available: list[str]
    words_spent: int
    words_remaining: int


# --- §8.4 manifest.json -------------------------------------------------------------


class SourceRef(_Base):
    type: Literal["topic", "pdf", "url"]
    ref: str


class Files(_Base):
    mp3: str
    chapters: str
    script: str


class Costs(_Base):
    llm_input_tokens: int
    llm_output_tokens: int
    tts_characters: int
    estimated_usd: float


class Manifest(_Base):
    episode_id: str
    title: str
    duration_target_min: int
    duration_actual_sec: int
    format: str
    source: SourceRef
    files: Files
    costs: Costs
    created_at: str
    published: bool
