"""zonecast command-line interface (PRD §10).

Phase 1 scope: real preflight, real episode-plan resolution, real profile management. The
per-stage pipeline calls (ingest → package → publish) land in later phases — the stage
commands here are honest stubs that wire and echo intent, never fake work.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import date
from pathlib import Path

import typer

from .config import Settings, get_settings, preflight
from .llm import LLMClient
from .pipeline import (
    STAGES,
    Stage,
    ensure_episode_dirs,
    episode_dir,
    episode_id,
    first_incomplete,
    run_pipeline,
)
from .stages import CreateArgs, StageContext

# Stages wired so far (phase 3). Publish (M2) extends this list when it lands.
_IMPLEMENTED: list[Stage] = [
    Stage.ingest,
    Stage.plan,
    Stage.blueprint,
    Stage.generate,
    Stage.polish,
    Stage.render,
    Stage.package,
]

app = typer.Typer(
    name="zonecast",
    help="Personal explainer-podcast generator: topic or paper in, phone-ready MP3 out.",
    no_args_is_help=True,
    add_completion=False,
)

profile_app = typer.Typer(help="Manage the listener profile (references/listener.md).")
app.add_typer(profile_app, name="profile")


def _settings() -> Settings:
    return get_settings()


# --- create -------------------------------------------------------------------------------


@app.command()
def create(
    topic: str | None = typer.Argument(None, help="Topic string, e.g. \"how transformers work\"."),
    duration: int | None = typer.Option(None, "--duration", help="Target length in minutes."),
    depth: str | None = typer.Option(None, "--depth", help="overview | standard | deep."),
    auto: bool = typer.Option(False, "--auto", help="Skip the offer prompt; pick the middle offer."),
    pdf: Path | None = typer.Option(None, "--pdf", help="Local PDF path to ingest."),
    url: str | None = typer.Option(None, "--url", help="arXiv abstract or PDF URL to ingest."),
    session: str | None = typer.Option(None, "--session", help='Session note, e.g. "3h ride".'),
    two_host: bool = typer.Option(False, "--two-host", help="Two-voice dialogue (M3)."),
    no_publish: bool = typer.Option(False, "--no-publish", help="Stop after packaging; don't publish."),
) -> None:
    """Plan and build an episode through the polished script (ingest → … → generate → polish)."""
    settings = _settings()
    preflight(settings=settings)

    if sum(bool(x) for x in (topic, pdf, url)) != 1:
        typer.echo("Provide exactly one source: a topic string, --pdf, or --url.", err=True)
        raise typer.Exit(1)

    label = topic or (pdf.stem if pdf else _url_label(url or ""))
    ep_id = episode_id(label, date.today().isoformat())
    ep_dir = episode_dir(settings.config.paths.episodes_dir, ep_id)
    ensure_episode_dirs(ep_dir)

    args = CreateArgs(
        topic=topic,
        pdf=pdf,
        url=url,
        duration=duration,
        depth=depth,
        auto=auto,
        session=session,
        two_host=two_host,
    )
    ctx = StageContext(episode_dir=ep_dir, settings=settings, llm=LLMClient(settings), args=args)
    # Persist the request so `resume` can reconstruct this run without the original invocation.
    ctx.write_json("request.json", args.to_dict())

    typer.echo(f"Episode:      {ep_id}")
    typer.echo(f"Working dir:  {ep_dir}")
    typer.echo(f"Offer select: {'auto (middle)' if auto else 'interactive'}")

    run_pipeline(ctx, _IMPLEMENTED)

    typer.echo(f"\nScript ready:   {ep_dir / 'script' / 'final.md'}")
    typer.echo(f"Episode ready:  {ep_dir / 'audio' / 'episode.mp3'}")
    typer.echo(f"Manifest:       {ep_dir / 'manifest.json'}")
    typer.echo(f"LLM cost so far: ${ctx.llm.costs.estimate_usd():.2f}")
    typer.echo("[phase 3] Pipeline stops after packaging; publish lands in M2.")


def _url_label(url: str) -> str:
    """Best-effort human-ish slug source from a URL, for the episode id."""
    import re

    m = re.search(r"arxiv\.org/abs/([\w.\-]+)", url, re.IGNORECASE)
    if m:
        return f"arxiv-{m.group(1)}"
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\.pdf$", "", tail, flags=re.IGNORECASE) or "episode"


# --- resume -------------------------------------------------------------------------------


@app.command()
def resume(episode_id_arg: str = typer.Argument(..., metavar="EPISODE_ID")) -> None:
    """Re-run from the first incomplete stage (skips completed work; RES-01)."""
    settings = _settings()
    ep_dir = episode_dir(settings.config.paths.episodes_dir, episode_id_arg)
    if not ep_dir.exists():
        typer.echo(f"No such episode: {ep_dir}", err=True)
        raise typer.Exit(1)

    implemented = tuple(_IMPLEMENTED)
    nxt = first_incomplete(ep_dir, implemented)
    if nxt is None:
        typer.echo(f"{episode_id_arg}: all wired stages complete — nothing to resume.")
        return

    typer.echo(f"{episode_id_arg}: resuming from stage '{nxt.value}'.")
    args = _load_args(ep_dir)
    ctx = StageContext(episode_dir=ep_dir, settings=settings, llm=LLMClient(settings), args=args)
    run_pipeline(ctx, _IMPLEMENTED)
    typer.echo(f"LLM cost this run: ${ctx.llm.costs.estimate_usd():.2f}")


def _load_args(ep_dir: Path) -> CreateArgs:
    """Reconstruct the create args for a resume: from request.json when present, else from the
    persisted source metadata (a topic-only best effort)."""
    import json

    request = ep_dir / "request.json"
    if request.exists():
        return CreateArgs.from_dict(json.loads(request.read_text()))
    meta_path = ep_dir / "source" / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        kind = meta.get("type")
        ref = meta.get("ref")
        if kind == "pdf":
            return CreateArgs(pdf=Path(ref) if ref else None)
        if kind == "url":
            return CreateArgs(url=ref)
        return CreateArgs(topic=ref)
    return CreateArgs()


# --- redo ---------------------------------------------------------------------------------


@app.command()
def redo(
    episode_id_arg: str = typer.Argument(..., metavar="EPISODE_ID"),
    stage: str = typer.Option(..., "--stage", help="Stage to invalidate and re-run from."),
) -> None:
    """Invalidate a stage and everything downstream, then re-run (Phase 1 stub)."""
    try:
        target = Stage(stage)
    except ValueError:
        valid = ", ".join(s.value for s in STAGES)
        typer.echo(f"Unknown stage '{stage}'. Valid: {valid}", err=True)
        raise typer.Exit(1) from None
    downstream = [s.value for s in STAGES[STAGES.index(target):]]
    typer.echo(f"{episode_id_arg}: would invalidate {', '.join(downstream)} and re-run.")
    typer.echo("[phase 1] Stage execution is wired in a later phase.")


# --- list ---------------------------------------------------------------------------------


@app.command(name="list")
def list_episodes() -> None:
    """List episodes found under the configured episodes dir."""
    settings = _settings()
    root = Path(settings.config.paths.episodes_dir)
    if not root.exists():
        typer.echo(f"No episodes dir yet ({root}).")
        return
    ids = sorted(p.name for p in root.iterdir() if p.is_dir())
    if not ids:
        typer.echo("No episodes yet.")
        return
    for ep_id in ids:
        nxt = first_incomplete(root / ep_id)
        status = "complete" if nxt is None else f"next: {nxt.value}"
        typer.echo(f"{ep_id}  [{status}]")


# --- publish ------------------------------------------------------------------------------


@app.command()
def publish(episode_id_arg: str = typer.Argument(..., metavar="EPISODE_ID")) -> None:
    """Upload the episode and regenerate the feed (Phase 1 stub; M2 implements)."""
    typer.echo(f"{episode_id_arg}: would upload MP3 + regenerate feed.xml.")
    typer.echo("[phase 1] Publishing is implemented in M2.")


# --- feed ---------------------------------------------------------------------------------


@app.command()
def feed(action: str = typer.Argument("url", help="Feed action (currently: url).")) -> None:
    """Feed utilities. ``feed url`` prints the configured feed path (Phase 1 stub)."""
    settings = _settings()
    if action == "url":
        typer.echo(f"Feed path (object key): {settings.config.feed.feed_path}")
        typer.echo("[phase 1] The public feed URL is assembled at publish time (M2).")
    else:
        typer.echo(f"Unknown feed action '{action}'. Try: url", err=True)
        raise typer.Exit(1)


# --- profile ------------------------------------------------------------------------------


def _skill_dir(override: Path | None) -> Path:
    return override if override is not None else Path(_settings().config.paths.skill_dir)


@profile_app.command("init")
def profile_init(
    skill_dir: Path | None = typer.Option(
        None, "--skill-dir", help="Override the skill dir (defaults to config.paths.skill_dir)."
    ),
) -> None:
    """Copy references/listener.example.md to listener.md. Refuses to overwrite an existing one."""
    refs = _skill_dir(skill_dir) / "references"
    example = refs / "listener.example.md"
    target = refs / "listener.md"

    if not example.exists():
        typer.echo(f"Template missing: {example}", err=True)
        raise typer.Exit(1)
    if target.exists():
        # listener.md is user-editable private state — never clobber it (CLAUDE.md).
        typer.echo(f"{target} already exists; leaving it untouched. Edit with 'zonecast profile edit'.")
        return
    shutil.copyfile(example, target)
    typer.echo(f"Created {target} from the template. Edit it to describe yourself.")


@profile_app.command("edit")
def profile_edit(
    skill_dir: Path | None = typer.Option(
        None, "--skill-dir", help="Override the skill dir (defaults to config.paths.skill_dir)."
    ),
) -> None:
    """Open listener.md in $EDITOR (falls back to vi)."""
    target = _skill_dir(skill_dir) / "references" / "listener.md"
    if not target.exists():
        typer.echo(f"{target} does not exist. Run 'zonecast profile init' first.", err=True)
        raise typer.Exit(1)
    editor = os.environ.get("EDITOR", "vi")
    subprocess.call([editor, str(target)])


if __name__ == "__main__":
    app()
