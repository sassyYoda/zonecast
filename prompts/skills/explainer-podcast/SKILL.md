---
name: explainer-podcast
description: Generates broadcast-quality explainer podcast scripts that teach technical concepts (ML, math, CS, papers) from the ground up in a 3blue1brown/Radiolab style, tuned for listening during long endurance training sessions. Use this skill whenever the user asks for a podcast, episode, audio explainer, "something to listen to," a script for TTS, or an audio-friendly explanation of a concept or paper — even if they don't say the word "podcast." Also use it when asked to plan, outline, budget, or polish any long-form spoken-word educational content.
---

# Explainer Podcast Script Generator

This skill turns a topic or paper into a script that teaches like Grant Sanderson, signposts like Radiolab, and holds attention over hours like Dan Carlin — while respecting one brutal constraint: the listener is on a bike at 140 bpm, cannot see anything, cannot take notes, and will not rewind.

The single most important idea, which everything below serves: **motivation is the bottleneck, not explanation quality.** A listener who badly wants the answer will follow you through hard material. A listener who doesn't will drift by minute four no matter how clear you are. Every structural decision in this skill exists to create and sustain that wanting.

## Before anything else

1. Read `references/listener.md` — who you're writing for and the conditions they'll be listening under. Nothing else makes sense without this.
2. Read `references/style-guide.md` — the distilled craft of the exemplar shows, plus duration templates.
3. If the input is a paper: extract and read it fully before planning. If it's a topic: research enough to know the landscape, the genuinely surprising parts, and what the standard textbook treatment gets wrong or makes boring.

## The pipeline (five passes)

Never write a script top-to-bottom in one shot. Long-form spoken audio degrades badly when generated linearly — pacing drifts, callbacks get forgotten, and word budgets blow out. Work in passes.

### Pass 1 — Assessment and the offer

Figure out what this topic actually demands, then let the user choose the contract.

1. Identify the **driving question** — not the topic, a question. "Attention mechanisms" is a topic. "How does a model decide which words matter to each other, when nobody told it?" is a driving question. If you can't phrase one the listener would genuinely want answered, you haven't understood the material well enough yet.
2. Map the **prerequisite chain** from the listener's baseline (in `listener.md`) up to the target. "From the ground up" means from *their* ground, not from arithmetic.
3. Produce **2–3 offers**, each with: duration, depth level, the driving question it answers, a 4–6 line outline, and what it deliberately leaves out. Leaving things out is a feature — name the cuts so the user can veto them.
4. Compute the word budget: **minutes × 150 words**. This is the contract. A 15-minute episode is ~2,250 words; 45 minutes ~6,750; 2 hours ~18,000.

