from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from zonecast.config import Config, Settings, load_config
from zonecast.llm import CostTracker, LLMClient, LLMParseError, _CallRecord

REPO_ROOT = Path(__file__).resolve().parent.parent


class Toy(BaseModel):
    answer: str


def _settings() -> Settings:
    cfg: Config = load_config(REPO_ROOT / "config.yaml")
    return Settings(cfg, {})


class FakeUsage:
    def __init__(self, **kw: int) -> None:
        self.input_tokens = kw.get("input_tokens", 0)
        self.output_tokens = kw.get("output_tokens", 0)
        self.cache_read_input_tokens = kw.get("cache_read_input_tokens", 0)
        self.cache_creation_input_tokens = kw.get("cache_creation_input_tokens", 0)


class FakeParsed:
    """Mimics a ParsedMessage: has .usage, .content (text blocks), and .parsed_output."""

    def __init__(self, parsed: object, usage: FakeUsage, text: str = "{}") -> None:
        self.parsed_output = parsed
        self.usage = usage
        self.content = [SimpleNamespace(type="text", text=text)]


class FakeMessages:
    def __init__(self, response: object) -> None:
        self._response = response
        self.calls: list[dict] = []

    def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self._response


class FakeClient:
    def __init__(self, response: object) -> None:
        self.messages = FakeMessages(response)


def test_structured_returns_parsed_model_and_records_usage() -> None:
    usage = FakeUsage(input_tokens=1000, output_tokens=200)
    client = FakeClient(FakeParsed(Toy(answer="hi"), usage))
    llm = LLMClient(_settings(), client=client)

    out = llm.structured("plan", [{"type": "text", "text": "sys"}], "user", Toy)

    assert isinstance(out, Toy)
    assert out.answer == "hi"
    totals = llm.costs.totals()
    assert totals["input_tokens"] == 1000
    assert totals["output_tokens"] == 200


def test_structured_uses_config_model_and_no_sampling_params() -> None:
    settings = _settings()
    client = FakeClient(FakeParsed(Toy(answer="x"), FakeUsage()))
    llm = LLMClient(settings, client=client)

    llm.structured("blueprint", [], "u", Toy)
    kwargs = client.messages.calls[0]

    # Model comes from config, not a literal.
    assert kwargs["model"] == settings.config.llm.model_quality
    # Adaptive thinking on; structured output requested.
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["output_format"] is Toy
    assert kwargs["output_config"] == {"effort": "high"}
    # Opus 4.8 rejects sampling params — they must never be sent.
    for banned in ("temperature", "top_p", "top_k"):
        assert banned not in kwargs


def test_structured_fast_selects_fast_model() -> None:
    settings = _settings()
    client = FakeClient(FakeParsed(Toy(answer="x"), FakeUsage()))
    llm = LLMClient(settings, client=client)
    llm.structured("plan", [], "u", Toy, fast=True)
    assert client.messages.calls[0]["model"] == settings.config.llm.model_fast


def test_structured_raises_with_raw_after_retries() -> None:
    # parsed_output None every time -> exhaust retries, raise with raw attached.
    client = FakeClient(FakeParsed(None, FakeUsage(), text='{"broken":true}'))
    llm = LLMClient(_settings(), client=client)
    with pytest.raises(LLMParseError) as exc:
        llm.structured("plan", [], "u", Toy)
    assert exc.value.raw == '{"broken":true}'
    # Retried up to config.llm.max_retries_json times.
    assert len(client.messages.calls) == _settings().config.llm.max_retries_json


def test_cost_estimate_math() -> None:
    tracker = CostTracker()
    # 1M input + 1M output on Opus 4.8 -> $5 + $25 = $30.
    tracker.record("plan", "claude-opus-4-8", FakeUsage(input_tokens=1_000_000, output_tokens=1_000_000))
    assert tracker.estimate_usd() == pytest.approx(30.0)


def test_cost_estimate_includes_cache_tiers() -> None:
    # cache read at 0.1x input, cache write at 1.25x input (Opus $5/Mtok input).
    rec = _CallRecord(
        stage="generate",
        model="claude-opus-4-8",
        input_tokens=0,
        output_tokens=0,
        cache_read_input_tokens=1_000_000,
        cache_creation_input_tokens=1_000_000,
    )
    # 1M read * $5 * 0.1 = $0.5 ; 1M write * $5 * 1.25 = $6.25
    assert rec.cost_usd() == pytest.approx(6.75)


def test_totals_fold_cache_into_input() -> None:
    tracker = CostTracker()
    tracker.record(
        "generate",
        "claude-sonnet-5",
        FakeUsage(input_tokens=100, cache_read_input_tokens=50, cache_creation_input_tokens=10),
    )
    # manifest input = uncached + cache read + cache write.
    assert tracker.totals()["input_tokens"] == 160
