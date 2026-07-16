"""Stage-orchestration contract for the script pipeline (PRD §5, §9).

Every stage is a module ``zonecast.stages.<name>`` exposing ``run(ctx: StageContext) -> None``.
A stage reads the prior stage's output from the episode working dir, writes its own output,
and calls :func:`zonecast.pipeline.mark_complete` last — so re-running a stage is safe and
``resume`` never re-pays for finished work (PRD §11 resumability). :class:`StageContext` is the
single object threaded through every stage; it carries the episode dir, settings, the *shared*
:class:`~zonecast.llm.LLMClient` (so cost accumulates across all stages), the parsed CLI args,
and thin artifact read/write helpers.

Artifact locations written by the stages built here (phase 2):
- ``source/meta.json``           — ingest: {type, ref, title, ...} source metadata
- ``source/paper.md``            — ingest (pdf/url only): extracted full text
- ``plan/offers.json``           — plan: the 2–3 generated offers (Offers schema)
- ``plan/offer.json``            — plan: the single chosen offer (Offer schema)
- ``blueprint/blueprint.json``   — blueprint: the validated section outline (Blueprint schema)
- ``request.json``               — create bookkeeping: the CreateArgs, so ``resume`` reconstructs
                                   the run without the original CLI invocation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..config import Settings  # noqa: F401  (typing re-export)


@dataclass
class CreateArgs:
    """The resolved inputs to a ``create`` run (mirrors the CLI flags in PRD §10)."""

    topic: str | None = None
    pdf: Path | None = None
    url: str | None = None
    duration: int | None = None
    depth: str | None = None
    auto: bool = False
    session: str | None = None
    two_host: bool = False

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable view (Path -> str) for persisting to ``request.json``."""
        return {
            "topic": self.topic,
            "pdf": str(self.pdf) if self.pdf is not None else None,
            "url": self.url,
            "duration": self.duration,
            "depth": self.depth,
            "auto": self.auto,
            "session": self.session,
            "two_host": self.two_host,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CreateArgs:
        pdf = data.get("pdf")
        return cls(
            topic=data.get("topic"),
            pdf=Path(pdf) if pdf else None,
            url=data.get("url"),
            duration=data.get("duration"),
            depth=data.get("depth"),
            auto=bool(data.get("auto", False)),
            session=data.get("session"),
            two_host=bool(data.get("two_host", False)),
        )


@dataclass
class StageContext:
    """Everything a stage needs, threaded unchanged through the whole pipeline."""

    episode_dir: Path
    settings: "Settings"
    llm: Any  # LLMClient — kept loose to avoid importing the anthropic-backed client for typing
    args: CreateArgs = field(default_factory=CreateArgs)

    # --- artifact helpers (all paths relative to the episode dir) --------------------------

    def _path(self, relpath: str) -> Path:
        return self.episode_dir / relpath

    def exists(self, relpath: str) -> bool:
        return self._path(relpath).exists()

    def read_text(self, relpath: str) -> str:
        return self._path(relpath).read_text()

    def write_text(self, relpath: str, s: str) -> Path:
        p = self._path(relpath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(s)
        return p

    def read_json(self, relpath: str) -> Any:
        return json.loads(self.read_text(relpath))

    def write_json(self, relpath: str, obj: Any) -> Path:
        """Write ``obj`` as pretty JSON. Accepts a pydantic model or any json-able value."""
        if isinstance(obj, BaseModel):
            text = obj.model_dump_json(indent=2)
        else:
            text = json.dumps(obj, indent=2, ensure_ascii=False)
        return self.write_text(relpath, text + "\n")


# Cap the paper excerpt injected into planning/blueprint user messages. The full text lives in
# source/paper.md; the offer/blueprint calls only need enough to assess scope, and the skill
# system prompt already dominates the token budget.
_PAPER_EXCERPT_CHARS = 12_000


def read_source_bundle(ctx: "StageContext") -> str:
    """Render the ingested source into a user-message block for the plan/blueprint stages.

    Topic sources are a one-liner; PDF/URL sources include the parsed metadata plus a leading
    excerpt of ``source/paper.md`` (truncated — the whole paper would crowd out the skill prompt).
    """
    meta = ctx.read_json("source/meta.json")
    lines = [
        f"Source type: {meta.get('type')}",
        f"Title: {meta.get('title')}",
    ]
    for key in ("authors", "year"):
        if meta.get(key):
            lines.append(f"{key.capitalize()}: {meta[key]}")
    if meta.get("type") == "topic":
        lines.append(f"Topic: {meta.get('ref')}")
        return "\n".join(lines)

    if ctx.exists("source/paper.md"):
        paper = ctx.read_text("source/paper.md")
        excerpt = paper[:_PAPER_EXCERPT_CHARS]
        truncated = " (truncated)" if len(paper) > _PAPER_EXCERPT_CHARS else ""
        lines.append(f"\nPaper text{truncated}:\n{excerpt}")
    return "\n".join(lines)


__all__ = ["CreateArgs", "StageContext", "read_source_bundle"]
