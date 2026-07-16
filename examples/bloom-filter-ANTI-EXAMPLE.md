# ANTI-EXAMPLE: "How a Bloom Filter Works" — why this reads as AI-generated

> **This is a labeled anti-example. It is what NOT to do.** It dissects a real script this
> system produced (a ~6-minute Bloom-filter explainer) that a listener immediately clocked as
> "super AI-generated." Read it alongside `style-guide.md` §9. The point isn't that the script
> broke the rules — it's that it followed them *joylessly*, and that's the failure that matters.
>
> The good, human counterpart is `diffusion-overview-15min.md`. Contrast the two.

## The verdict

The script is **skill-compliant but joyless.** It has a spine analogy (a wall of switches,
stampers that flip them), a driving question, discovery framing, and a recap — it ticks every
structural box in the skill. It still reads as generated, because it executes every technique
at *uniform intensity with zero friction*. Two of the hardest-to-fake human moves the skill
explicitly asks for are simply absent: **self-interruption** (Carlin's register, SKILL §1) and
**marked analogy-breakage** (style-guide §4). Their absence, more than any single word, is the
tell.

## Root cause, in three

1. **Frictionless perfection.** Nothing hesitates, self-corrects, arrives out of order, or
   resists the analogy. Real explanation has texture — a stumble, a "wait, better to say it
   this way," an analogy that leaks and gets patched. This script is sanded smooth, and
   smoothness at this level is the signature of generation.
2. **Told-not-shown affect.** It repeatedly instructs the listener how to feel instead of
   engineering the moment and letting the feeling be earned. That directly violates the
   pointing-arrows rule: say what to attend to, never how to feel.
3. **Formulaic rhythm and reflexive constructions.** The long-sentence/punch-fragment
   metronome, the recurring "Here's the—" opener, the "not X, not Y, just Z" antithesis, and
   the tricolon are deployed as *defaults*, not choices. Their repetition is the tell — the
   model can't hear itself reusing a mold.

## The tells, quoted from the script

**A — "not X, it's Y" antithesis, on repeat.** The negation-then-correction is the most
fingerprint-heavy construction here; it appears five-plus times and becomes a tic.
> "That's the knob. **Not the count of addresses, not the size of your data.** Just: how many switches do I hand each item?"

> "Which makes each of those coincidences easier, **not harder.**"

Fix: use it *once*, where you're genuinely dislodging a belief the listener holds. The good
example uses it exactly once — "she recovers no such thing. Ours recovers **some** painting" —
saved for the moment the analogy breaks.

**B — the one-word fragment as a beat-marker.** "Good." "Except." "One percent." "That's the
peak." The clipped fragment is reached for at almost every section seam — a drummer hitting the
same fill every four bars. Used rarely, the hard stop detonates; used as the default cadence,
it flattens into mannerism. ("Except." even stands alone as its own paragraph — a very
recognizable AI "dramatic pivot.")

**C — hollow enthusiasm / told-not-shown.**
> "Here's the click, and **it's cleaner than you'd expect.**"

> "And once you know that, **something beautiful falls out.**"

> "And here's the **genuinely strange** part..."

> "**Sit with that,** because it's the tension everything hangs on."

The narrator keeps *asserting* that things are beautiful, strange, cleaner-than-expected. "Something
beautiful falls out" is the narrator applauding his own explanation. The good example never
once tells you something is beautiful; it shows you a machine that creates without being taught
to, and lets "And yet." carry the awe.

**D — over-signposting the stakes, same frame three times.**
> "So here's the tug-of-war, **and it's the whole episode.**"
> "Let me make that a number, because **the number is the whole payoff.**"
> "...because **it's the tension everything hangs on.**"

Four "this is the important one" flags in 900 words, all the same superlative mold ("the whole
X," "everything hangs on"). The style guide says vary signposts and never reuse a phrasing.
When everything is flagged as the crux, nothing is.

**E — stock "Here's the—" openers.** "Here's a thing that shouldn't be possible." / "Here's the
tug-of-war" / "Here's the click" / "here's the genuinely strange part." ~7 hits. A human burns
through their "here's" allowance and starts varying; the model generates each sentence locally
and never hears the repetition.

**F — terrain-metaphor stacking (the exact thing the guide warns about).**
> "the part worth carrying up **the climb** with you"

The listener is *literally* climbing on a bike; the style guide and the good example both flag
that climb/ascent metaphors collide with that and must be budgeted. Dropping "up the climb"
with no awareness proves the generation followed the analogy rules but not the meta-warning a
few sections later in the same file.

**G — tidy bow-tie ending / manufactured profundity.**
> "Everything ... comes down to **one confession. Your own tolerance for being wrong, turned
> into switches.**"

A strain for a mic-drop — reframing a design parameter (false-positive rate) as a moral
revelation about the self. Contrast the good ending, which re-derives the *mechanism*
("break enough things, carefully — and pay attention on the way back"). The good last line is
**content**; this one is sentiment. Sentiment-as-finale is a reliable tell.

**H — over-explaining one beat three ways in a row.**
> "More stampers make a false yes need more coincidences... But more stampers also crowd the
> wall... Both effects get stronger at the same time, pulling in opposite directions. Therefore
> there has to be a number of stampers where those two forces exactly balance."

The idea is stated, restated, then "therefore"-restated a third time in one breath. The
redundancy rule wants re-derivation *minutes apart from a new angle*, not three paraphrases
back-to-back. This is padding by circling.

## Rhythm analysis: the counterfeit variety

Measured across the script, the sentence-length distribution is **bimodal and artificial**: a
cluster of engineered 1–4 word "impact" fragments (tell B) plus a fat band of 14–24 word
explanatory sentences — with the natural in-between largely *absent* (the 8–12 word
conversational aside, the 30–40 word clause-stacked build). It reads as uniform because the
*variation itself is formulaic*: long explanatory sentence → punch fragment → long → punch.
**Predictable alternation is not rhythm; it's a metronome.**

The good example sustains a genuine 40-plus-word build — "A thousand tiny, unglamorous steps
that individually change almost nothing and collectively change everything — which, I suspect,
is an idea that lands a little differently in hour two of a ride" — and lets "And yet." sit
isolated pages later. That's real dynamic range. The Bloom script never sustains a build that
long and never lets a fragment sit that alone.

## Three concrete contrasts with the good example

- **Opening.** Bloom *announces* the anomaly ("Here's a thing that shouldn't be possible") then
  explains. Diffusion drops you into a concrete sensory scene (static resolving into "a face
  with pores, and stray hairs, and a catchlight in each eye") and only *then* names it flatly:
  "That should bother you." Show-then-name reads human; name-then-show reads like a summary of a
  good opening.
- **Analogy.** The Bloom stamper/switch analogy maps cleanly start to finish and **never
  breaks** — which is too clean; real teaching analogies leak, and saying where is what builds
  trust. Diffusion makes the breakage its climax ("our analogy just quietly broke — and the
  break is the whole point").
- **Ending.** Bloom re-abstracts into a life lesson; Diffusion re-derives the mechanism in one
  breath and opens a real next-episode door. Last line = content, not psyche.

## Rewrite demonstration (one passage)

**Original — the "sweet spot" reveal (dense with tells C, D, A, B):**
> So where is it? Where do those two forces cancel? Here's the click, and it's cleaner than you'd
> expect. The balance point lands right where the wall sits about half-lit. Half the switches on,
> half still off. Fewer stampers than that, and the wall's too empty... More stampers than that,
> and the wall's too crowded... Dead center, half and half, is the sweet spot. That's the peak.

**Rewrite — same content, same analogy, human voice:**
> So where does that balance actually sit? I'll tell you the answer and then I want you to check
> whether it feels right, because it surprised me the first time. The two forces cancel out right
> when the wall is half-lit. Half the switches on, half off. That's it.
>
> Why there? Think about the two failure modes. If you've got too few stampers, most of the wall
> is still dark — and all that darkness is wasted, because every dark switch was a chance to catch
> a false yes and you didn't take it. Push the other way, too many stampers, and now the wall's so
> crowded that finding a lit switch tells you almost nothing — half of them are lit anyway, so a
> "yes" is basically a coin landing heads three times, which happens. Somewhere between wasteful
> and crowded, the wall's exactly half full. That's your peak.

**What changed and why:**
- Cut "Here's the click, and it's cleaner than you'd expect" (hollow enthusiasm + stock opener);
  replaced with an *invitation to verify* that hands ownership to the listener instead of the
  narrator congratulating himself.
- Added real friction — a question and a beat of thought ("Why there? Think about the two failure
  modes") — restoring discovery framing.
- Broke the mirrored "Fewer stampers... / More stampers..." template so it doesn't scan as a
  parallel mold; varied length and phrasing.
- Rationed the fragments: one deliberate "That's it." instead of stacking "That's the peak."
- Made the abstraction concrete ("a coin landing heads three times, which happens") instead of
  "the coincidences come cheap."
- Introduced a genuine ~40-word build against a short beat — real dynamic range, not the
  medium-everything metronome.

---

*See `style-guide.md` §9 for the general rules distilled from this and from research into AI
writing tells. The generated script this analyzes lives (gitignored) under
`episodes/2026-07-16-how-a-bloom-filter-works/script/final.md`.*
