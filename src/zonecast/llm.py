"""Anthropic client wrapper with cost tracking (PRD §7, §11 cost tracking).

Structured outputs are the primary path for JSON stages: ``client.messages.parse`` with an
``output_format`` pydantic model returns a schema-valid, already-validated instance. Adaptive
thinking is on; sampling params (temperature/top_p/top_k) are never sent — Opus 4.8 rejects
them with a 400. Model IDs come from config, never literals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar

import anthropic

from .config import Settings

if TYPE_CHECKING:
    from pydantic import BaseModel

M = TypeVar("M", bound="BaseModel")

# USD per 1M tokens (input, output). External pricing fact, verified 2026-07-15 against
# docs.claude.com; keyed by model id for accounting only — model *selection* still comes
# from config (CLAUDE.md). Unknown models price at zero rather than crashing cost accounting.
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
}
# Prompt-cache multipliers on the input rate: reads are cheap, the first write costs a premium.
_CACHE_READ_MULT = 0.1
_CACHE_WRITE_MULT = 1.25


@dataclass
class _CallRecord:
    stage: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def cost_usd(self) -> float:
        in_rate, out_rate = _PRICING_PER_MTOK.get(self.model, (0.0, 0.0))
        return (
            self.input_tokens * in_rate
            + self.output_tokens * out_rate
            + self.cache_read_input_tokens * in_rate * _CACHE_READ_MULT
            + self.cache_creation_input_tokens * in_rate * _CACHE_WRITE_MULT
        ) / 1_000_000


class CostTracker:
    """Accumulates per-call token usage tagged by stage, for the manifest cost accounting."""

    def __init__(self) -> None:
        self._records: list[_CallRecord] = []

    def record(self, stage: str, model: str, usage: Any) -> None:
        """Record one call's usage. ``usage`` is an Anthropic ``Usage`` (or any object with
        the same attribute names); missing/None fields count as zero."""

        def _u(name: str) -> int:
            return int(getattr(usage, name, 0) or 0)

        self._records.append(
            _CallRecord(
                stage=stage,
                model=model,
                input_tokens=_u("input_tokens"),
                output_tokens=_u("output_tokens"),
                cache_read_input_tokens=_u("cache_read_input_tokens"),
                cache_creation_input_tokens=_u("cache_creation_input_tokens"),
            )
        )

    def totals(self) -> dict[str, int]:
        """Aggregate token counts across all calls. ``input_tokens`` is the full billed input
        (uncached + cache read + cache write), so it feeds ``manifest.costs`` directly."""
        t = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }
        for r in self._records:
            t["input_tokens"] += r.input_tokens + r.cache_read_input_tokens + r.cache_creation_input_tokens
            t["output_tokens"] += r.output_tokens
            t["cache_read_input_tokens"] += r.cache_read_input_tokens
            t["cache_creation_input_tokens"] += r.cache_creation_input_tokens
        return t

    def per_stage(self) -> dict[str, dict[str, int]]:
        """Token totals broken out by stage (observability)."""
        out: dict[str, dict[str, int]] = {}
        for r in self._records:
            s = out.setdefault(r.stage, {"input_tokens": 0, "output_tokens": 0})
            s["input_tokens"] += r.input_tokens + r.cache_read_input_tokens + r.cache_creation_input_tokens
            s["output_tokens"] += r.output_tokens
        return out

    def estimate_usd(self) -> float:
        """Total estimated dollar cost across all recorded calls."""
        return sum(r.cost_usd() for r in self._records)


class LLMParseError(RuntimeError):
    """Raised when structured output cannot be parsed after all retries. Carries the raw
    model text (``.raw``) so the caller can persist it for inspection (PRD §12)."""

    def __init__(self, message: str, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


@dataclass
class LLMClient:
    """Thin wrapper over the Anthropic SDK, sharing one :class:`CostTracker`."""

    settings: Settings
    client: Any = None
    costs: CostTracker = field(default_factory=CostTracker)

    def __post_init__(self) -> None:
        if self.client is None:
            # Zero-arg: picks up ANTHROPIC_API_KEY or an active `ant` CLI profile.
            self.client = anthropic.Anthropic()

    def _model(self, fast: bool) -> str:
        llm = self.settings.config.llm
        return llm.model_fast if fast else llm.model_quality

    def structured(
        self,
        stage: str,
        system_blocks: list[dict[str, Any]],
        user: str,
        response_model: type[M],
        *,
        fast: bool = False,
        effort: str = "high",
        max_tokens: int = 8192,
    ) -> M:
        """Return a validated ``response_model`` instance via structured outputs.

        Structured outputs guarantee schema-valid JSON, so this normally succeeds first try;
        the retry loop (``config.llm.max_retries_json``) is a fallback. On final failure the
        raw output is attached to the raised :class:`LLMParseError`.
        """
        model = self._model(fast)
        attempts = max(1, self.settings.config.llm.max_retries_json)
        raw = ""
        last_exc: Exception | None = None

        for _ in range(attempts):
            try:
                resp = self.client.messages.parse(
                    model=model,
                    max_tokens=max_tokens,
                    system=system_blocks,
                    messages=[{"role": "user", "content": user}],
                    output_format=response_model,
                    output_config={"effort": effort},  # parse merges the JSON schema in
                    thinking={"type": "adaptive"},
                    # No temperature/top_p/top_k — Opus 4.8 400s on sampling params.
                )
            except Exception as exc:  # network / transient parse failure -> retry
                last_exc = exc
                continue

            self.costs.record(stage, model, getattr(resp, "usage", None))
            raw = _raw_text(resp)
            parsed = resp.parsed_output
            if parsed is not None:
                return parsed
            last_exc = LLMParseError(f"{stage}: structured output produced no parsed value", raw)

        raise LLMParseError(
            f"{stage}: failed to parse structured output after {attempts} attempt(s): {last_exc}",
            raw,
        )

    def text(
        self,
        stage: str,
        system_blocks: list[dict[str, Any]],
        user: str,
        *,
        fast: bool = False,
        effort: str = "high",
        max_tokens: int = 8192,
    ) -> str:
        """Plain-text completion for prose stages (polish, normalization). Streams for large
        ``max_tokens`` so long outputs don't hit the non-streaming timeout."""
        model = self._model(fast)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"effort": effort},
            "thinking": {"type": "adaptive"},
        }

        if max_tokens > 8192:
            with self.client.messages.stream(**kwargs) as stream:
                for _ in stream.text_stream:
                    pass
                resp = stream.get_final_message()
        else:
            resp = self.client.messages.create(**kwargs)

        self.costs.record(stage, model, getattr(resp, "usage", None))
        return _raw_text(resp)


def _raw_text(resp: Any) -> str:
    """Concatenate the text of every text block in a message response."""
    parts: list[str] = []
    for block in getattr(resp, "content", None) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts)
