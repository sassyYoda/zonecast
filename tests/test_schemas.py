import pytest
from pydantic import ValidationError

from zonecast.schemas import Blueprint, Manifest, Offer, Offers, Section, StateBlock


def _offer_dict(**over) -> dict:
    base = dict(
        id=1,
        duration_min=45,
        word_budget=6750,
        depth="standard",
        driving_question="How does a model decide which words matter to each other?",
        outline_preview=["beat one", "beat two", "beat three"],
        deliberately_excluded=["positional encodings"],
        format_recommendation="solo",
        style_file=None,
    )
    base.update(over)
    return base


def test_offer_valid_with_null_style_file() -> None:
    offer = Offer.model_validate(_offer_dict())
    assert offer.style_file is None
    offer2 = Offer.model_validate(_offer_dict(style_file="ml-theory"))
    assert offer2.style_file == "ml-theory"


def test_offers_wrapper() -> None:
    offers = Offers.model_validate({"topic": "transformers", "offers": [_offer_dict()]})
    assert offers.topic == "transformers"
    assert len(offers.offers) == 1


def _section_dict(**over) -> dict:
    base = dict(
        n=1,
        name="The Vandal",
        job="Introduce forward diffusion as trivial destruction.",
        word_budget=600,
        opens_with_tension="restoration implies something was there",
        closes_opening_tension="but there was nothing there",
        connective_to_next="but",
        recap_beat=False,
    )
    base.update(over)
    return base


def test_blueprint_valid() -> None:
    bp = Blueprint.model_validate(
        dict(
            offer_id=1,
            title="The Restorer",
            driving_question="How do you get creation from a machine never taught to create?",
            spine_analogy={
                "image": "the vandal and the restorer",
                "mapping": {"vandal": "forward noising", "restorer": "denoising net"},
            },
            sections=[_section_dict(), _section_dict(n=2, connective_to_next="therefore")],
        )
    )
    assert bp.sections[1].connective_to_next == "therefore"
    assert bp.spine_analogy.mapping["vandal"] == "forward noising"


def test_section_rejects_and_then_connective() -> None:
    with pytest.raises(ValidationError):
        Section.model_validate(_section_dict(connective_to_next="and_then"))


def test_state_block_valid() -> None:
    state = StateBlock.model_validate(
        dict(
            after_section=2,
            concepts_established=["forward noising", "timestep conditioning"],
            live_analogies=[{"image": "the date", "maps_to": "timestep"}],
            open_loops=["how does repair become creation?"],
            callbacks_available=["gray mush"],
            words_spent=1504,
            words_remaining=746,
        )
    )
    assert state.live_analogies[0].maps_to == "timestep"


def test_manifest_valid() -> None:
    manifest = Manifest.model_validate(
        dict(
            episode_id="2026-07-15-attention-from-the-ground-up",
            title="Attention from the Ground Up",
            duration_target_min=45,
            duration_actual_sec=2710,
            format="solo",
            source={"type": "topic", "ref": "how transformers work"},
            files={"mp3": "audio/episode.mp3", "chapters": "chapters.json", "script": "script/final.md"},
            costs={
                "llm_input_tokens": 100,
                "llm_output_tokens": 200,
                "tts_characters": 12000,
                "estimated_usd": 1.5,
            },
            created_at="2026-07-15T12:00:00Z",
            published=False,
        )
    )
    assert manifest.source.type == "topic"
    assert manifest.costs.estimated_usd == 1.5


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        Offer.model_validate(_offer_dict(unexpected="nope"))