Present the offers and wait for the user to pick (or pick the middle one if they've said "just go").

### Pass 2 — The blueprint

Turn the chosen offer into a section-by-section outline. For each section specify:

- **Job**: the one thing this section makes the listener understand or feel. One job per section.
- **Word budget**: 800–1,200 words per section (5–8 minutes) — for episodes of **30 minutes or more**. Longer sections lose people; shorter ones feel choppy. **Overview episodes (≤ 20 min) are the exception:** a 2,250-word episode cannot afford three 800-word minimums, let alone the five beats the overview template calls for. Use beats of **350–1,000 words** instead. Applying the 800-word floor to a short episode is arithmetically impossible and will silently blow the contract.
- Budgets count **spoken words only** — see Pass 4.
- **The tension**: what question is open at the start of this section, and what new question opens as it closes. Sections chain with "but" and "therefore," never "and then." If two adjacent sections connect with "and then," merge or reorder them.
- **Recap beat**: where in the section the running recap lands (see audio constraints below).

Also choose the **spine analogy** now: one concrete, physical, extended metaphor introduced in the first ten minutes that the entire episode maps back onto. Radiolab-style explainers live or die by this. It must be something the listener can hold in their mind's eye with zero visual aid — a landscape, a room full of people, a machine with parts. Every subsequent abstraction gets attached to the spine rather than floating free.

Sanity-check the blueprint: does the whole thing build to a **climax** — the moment two previously separate ideas snap together and the driving question resolves? If the outline is just a sequence of explanations with no convergence, restructure until there is one. The listener should feel the click.

### Pass 3 — Draft, section by section

Write one section at a time. Between sections, maintain a **state block** (keep it in your working context, not in the script):

```
STATE after section N:
- Concepts now safely assumed: ...
- Live analogies and their mappings: ...
- Open loops (questions raised, not yet answered): ...
- Callbacks available (jokes, images, phrases planted earlier): ...
- Words spent / words remaining: ...
```

Update it after every section. This is what prevents the 90-minute mark from contradicting the 20-minute mark, and it's what makes callbacks possible — and callbacks are the cheapest way to make a long episode feel authored rather than generated.

Drafting rules (justifications in `references/style-guide.md`):

- **Concrete before abstract, always.** Start every new idea with a specific worked example or scenario, then name the general pattern it exemplifies. Resist the textbook order (definition → examples) even when it feels more efficient — it is more efficient only for people who already understand.
- **Discovery framing.** Where possible, pose the problem the concept was invented to solve and let the listener almost invent it themselves before you reveal it. "So how would *you* fix this? You might think to... and that almost works, except..." The listener should periodically feel clever.
- **Anticipate the objection.** At any moment, the sharpest version of the listener has a "wait, but what about—" forming. Voice it for them, at the moment it would naturally form, and answer it. Getting this timing right is most of what separates a great explainer from a competent one.
- **Numbers made visceral.** Never leave a magnitude naked. "175 billion parameters" means nothing at 140 bpm; "if you counted one per second, you'd finish in five and a half thousand years" means something.

### Pass 4 — The read-aloud polish

A full editorial pass over the assembled draft, applying the audio constraints below plus:

- Read every sentence as sound. Kill anything you'd stumble saying aloud. Spoken sentences average 15–20 words; anything past 30 gets split.
- Verify signposting at every section boundary (phrasebook in the style guide).
- Humor pass: sparse, dry, and load-bearing only — a joke should land on a concept, making it more memorable, never interrupt one. Cut any joke that requires a pause to work; TTS can't do comic timing reliably.
- Verify the redundancy rule: every load-bearing idea stated at least twice, in different words, minutes apart — once when introduced, once woven into later material. Not verbatim repetition; re-derivation from a new angle.
- **Anti-AI-tell pass — run the `style-guide.md` §9 checklist over the whole draft.** A script can satisfy every other rule here and still sound machine-generated, because the tell is craft applied *evenly* rather than any single broken rule. Hunt specifically for: the narrator naming feelings instead of showing them ("the genuinely strange part," "something beautiful"); throat-clearing openers ("here's where it gets interesting," "let's dive in"); the "not X, it's Y" antithesis used more than once; a long-sentence-then-punchy-fragment metronome instead of real rhythm variety; a bow-tie ending that reframes the mechanism as a life lesson; and reflexive "Here's the—" connectives. Two human moves are **required, not optional**, and are the ones most often missing: at least one genuine self-interruption/repair written into the text (the TTS won't improvise it), and the spine analogy's breakage marked out loud at the point it stops fitting. A draft with neither is coasting — fix it before shipping.
- **Emphasis must survive being spoken.** Italics do not exist in audio, and the TTS voice has no emphasis mechanism to convert them into — every `*marker*` is simply stripped before rendering. So any emphasis you would express with italics has to be carried by word choice or sentence structure instead. This bites hardest where a contrast *is* the point: "she recovers *a* painting, not *the* original" collapses to "she recovers a painting, not the original" — the same words, the meaning gone. Rewrite it so the contrast lives in the words themselves ("not the one that was there — *some* painting, one that could have existed"). Scan for italics at polish time and rewrite every one; do not leave them for the TTS pass, where the only remaining option is to delete them.
- Check the word count against the contract, **counting spoken words only**. Speaker tags, `[PAUSE:*]` markers, section headers, and the metadata block are not spoken and must not be counted. Counting the raw file instead inflates the total by roughly 15% and produces an episode that runs short of its contract while appearing to hit it. Over budget: cut a section's scope, never compress its prose into density. Dense prose is unlistenable.

### Pass 5 — TTS preparation

Read `references/tts-production.md` and convert the polished script into the TTS-ready format specified there (speaker tags, number normalization, pause markers, chunking for API limits).

## Audio constraints (non-negotiable)

These exist because the medium is ears-only and the listener is exercising. Violating any of them produces a script that reads well and listens badly.

1. **Nothing that requires seeing.** No "as shown above," no spelled-out equations, no notation. An equation must become either a sentence about relationships ("the loss is just: how wrong were you, squared, averaged over everything") or be cut. If a derivation can't survive translation into narrative, summarize what it accomplishes and move on.
2. **Names, not symbols.** Never "network A and network B" — give everything a vivid handle: "the forger and the detective," "the fast learner and the slow judge." Symbols are free to hold in working memory only when you can see them written down; the listener can't.
3. **Three-object limit.** Never require the listener to hold more than three named things in relation to each other at once. If a mechanism genuinely involves five components, introduce them in stages and let earlier ones fuse into a single chunk ("the whole encoder side — think of it as one box now — hands off to...").
4. **Recap every 8–12 minutes.** A 30–60 second "where are we" beat: what we've established, what's still open. Frame it as momentum, not review: "So here's the situation we've built up to..." The listener who zoned out for ninety seconds at an intersection re-boards here. This is the single highest-value structural element for exercise listening.
5. **Signpost importance explicitly.** The listener can't skim ahead to see what matters. Before anything crucial: "this next bit is the whole ballgame" or equivalent. Radiolab's producers call these pointing arrows and use them relentlessly — tell people what to pay attention to, never how to feel.
6. **Rewind-proofing.** Assume any given 60 seconds might be missed. No single missed minute should make the rest incomprehensible. This is what constraints 4 and the redundancy rule jointly guarantee — check it explicitly at polish time.

## Duration behavior

The duration doesn't scale the script linearly; it changes its shape. Templates in the style guide, but the principle: short episodes (≤20 min) are a single arc to one insight, ruthlessly scoped. Medium (30–60 min) get a full act structure with one major midpoint turn. Long (90 min+) are Carlin territory — they need *narrative* stakes, not just conceptual ones: the history, the rivalries, the failed attempts, the human story of why anyone cared, braided through the technical spine so the listener's attention has two threads to hold onto when either one alone would fatigue.

## Output format

Deliver the final script as markdown:

```markdown
# {Episode title — evocative, not descriptive}

**Driving question:** ...
**Duration target:** {min} min (~{words} words) | **Format:** {solo | two-host}
**Spine analogy:** ...

## Section 1: {name} [{word budget}]
[HOST] ...script text...
[GUEST] ...script text...   <!-- two-host format only -->
[PAUSE:short|long]          <!-- sparingly, at act boundaries -->

## Section 2: ...
```

Solo narration is the default. Offer two-host dialogue when the episode exceeds 45 minutes or the material is objection-rich — a second voice whose job is to be the listener's proxy (asks the forming question, demands the recap, pushes back) is worth the added production cost on long rides. Guidance for writing the second voice honestly (not as a sycophantic "wow, fascinating!" machine) is in the style guide.

## Reference files

- `references/listener.md` — the listener profile and session context. Read first, every time.
- `references/style-guide.md` — distilled craft from the exemplar shows, duration templates, openings, signposting phrasebook, humor and dialogue rules. Read before Pass 2.
- `references/tts-production.md` — ElevenLabs-specific formatting, chunking, number normalization, stitching, cost math. Read at Pass 5 only.
