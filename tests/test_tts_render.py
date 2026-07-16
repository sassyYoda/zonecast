"""Tests for the phase-3 render half: the TTS wrapper (chunker, cache, stitching) and the
render stage (normalization + clip manifest + resume).

No real ElevenLabs or LLM calls — the elevenlabs client is a recording fake that mimics the
raw-response context-manager API, and the normalization LLM is a passthrough. Assertions pin
the invariants that matter: the clip cache never re-bills (RES-02), stitching passes the recent
request ids and drops stale ones, retries cap at 3 then raise, [PAUSE:*] becomes <break>, and a
completed render is skipped on resume.
"""

from __future__ import annotations

import contextlib
import types
from pathlib import Path

import pytest

from zonecast.config import Config, Settings, load_config
from zonecast.pipeline import Stage, ensure_episode_dirs, is_complete
from zonecast.stages import CreateArgs, StageContext
from zonecast.tts import TTSClient, TTSRenderError, chunk_text, clip_cache_key

REPO_ROOT = Path(__file__).resolve().parent.parent


def _settings() -> Settings:
    cfg: Config = load_config(REPO_ROOT / "config.yaml")
    return Settings(cfg, {})


# --- fake elevenlabs client ---------------------------------------------------------------


class RecordingEleven:
    """Mimics ``client.text_to_speech.with_raw_response.convert`` as a context manager.

    Records every convert() kwargs dict, hands back a fresh request id per call (unless
    ``fail`` is set, in which case every call raises to exercise the retry path).
    """

    def __init__(self, request_ids: list[str] | None = None, fail: bool = False) -> None:
        self.calls: list[dict] = []
        self._ids = list(request_ids or [])
        self.fail = fail
        self.text_to_speech = types.SimpleNamespace(
            with_raw_response=types.SimpleNamespace(convert=self._convert)
        )

    @contextlib.contextmanager
    def _convert(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("boom")
        rid = self._ids.pop(0) if self._ids else None
        headers = {"request-id": rid} if rid else {}
        yield types.SimpleNamespace(data=iter([b"MP3-BYTES"]), headers=headers)


def _client(fake: RecordingEleven, **kw) -> TTSClient:
    return TTSClient(_settings(), client=fake, sleep_fn=lambda *_: None, **kw)


# --- chunk_text ---------------------------------------------------------------------------


def test_chunk_text_packs_paragraphs_into_range() -> None:
    # Ten 800-char single-sentence paragraphs; min 2000 / max 5000.
    para = ("word " * 158).strip() + "."  # ~ 795 chars, ends on a sentence boundary
    assert 700 < len(para) <= 800
    text = "\n\n".join([para] * 10)
    chunks = chunk_text(text, 2000, 5000)

    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 5000
        # Never split mid-sentence: every paragraph ends in '.', so every chunk must too.
        assert c.rstrip().endswith(".")
    # Every non-final chunk is genuinely packed (>= min); only the remainder may be short.
    for c in chunks[:-1]:
        assert len(c) >= 2000


def test_chunk_text_giant_paragraph_falls_back_to_sentence_split() -> None:
    sentence = ("word " * 78).strip() + "."  # ~ 395 chars
    giant = " ".join([sentence] * 20)  # ~ 7.9k chars, one paragraph, busts max
    assert len(giant) > 5000
    chunks = chunk_text(giant, 2000, 5000)

    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 5000
        assert c.rstrip().endswith(".")  # split only at sentence boundaries


def test_chunk_text_tiny_script_yields_one_chunk() -> None:
    chunks = chunk_text("A short thought.", 2000, 5000)
    assert chunks == ["A short thought."]


def test_chunk_text_empty_input_yields_nothing() -> None:
    assert chunk_text("   \n\n  ", 2000, 5000) == []


# --- clip_cache_key -----------------------------------------------------------------------


def test_clip_cache_key_is_deterministic() -> None:
    a = clip_cache_key("voiceA", "modelA", "hello world")
    b = clip_cache_key("voiceA", "modelA", "hello world")
    assert a == b and len(a) == 64  # sha256 hexdigest


def test_clip_cache_key_varies_with_each_field() -> None:
    base = clip_cache_key("voiceA", "modelA", "text")
    assert clip_cache_key("voiceB", "modelA", "text") != base
    assert clip_cache_key("voiceA", "modelB", "text") != base
    assert clip_cache_key("voiceA", "modelA", "text!") != base


# --- TTSClient.render_chunks --------------------------------------------------------------


def test_cache_hit_makes_no_api_call(tmp_path: Path) -> None:
    fake = RecordingEleven(request_ids=["r1"])
    client = _client(fake)
    out = tmp_path / "clips"
    out.mkdir()
    # Pre-place the exact cached clip for the (voice, model, text) triple.
    chunk = "already rendered"
    key = clip_cache_key("V", "M", chunk)
    (out / f"{key}.mp3").write_bytes(b"CACHED")

    paths = client.render_chunks([chunk], "V", "M", out)

    assert fake.calls == []  # RES-02: no billing for a cache hit
    assert paths == [out / f"{key}.mp3"]
    assert paths[0].read_bytes() == b"CACHED"
    assert client.chars_rendered == 0


def test_stitching_passes_previous_request_ids_on_second_chunk(tmp_path: Path) -> None:
    fake = RecordingEleven(request_ids=["req-1", "req-2"])
    client = _client(fake)
    out = tmp_path / "clips"

    client.render_chunks(["chunk one", "chunk two"], "V", "M", out)

    assert len(fake.calls) == 2
    # Chunk 1 has no prior id -> no previous_request_ids; falls back to nothing (empty prev_text).
    assert "previous_request_ids" not in fake.calls[0]
    # Chunk 2 conditions on chunk 1's returned id.
    assert fake.calls[1]["previous_request_ids"] == ["req-1"]
    assert "previous_text" not in fake.calls[1]  # ids override text; never send both
    assert client.chars_rendered == len("chunk one") + len("chunk two")


def test_stale_request_ids_dropped_and_previous_text_used(tmp_path: Path) -> None:
    # A controllable clock: chunk 1 is recorded at t=0, then time jumps past the 2h TTL so its
    # id is stale by the time chunk 2 selects continuity.
    # Ticks feed, in order: chunk1 select (recent empty, value irrelevant), chunk1 record ts=0,
    # chunk2 select at t >> TTL (so req-1 is stale), chunk2 record ts.
    ttl = _settings().config.tts.stitch_id_ttl_sec
    ticks = iter([0.0, 0.0, ttl + 100.0, ttl + 100.0])
    fake = RecordingEleven(request_ids=["req-1", "req-2"])
    client = _client(fake, time_fn=lambda: next(ticks))
    out = tmp_path / "clips"

    client.render_chunks(["chunk one is long enough", "chunk two"], "V", "M", out)

    # Chunk 2's only prior id is stale -> dropped; continuity falls back to previous_text.
    assert "previous_request_ids" not in fake.calls[1]
    assert fake.calls[1]["previous_text"] == "chunk one is long enough"


def test_failing_chunk_retries_three_times_then_raises(tmp_path: Path) -> None:
    fake = RecordingEleven(fail=True)
    client = _client(fake)
    out = tmp_path / "clips"

    with pytest.raises(TTSRenderError):
        client.render_chunks(["doomed chunk"], "V", "M", out)

    assert len(fake.calls) == 3  # 3 attempts total, then give up (PRD §12)


def test_render_uses_output_format_and_model(tmp_path: Path) -> None:
    fake = RecordingEleven(request_ids=["r1"])
    client = _client(fake)
    client.render_chunks(["only chunk"], "VOICE", "MODEL", tmp_path / "clips")
    call = fake.calls[0]
    assert call["voice_id"] == "VOICE"
    assert call["model_id"] == "MODEL"
    assert call["output_format"] == "mp3_44100_128"


# --- render stage -------------------------------------------------------------------------


class PassthroughLLM:
    """Normalization LLM that echoes the section body back unchanged (still holding [PAUSE:*]
    and [HOST]) so the stage's deterministic markup enforcement is what gets exercised."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def text(self, stage, system, user, **kw):  # noqa: ANN001
        self.calls.append(user)
        return user.split("Section text:\n", 1)[1]


_FINAL_MD = """# The Title

**Driving question:** how?
**Duration target:** 15 min (~2,250 words) | **Format:** solo
**Spine analogy:** a vandal and a restorer

## Section 1: intro [~450 words]

[HOST] Hello there, welcome. [PAUSE:long] Now we continue onward.

## Section 2: body [~450 words]

[HOST] Here is the middle. [PAUSE:short] And then it wraps up neatly.
"""


def _render_ctx(tmp_path: Path, llm) -> StageContext:
    ep = tmp_path / "ep"
    ensure_episode_dirs(ep)
    ctx = StageContext(episode_dir=ep, settings=_settings(), llm=llm, args=CreateArgs(topic="t"))
    ctx.write_text("script/final.md", _FINAL_MD)
    return ctx


def _patch_ttsclient(monkeypatch, fake: RecordingEleven) -> None:
    import zonecast.stages.render as render

    monkeypatch.setattr(
        render,
        "TTSClient",
        lambda settings: TTSClient(settings, client=fake, sleep_fn=lambda *_: None),
    )


def test_translation_helper_maps_pause_to_break() -> None:
    from zonecast.stages.render import _enforce_tts_markup

    assert _enforce_tts_markup("[PAUSE:long]") == '<break time="1.5s"/>'
    assert _enforce_tts_markup("[PAUSE:short]") == '<break time="0.5s"/>'
    # Speaker tags and emphasis are scrubbed; the <break> and the words survive.
    out = _enforce_tts_markup("[HOST] a *strong* word. [PAUSE:long] done.")
    assert "[HOST]" not in out and "*" not in out and "strong" in out
    assert '<break time="1.5s"/>' in out


def test_render_stage_translates_pauses_and_writes_manifest(tmp_path: Path, monkeypatch) -> None:
    import zonecast.stages.render as render

    fake = RecordingEleven(request_ids=["r1", "r2"])
    _patch_ttsclient(monkeypatch, fake)
    llm = PassthroughLLM()
    ctx = _render_ctx(tmp_path, llm)

    render.run(ctx)

    # [PAUSE:long] -> <break time="1.5s"/> in the audio-ready text; no source markers survive.
    tts_txt = ctx.read_text("script/tts.txt")
    assert '<break time="1.5s"/>' in tts_txt
    assert '<break time="0.5s"/>' in tts_txt
    assert "[PAUSE:" not in tts_txt and "[HOST]" not in tts_txt

    # Two tiny sections -> two chunks -> two clips, each tagged with its section + char count.
    manifest = ctx.read_json("audio/clips.json")
    assert manifest["model_id"] == ctx.settings.config.tts.model
    assert manifest["output_format"] == "mp3_44100_128"
    assert [c["section"] for c in manifest["clips"]] == [1, 2]
    assert [s["n"] for s in manifest["sections"]] == [1, 2]
    for clip in manifest["clips"]:
        assert clip["chars"] > 0
        assert (ctx.episode_dir / "audio" / clip["file"]).exists()
    assert manifest["chars_rendered"] > 0
    assert is_complete(ctx.episode_dir, Stage.render)


def test_render_stage_resume_skips_when_clips_present(tmp_path: Path, monkeypatch) -> None:
    import zonecast.stages.render as render

    fake = RecordingEleven(request_ids=["r1", "r2"])
    _patch_ttsclient(monkeypatch, fake)
    llm = PassthroughLLM()
    ctx = _render_ctx(tmp_path, llm)

    render.run(ctx)
    calls_after_first = len(fake.calls)
    llm_after_first = len(llm.calls)

    # Second run: manifest + clips exist -> fully skipped, no LLM or API work re-done.
    render.run(ctx)
    assert len(fake.calls) == calls_after_first
    assert len(llm.calls) == llm_after_first
    assert is_complete(ctx.episode_dir, Stage.render)


def test_render_reentry_after_crash_does_not_rebill(tmp_path: Path, monkeypatch) -> None:
    """RES-02/ACC-02 regression: a render that crashed before completion must, on re-entry,
    reuse the cached normalization (no LLM re-bill) and the cached clips (no TTS re-bill).

    The bug this guards: normalization is a non-deterministic LLM call, so re-running it on
    resume produced a different tts.txt, changed every clip cache key, and re-billed both the
    LLM and every already-rendered clip. The fix caches normalization keyed to a hash of
    final.md. Here we force re-entry (delete the completion marker and clips.json, as if the
    process died just before writing them) while the normalization cache and clip files
    remain, and assert nothing bills again."""
    import zonecast.stages.render as render

    fake = RecordingEleven(request_ids=["r1", "r2"])
    _patch_ttsclient(monkeypatch, fake)
    llm = PassthroughLLM()
    ctx = _render_ctx(tmp_path, llm)

    render.run(ctx)
    calls_after_first = len(fake.calls)
    llm_after_first = len(llm.calls)
    assert calls_after_first > 0 and llm_after_first > 0  # first run really did work
    assert ctx.exists("script/tts_sections.json")

    # Simulate a crash after clips + normalization cache landed but before completion: drop the
    # done marker and the manifest so _render_already_complete() is False and run() re-enters.
    (ctx.episode_dir / ".stages" / "render.done").unlink(missing_ok=True)
    (ctx.episode_dir / "audio" / "clips.json").unlink()

    render.run(ctx)

    assert len(llm.calls) == llm_after_first, "normalization LLM was re-billed on resume"
    assert len(fake.calls) == calls_after_first, "TTS clips were re-billed on resume"
    assert is_complete(ctx.episode_dir, Stage.render)
