# zonecast

Turn a topic or a paper into a private, phone-ready explainer podcast episode.

One CLI command and one choice (how long, how deep) gets you a script that teaches
from the ground up — 3blue1brown-style pedagogy, Radiolab-style audio craft — rendered
with ElevenLabs into an MP3 that lands in your podcast app. Built for study during long
endurance training sessions: eyes-free, hands-free, no rewinding.

```bash
zonecast create "how transformers work" --duration 15 --auto
```

## Why it exists

Most effective studying is listening to someone explain things. Long zone 2 workouts are
hours of otherwise-idle attention. This converts one into the other.

It is not a generic "audio overview" generator. The difference is the
[listener profile](prompts/skills/explainer-podcast/references/listener.example.md) — "from
the ground up" means *from your ground*, and the pipeline enforces a five-pass process
(assess → blueprint → sectioned drafting with a running state block → read-aloud polish →
TTS prep) rather than one-shotting a script.

## Status

**M1 in progress** — core pipeline to a local MP3. See [PRD.md](PRD.md) for milestones
M1–M5, functional requirements, JSON schemas, and acceptance criteria.

## The skill files are the product

Everything under `prompts/skills/explainer-podcast/` is the quality spec *and* the prompt
asset. Every LLM call assembles its system prompt by reading these files from disk at call
time — editing the markdown changes behavior with zero code changes. That's a hard
architectural rule, not a convention.

| File | Role |
|---|---|
| `SKILL.md` | The five-pass pipeline, pedagogy core, six non-negotiable audio constraints |
| `references/listener.md` | Who you are and how you listen. Gitignored — this is your private state |
| `references/style-guide.md` | Distilled craft of the exemplars, duration templates, humor and dialogue rules |
| `references/tts-production.md` | Normalization, chunking, stitching, loudness targets |

## Setup

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and `ffmpeg`.

```bash
git clone https://github.com/<you>/zonecast && cd zonecast
uv sync

cp .env.example .env          # add ANTHROPIC_API_KEY and ELEVENLABS_API_KEY
zonecast profile init         # copies listener.example.md -> listener.md
zonecast profile edit         # rewrite it to describe yourself — do this first
```

Then set `tts.voice_host` in `config.yaml` to an ElevenLabs voice ID, and set
`tts.max_parallel_requests` to your plan's concurrency cap (Free 2 / Starter 3 /
Creator 5 / Pro 10).

## Design notes worth knowing

- **Duration is a word budget.** 150 wpm → words = minutes × 150. It's the generation
  contract, enforced per section.
- **Resumability is a requirement, not polish.** Every stage checkpoints; TTS clips are
  hash-cached by (voice, model, text) so `resume` never re-bills.
- **No transcript datasets.** Style comes from distilled principles in original words —
  never stored third-party transcripts.
- **Private RSS, not Spotify.** Spotify doesn't accept arbitrary private feeds. MP3s go to
  R2/S3 behind an unguessable feed URL you subscribe to in Overcast or Pocket Casts.
- **`eleven_multilingual_v2` is pinned deliberately.** `eleven_v3` is the newer flagship but
  doesn't support request stitching, which prosody continuity across chunks depends on. See
  the comment in `config.yaml` before changing it.

## Cost

Roughly a coffee per episode. A 2-hour episode is ~100k characters ≈ $5–10 of TTS plus a
few dollars of LLM; `--fast` (Flash tier) halves the TTS half. A 15-minute overview lands
well under $2.

## License

MIT
