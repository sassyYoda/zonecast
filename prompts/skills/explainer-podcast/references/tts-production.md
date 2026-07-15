# TTS Production Reference

Read at Pass 5 only. Converts a polished script into audio-ready text and covers the pipeline mechanics. Provider specifics change often — treat the numbers here as ballpark and verify against current ElevenLabs docs before relying on them.

## Text normalization (do this in the script, never trust the TTS to guess)

TTS models mispronounce notation confidently. Rewrite everything as it should be *spoken*:

- Numbers and math: `1e-4` → "one times ten to the minus four" (or better, "a ten-thousandth"); `O(n log n)` → "n log n time"; `~0.7` → "about point seven"; ranges like `10–15%` → "ten to fifteen percent".
- Acronyms: decide pronunciation explicitly. Spell with spaced letters to force letter-reading ("G P U", "R L H F"); write pronounceable ones as words ("relu" → "RAY-loo" on first use, then "relu"). Establish each on first appearance, stay consistent.
- Names and terms with unintuitive pronunciation: give a phonetic respelling on first use in the script text if the natural spelling misleads ("Dijkstra — DIKE-struh").
- Symbols never survive: `→` becomes "maps to" or "leads to"; `≈` becomes "roughly"; `*`, `_`, `#`, backticks, and markdown artifacts must be stripped from the spoken text.
- Citations, URLs, bracketed asides: cut entirely or convert to speech ("there's a 2017 paper on this — the famous one").

## Delivery markup

- Keep sentences short; punctuation is the main pacing control most models respect. Em-dashes and ellipses produce natural hesitations; paragraph breaks produce longer pauses.
- ElevenLabs' newer models support inline audio tags for delivery (emotional register, laughter, pauses) and the older models do not — check the current model's documentation and use whichever pause/expression mechanism it supports rather than assuming. Use delivery tags sparingly: one per few paragraphs at most, at genuine beats. Over-tagged scripts sound deranged.
- The `[PAUSE:short|long]` markers from the script format are *your* markers — translate them into the target model's mechanism (punctuation, break tags, or splitting the audio request) at render time.

## Chunking and stitching

- Generate audio in chunks of roughly 2,000–5,000 characters, split at paragraph boundaries — never mid-sentence. Long single requests degrade in delivery consistency and are painful to retry.
- Use the provider's continuity features where available (request stitching / previous-text context) so prosody doesn't reset at chunk boundaries; at minimum, split at section boundaries where a prosody reset sounds natural.
- Two-host format: render each speaker's lines with a distinct voice ID, in script order, as separate clips.
- Assemble with ffmpeg: concatenate clips in order, insert 300–600 ms of silence at speaker changes and 1–2 s at section boundaries, then loudness-normalize the full episode to podcast standard (-16 LUFS mono / -19 LUFS stereo is the common target; `ffmpeg -af loudnorm=I=-16:TP=-1.5:LRA=11`).
- Export: MP3, 128 kbps mono is plenty for speech and keeps a 2-hour episode ~110 MB.

## Cost math (ballpark, mid-2026)

- Script characters ≈ words × 5.5 (English incl. spaces). 15 min ≈ 12k chars; 60 min ≈ 50k; 120 min ≈ 100k.
- ElevenLabs API list pricing has been about $0.10 per 1k characters for the flagship multilingual models and about $0.05 per 1k for Flash/Turbo tiers; subscription plans bill the same generation in credits (roughly 1 credit/char flagship, ~0.5 Flash). So a 2-hour episode ≈ $5–10 of TTS; a 15-minute overview well under $1. Cheaper providers (OpenAI, Gemini/Polly-class) run at a fraction of that if voice quality is acceptable — worth A/B testing for daily-driver use.
- LLM cost for the script itself (multi-pass on a frontier model) typically lands in the same few-dollars range per long episode. Total: a 2-hour custom episode ≈ the price of a coffee.

## Delivery to the phone

- Simplest robust path: upload MP3s to object storage (S3/R2), maintain a single `feed.xml` (RSS 2.0 with iTunes namespace tags: title, description, enclosure URL, duration, pubDate per episode), and subscribe to the feed URL in a podcast app that accepts private feeds (Overcast, Pocket Casts, Apple Podcasts). Spotify does not accept arbitrary private feed URLs — don't design for it.
- Add `<itunes:duration>` and chapter markers (Podcasting 2.0 `<podcast:chapters>` JSON, supported by Overcast/Pocket Casts) using the script's section boundaries — chapters are genuinely useful mid-ride for "skip back to the start of this section."
