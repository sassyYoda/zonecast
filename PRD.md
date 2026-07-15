# PRD — Zonecast: Personal Explainer-Podcast Generator

**Version:** 1.0 (2026-07-15) · **Status:** Ready for implementation · **Working name:** `zonecast` (placeholder, rename freely)

This document is written to be handed directly to a coding agent. It contains full functional requirements, data schemas, repo layout, CLI spec, and acceptance criteria. Companion files: `PROJECT_CONTEXT.md` (design history and rationale) and `explainer-podcast.skill` (a zip archive containing three prompt-asset markdown files: `SKILL.md`, `references/listener.md`, `references/style-guide.md`, `references/tts-production.md` — extract into `prompts/skills/explainer-podcast/`).

---

## 1. Summary

A single-user pipeline that turns a topic or a paper (PDF) into a downloadable, phone-ready explainer podcast episode. The listener is a graduate-level ML researcher in endurance training; episodes are consumed hands-free and eyes-free during long zone 2 workouts (45 min–3 h). The system plans an episode at a chosen duration/depth, generates a pedagogically rigorous script (3blue1brown-style ground-up teaching + Radiolab-style audio craft), renders it with ElevenLabs TTS, stitches an MP3 with chapters, and publishes it to a private RSS feed the user subscribes to in a podcast app.

## 2. Goals

- G1: Topic/paper in → listenable MP3 out, end to end, with one CLI command plus one interactive choice (the duration/depth offer).
- G2: Script quality that follows the bundled `explainer-podcast` skill exactly (the skill IS the quality spec — the pipeline's job is to enforce its five-pass process programmatically).
- G3: Episodes appear automatically on the user's phone via private RSS within minutes of generation.
- G4: Cost per 2-hour episode ≤ ~$15 all-in; per 15-min episode ≤ ~$2.
- G5: Resumable: any stage can fail and be re-run without redoing completed work or re-paying for it.

## 3. Non-goals (v1)

- No multi-user support, auth, or web UI.
- No Spotify publishing (Spotify does not accept private RSS feeds; do not design for it).
- No fine-tuning or transcript-dataset curation — style is enforced via the skill's distilled style guides.
- No background music / sound design in v1 (optional intro sting is M5).
- No real-time streaming generation.

## 4. Milestones

- **M1 — Core pipeline (CLI):** ingest → plan → blueprint → generate → polish → local MP3. Solo-narrator only.
- **M2 — Delivery:** object storage upload, RSS feed generation, chapters. Episode shows up in Overcast/Pocket Casts.
- **M3 — Two-host dialogue:** dual-voice rendering per the skill's dialogue rules; auto-offered for episodes > 45 min.
- **M4 — Style library:** dynamic style-guide distillation for new fields, cached in `styles/`.
- **M5 — Polish:** intro sting, listener-feedback command that updates `listener.md`, episode regeneration of a single section.

Build strictly in this order. M1 alone is daily-usable (AirDrop/copy the MP3).

## 5. System overview

```
input (topic | pdf | url)
   │
   ▼
[1 INGEST] ──► normalized source bundle (text + metadata)
   │
   ▼
[2 PLAN] ──► 2–3 offers (duration/depth/driving question/outline) ──► USER PICKS
   │
   ▼
[3 BLUEPRINT] ──► section-by-section outline w/ word budgets, spine analogy
   │
   ▼
[4 GENERATE] ──► loop: draft section N with STATE block, update STATE
   │
   ▼
[5 POLISH] ──► audio-native edit pass over assembled draft
   │
   ▼
[6 RENDER] ──► normalize → chunk → TTS calls → clips
   │
   ▼
[7 PACKAGE] ──► ffmpeg stitch + loudnorm → MP3 + chapters.json + manifest
   │
   ▼
[8 PUBLISH] ──► upload MP3 + regenerate feed.xml → private podcast feed
```

Every stage writes its output to the episode's working directory before the next stage starts (see §9 repo layout, §12 resumability).

## 6. Functional requirements

### FR-1 Ingestion
- Accept: (a) free-text topic string; (b) local PDF path; (c) URL (arxiv abstract page or PDF link).
- PDF: extract full text (pymupdf), preserving section structure where detectable; store as `source/paper.md` plus `source/meta.json` (title, authors, year if parseable).
- URL: for arxiv, prefer fetching the PDF; store the same way.
- Topic-only: `source/meta.json` records the raw topic string; optionally (flag `--research`) run a web-search enrichment step producing `source/research-notes.md` (M1: stub acceptable; implement if a search API key is configured).

### FR-2 Prompt assembly
- Every LLM call's system prompt is assembled from the skill assets: `SKILL.md` always; `references/listener.md` always; `references/style-guide.md` for stages 3–5; `references/tts-production.md` for stage 6 normalization; plus the relevant field style guide from `styles/` (FR-10) when one exists.
- Skill files are loaded from disk at call time (never hard-coded into Python), so editing the markdown tunes the product with no code change. This is a hard requirement.

### FR-3 Planning pass (stage 2)
- One LLM call. Input: source bundle + optional user constraints (`--duration 60`, `--depth overview|standard|deep`, session note like "3h ride").
- Output: strict JSON, 2–3 offers (schema §8.1). Enforce with retry-on-invalid-JSON (max 3 attempts, then fail loudly).
- CLI presents offers, user picks by number; `--auto` picks the middle offer. If the user passed `--duration`, generate offers at that duration varying only depth/angle.

### FR-4 Blueprint (stage 3)
- One LLM call. Input: chosen offer + source bundle. Output: blueprint JSON (schema §8.2): ordered sections, each with job, word budget (800–1,200), open/close tension, recap flag; plus the spine analogy and its explicit mapping.
- Validate: sum of section budgets within ±10% of `duration_min × 150`; every section has a but/therefore link to the next (the LLM must output the connective type; reject `and_then`).

### FR-5 Section generation loop (stage 4)
- For each section in order: one LLM call with (system: skill assets; user: blueprint, this section's spec, full text of the previous section for voice continuity, and the current STATE block). Output: section prose + updated STATE (schema §8.3).
- Persist each section to `draft/section-NN.md` and STATE to `draft/state-NN.json` immediately (resumability).
- Enforce word budget per section: if output deviates > 20%, one automatic retry with corrective instruction; then accept and log.

### FR-6 Polish pass (stage 5)
- Process the assembled draft in overlapping windows of ~3 sections (long scripts exceed comfortable single-call editing). Instructions: the skill's Pass-4 checklist (sentence length, signposting at boundaries, redundancy rule, humor pruning, budget check).
- Output `script/final.md` in the skill's output format (speaker tags, `[PAUSE:*]` markers, metadata header).

### FR-7 TTS rendering (stage 6)
- Normalization sub-pass (LLM or rules+LLM hybrid) per `references/tts-production.md`: numbers, acronyms, symbols, markdown stripping. Output `script/tts.txt` (solo) or `script/tts.jsonl` (dialogue: `{speaker, text}` lines).
- Chunk at paragraph boundaries, 2,000–5,000 chars/chunk, never mid-sentence.
- ElevenLabs API: model and voice IDs from config; use request-stitching/previous-text continuity parameters where the current API supports them (verify against current ElevenLabs docs at implementation time). Retry each chunk up to 3× with backoff; cache completed chunk audio by content hash so retries and re-runs never re-bill.
- Dialogue mode (M3): render per-speaker with distinct voice IDs, in script order.

### FR-8 Packaging (stage 7)
- ffmpeg: concatenate clips in order; insert 400 ms silence at speaker changes, 1.5 s at section boundaries; loudness-normalize (`loudnorm=I=-16:TP=-1.5:LRA=11`); export MP3 128 kbps mono, ID3 tags (title, "Zonecast", episode date).
- Emit `chapters.json` (Podcasting 2.0 format) from section boundaries using actual audio timestamps (track cumulative clip durations during stitching).
- Emit `manifest.json` (schema §8.4) including full cost accounting (LLM tokens per stage, TTS characters, dollar estimates).

### FR-9 Publishing (stage 8, M2)
- Upload MP3 + chapters.json to S3-compatible storage (Cloudflare R2 default; boto3-compatible config).
- Regenerate `feed.xml` (RSS 2.0 + iTunes namespace + `<podcast:chapters>`) from all manifests; upload. Feed URL is stable; treat it as a secret (unguessable path).
- Verify: after publish, fetch the feed URL and confirm the new item parses.

### FR-10 Style-guide library (M4)
- `styles/<field-slug>.md` holds distilled per-field style guides (e.g., `ml-theory.md`, `systems.md`, `biology.md`).
- During planning, an LLM classifier maps the topic to an existing style file or proposes a new field. If new: run the distillation prompt (asks the model to produce a field-specific addendum — canonical analogy domains for the field, common misconception traps, what the field's best explainers emphasize) and cache it. Distillation is from the model's knowledge; it must NOT scrape or store third-party transcripts.
- Style files are injected into stages 3–5 prompts alongside the core style guide.

### FR-11 Config & profile
- `.env`: `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `R2_*` credentials, optional search API key.
- `config.yaml`: model IDs (LLM + TTS), voice IDs (host, guest), wpm constant (default 150), feed metadata, storage bucket/paths.
- `prompts/skills/explainer-podcast/references/listener.md` is the live listener profile; `zonecast profile edit` opens it in `$EDITOR`.

## 7. LLM usage notes for the implementer

- Use the Anthropic API (Python SDK `anthropic`). Default generation model: a current frontier model — as of this writing `claude-opus-4-8` for stages 3–5 quality-critical calls and `claude-sonnet-4-6` for classification/normalization; **verify current model strings and pricing at https://docs.claude.com before pinning** (models are config values, never literals in code).
- Long outputs: section generation targets ≤ 1,300 words/call — well within limits — but set `max_tokens` generously and handle `stop_reason == "max_tokens"` by continuing the call.
- All structured outputs (offers, blueprint, state): request JSON-only responses, parse defensively, retry with the parse error included on failure.

## 8. Data schemas (JSON)

### 8.1 `offers.json`
```json
{
  "topic": "string",
  "offers": [
    {
      "id": 1,
      "duration_min": 45,
      "word_budget": 6750,
      "depth": "standard",
      "driving_question": "string",
      "outline_preview": ["4-6 one-line beats"],
      "deliberately_excluded": ["string"],
      "format_recommendation": "solo | two_host",
      "style_file": "ml-theory"
    }
  ]
}
```

### 8.2 `blueprint.json`
```json
{
  "offer_id": 1,
  "title": "string",
  "driving_question": "string",
  "spine_analogy": {"image": "string", "mapping": {"concept": "analog"}},
  "sections": [
    {
      "n": 1,
      "name": "string",
      "job": "one sentence",
      "word_budget": 1000,
      "opens_with_tension": "string",
      "closes_opening_tension": "string",
      "connective_to_next": "but | therefore",
      "recap_beat": true
    }
  ]
}
```

### 8.3 `state-NN.json`
```json
{
  "after_section": 3,
  "concepts_established": ["string"],
  "live_analogies": [{"image": "string", "maps_to": "string"}],
  "open_loops": ["string"],
  "callbacks_available": ["string"],
  "words_spent": 3120,
  "words_remaining": 3630
}
```

### 8.4 `manifest.json`
```json
{
  "episode_id": "2026-07-15-attention-from-the-ground-up",
  "title": "string",
  "duration_target_min": 45,
  "duration_actual_sec": 2710,
  "format": "solo",
  "source": {"type": "topic | pdf | url", "ref": "string"},
  "files": {"mp3": "path", "chapters": "path", "script": "path"},
  "costs": {"llm_input_tokens": 0, "llm_output_tokens": 0, "tts_characters": 0, "estimated_usd": 0.0},
  "created_at": "iso8601",
  "published": false
}
```

## 9. Repo layout

```
zonecast/
├── pyproject.toml
├── config.yaml
├── .env.example
├── prompts/
│   └── skills/explainer-podcast/     # extracted from explainer-podcast.skill
│       ├── SKILL.md
│       └── references/{listener,style-guide,tts-production}.md
├── styles/                            # FR-10 cached field guides
├── src/zonecast/
│   ├── cli.py                         # typer app
│   ├── pipeline.py                    # stage orchestration + checkpointing
│   ├── stages/
│   │   ├── ingest.py, plan.py, blueprint.py, generate.py,
│   │   ├── polish.py, render.py, package.py, publish.py
│   ├── llm.py                         # Anthropic client wrapper, JSON-mode helper, cost tracking
│   ├── tts.py                         # ElevenLabs wrapper, chunker, clip cache
│   ├── audio.py                       # ffmpeg stitch, loudnorm, chapters
│   ├── feed.py                        # RSS generation
│   └── schemas.py                     # pydantic models mirroring §8
├── episodes/
│   └── <episode_id>/
│       ├── source/  draft/  script/  audio/  manifest.json
└── tests/
```

## 10. CLI spec (typer)

```
zonecast create "diffusion models" [--duration 60] [--depth deep] [--auto]
                [--pdf path | --url u] [--session "3h ride"] [--two-host]
zonecast resume <episode_id>            # re-run from first incomplete stage
zonecast redo <episode_id> --stage polish   # invalidate a stage + downstream
zonecast publish <episode_id>
zonecast list
zonecast profile edit
zonecast feed url
```

`create` runs stages 1–7 (and 8 unless `--no-publish`), pausing once at the offer selection unless `--auto`.

## 11. Non-functional requirements

- **Resumability/idempotency:** each stage writes a completion marker; `resume` skips completed stages; TTS clip cache keyed by (voice, model, text-hash) guarantees no double billing.
- **Cost tracking:** every LLM/TTS call logs tokens/characters; manifest totals must be accurate to ±10%.
- **Observability:** structured logs per stage; `--verbose` streams LLM output live.
- **Runtime target:** 60-min episode end-to-end in ≤ 15 min wall clock (TTS chunks may render concurrently, ≤ 4 parallel to respect concurrency limits).
- **Secrets:** never log API keys or the feed URL.

## 12. Error handling matrix

| Failure | Behavior |
|---|---|
| PDF extraction empty/garbled | Abort ingest with actionable message (suggest `--url` arxiv variant) |
| Invalid JSON from LLM ×3 | Fail stage, persist raw output for inspection |
| Section > ±20% budget after retry | Accept, log warning, surface in manifest |
| TTS chunk fails ×3 | Fail render stage; completed clips cached; `resume` retries only failures |
| ffmpeg missing | Preflight check at startup with install hint |
| Feed upload fails | MP3 remains local; `publish` retryable independently |

## 13. Acceptance criteria

- **M1:** `zonecast create "how transformers work" --duration 15 --auto` produces a playable MP3 whose duration is within ±15% of 15 min; script passes automated checks: recap beats present at expected cadence (regex on recap markers), no markdown artifacts in TTS text, per-section word budgets within tolerance; kill the process mid-generate → `resume` completes without regenerating finished sections and without duplicate TTS spend.
- **M2:** New episode appears in Overcast via the private feed within 5 min of `publish`; chapters navigable.
- **M3:** `--two-host` renders two distinct voices; no "wow/fascinating" reaction lines (lint the script against the ban list).
- **M4:** A topic in a novel field (e.g., "CRISPR base editing") creates `styles/molecular-bio.md` on first run and reuses it (no distillation call) on second run.

## 14. Open questions (decide during implementation, defaults given)

1. Search enrichment provider for `--research` — default: skip in M1.
2. TTS model tier — default: start with the flagship multilingual model for quality; add a `--fast` flag using the Flash tier (~half cost) for daily-driver episodes.
3. Feed privacy — default: unguessable URL path; optional basic-auth via storage provider if supported by chosen podcast app.

## 15. Appendix — key constants

- Speaking rate: 150 wpm → words = minutes × 150; characters ≈ words × 5.5.
- 15 min ≈ 2,250 words ≈ 12k chars; 60 min ≈ 9,000 words ≈ 50k chars; 120 min ≈ 18,000 words ≈ 100k chars.
- ElevenLabs API list pricing (verify current): ~$0.10/1k chars flagship, ~$0.05/1k Flash/Turbo → 2-h episode ≈ $5–10 TTS.
- Section size: 800–1,200 words. Recap cadence: every 8–12 min. Working-memory ceiling: 3 named objects.
