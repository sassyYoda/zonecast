# Style Guide: Distilled Craft of the Great Explainers

This is a distillation of *techniques*, not a license to imitate any show's voice or reproduce its content. Everything here is stated as a principle to apply, in original words.

## Contents

1. The exemplars and what each one teaches
2. Openings
3. The signposting phrasebook
4. Analogy craft
5. Duration templates
6. Humor rules
7. Two-host dialogue rules
8. Endings
9. Sounding human, not generated (the anti-AI-tell layer)

---

## 1. The exemplars and what each one teaches

### 3blue1brown (Grant Sanderson) — the pedagogy spine

- **Invert the textbook.** Textbooks state the general abstraction, then populate it with examples — because that ordering is natural *once you already understand*. Sanderson's core move is the reverse: a specific motivating puzzle first, abstraction second, so the general definition arrives as the answer to a question the viewer already has. Adopt this ordering unconditionally.
- **Motivation is the limiting factor.** He treats explanation quality as secondary to making the learner *want* the understanding. Practical test for every section: if the listener didn't have to be here, would they stay?
- **Treat the lesson as a story.** Even a technical derivation has characters (the quantities involved), conflict (the thing that shouldn't be possible, the tension between two constraints), and a climax — the moment two ideas that were developed separately combine and the problem cracks open. Build every episode toward at least one such moment, and make it felt: slow down, signpost it, let it land.
- **Ownership.** The listener should feel they *could have* invented the idea. Walk the plausible dead ends ("your first instinct might be X — and that almost works") so the real solution feels earned, not announced.
- **Audio translation caveat:** his medium is animation; this skill's medium is not. Every "picture this" must be constructible from words alone by a listener with closed eyes. Prefer scenes with agents doing things (people sorting mail, water flowing downhill) over static geometric pictures, which are hard to hold without a screen.

### Radiolab / NPR narrative radio — the audio craft

- **Pointing arrows.** Jad Abumrad's storytelling philosophy: don't tell listeners how to feel, tell them what to pay attention to. Drop explicit markers right before important moments — "and this is where the whole thing turns." Use them at every crucial beat; in audio there is no such thing as over-signposting, only clumsy signposting.
- **One driving question.** NPR's radio training doctrine: a linear, ears-only audience gets lost easily, so a piece succeeds by answering ONE question, with the narrator acting as tour guide. Multi-question episodes become multi-part series, not longer episodes.
- **Answer the forming question.** The most-praised Radiolab structural trait: information arrives in the same order that questions form in the listener's head — just as "yeah, but what about..." crystallizes, the answer appears. In drafting, literally simulate the listener's internal monologue at each paragraph and check the next paragraph addresses it.
- **Pace through rhythm contrast.** Alternate dense explanatory passages with lighter conversational beats — an aside, a reaction, a quick story. Density fatigue, not difficulty, is what makes people tune out. Roughly: no more than 90 seconds of maximum-density explanation without a breather.
- **But/therefore, never and-then.** Consecutive beats must connect by complication ("but") or consequence ("therefore"). A chain of "and then" is a list wearing a story costume.
- **Legitimate backgrounding.** When context must interrupt momentum, say so explicitly — "to see why this matters, you need thirty seconds of backstory" — then return with an explicit "okay, so, back to our problem." The detour framing preserves the listener's map.

### Hardcore History (Dan Carlin) — long-form endurance

- **Multi-hour attention is earned with human stakes.** Carlin holds people for 4+ hours by treating history as drama: real people under pressure, empathy for their impossible decisions, vivid sensory grounding. For technical episodes, the equivalent thread is the human history of the idea — who was stuck, what the field believed that turned out wrong, the rivalry or accident behind the breakthrough. In 90-minute-plus episodes, braid this narrative thread through the conceptual one so attention can switch tracks instead of dropping.
- **Intimacy over production.** His format is one voice, no gloss, like a brilliant friend monologuing by a campfire. Conversational register, contractions, occasional self-interruption ("actually, wait, the better way to say this is...") reads as human and holds attention better than polished prose.
- **Recurring perspective questions.** He returns to a framing question ("what would this feel like from the inside?") as a leitmotif. Give long episodes one recurring question that gets re-asked with more insight each act.

### Acquired — structure for long analysis

- Their long-form format works by hard separation of *narrative* and *analysis*: hours of chronological story first, then explicitly-labeled sections that extract the lessons and frameworks. Adopt the pattern for long episodes: story/mechanics first, then a clearly announced "so what does this all mean / what's the playbook" segment near the end. The label itself ("okay — analysis time") is a gift to a tired listener: it tells them the mode is changing and the payoff is starting.

---

## 2. Openings

Never open with a definition, a welcome, or an agenda. The first 60 seconds buy the next 60 minutes. Three patterns, in order of preference:

1. **Cold open on a concrete anomaly.** Drop into a specific moment or fact that shouldn't be possible given what the listener knows. Then: "By the end of this ride, you'll understand exactly why that works." (This is the promise; the episode is the payoff.)
2. **The mystery.** Pose the driving question as a genuine whodunit with a named tension. Works especially well for papers: "The result in this paper says X. Everyone believed not-X for a decade. Somebody's wrong, and finding out who is going to take us somewhere strange."
3. **The stakes open.** Why this idea mattered to real people — the thing that was broken, the money/careers/science blocked on it — then reveal the concept as what unblocked it.

After the hook, one compact contract: what question we're answering, roughly how long the journey is, and the two or three big landmarks. Then go.

## 3. The signposting phrasebook

Vary these; never reuse the same phrasing twice in an episode.

- Importance: "If you remember one thing from this whole episode, it's the next two minutes." / "Here's the part everything else has been building toward."
- Turn: "And this is where the story flips." / "Everything I've told you so far is the setup. Here's the twist."
- Backgrounding: "Quick detour — ninety seconds of context, and I promise it pays off."
- Return: "Okay. Back to our forger and detective."
- Recap: "Let's take stock, because we've built up quite a machine here..." / "Quick altitude check: here's the terrain we've covered."
- Pre-difficulty warning: "The next stretch is the steepest climb in the episode. Take it easy, I'll go slow, and there's a recap at the top."
- Post-difficulty relief: "That was the hard part. Genuinely. It's all downhill from here."

**Watch the terrain metaphors stacking.** Several phrases above are climb/descent-shaped, and
the listener is *literally* climbing. Those sanctioned metaphors silently consume the same
budget as the deliberate nods to the listener's setting that `listener.md` caps at once or
twice an episode — and the two are indistinguishable to a listener. A 15-minute test draft
landed "top of the hill," "steepest climb," "recap at the top," "hour two of a ride," and
"earn its own ride": individually defensible, collectively a running bit, which is exactly what
`listener.md` forbids. Budget them **together**, not separately, and vary the register — reach
for a non-terrain signpost ("here's the part everything has been building toward") when you've
already spent the terrain ones. This compounds badly over 90+ minutes.

## 4. Analogy craft

- **One spine, few satellites.** One extended analogy carries the episode (chosen in Pass 2). Local one-shot analogies are fine, but they must not conflict with the spine's imagery. Two competing extended metaphors is worse than none.
- **Physical, agentive, ears-native.** Best spines involve agents doing things in a space: a mailroom, a courtroom, a market, an ecosystem, a kitchen. These narrate well. Avoid analogies that are secretly diagrams (grids, axes, arrows) — they require eyes.
- **Map explicitly, and mark the breakage.** When introducing the spine, name the mapping out loud ("the judge is the loss function — every dish the chef sends out gets a score"). And when the analogy breaks — every analogy breaks — say so at the moment it matters: "here's where the kitchen metaphor lies to you, and the lie is actually the interesting part." Marked breakage converts an analogy's weakness into a teaching beat and keeps trust.
- **Upgrade, don't abandon.** When the material outgrows the spine, extend it rather than switching: the kitchen gains a second kitchen, the judges start disagreeing with each other. Continuity of imagery is continuity of understanding.

## 5. Duration templates

Word budget = minutes × 150, counted in **spoken words only** (see SKILL.md Pass 4).
Section = 800–1,200 words for episodes ≥ 30 min. **Overview episodes (≤ 20 min) use beats of
350–1,000 words** — the 800-word floor does not fit inside a 2,250-word contract.

### Overview — 15–20 min (~2,300–3,000 words)
One arc, one insight. Hook (1 min) → minimal scaffolding, only prerequisites the punchline needs (5 min) → core mechanism via spine analogy (7 min) → the click + why it matters + where it breaks (4 min) → closing recap (1 min). Ruthless scoping: name what you're skipping in one sentence and move on. No secondary threads.

### Standard — 30–60 min (~4,500–9,000 words)
Three acts. Act I: hook, contract, scaffolding, spine established. Act II: the mechanism built in stages, each stage a but/therefore consequence of the last; midpoint turn — a complication that reframes the first act ("except that can't be the whole story, because..."). Act III: resolution/climax, implications, honest limitations, recap. Recaps at each act boundary plus every ~10 minutes inside acts.

### Deep dive — 90–150+ min (~13,500–22,500+ words)
Braided structure: conceptual thread + human/historical thread, alternating emphasis. Front-load the hardest technical material (fatigue rule from listener.md). Explicit "analysis time" segment in the final third (Acquired pattern). A recurring perspective question re-asked each act (Carlin pattern). Chapter announcements at each major boundary ("Part three: the part where everything breaks") — long-haul listeners orient by chapters. For papers at this length: the field before the paper → the problem in full depth → the idea → why it works → what it broke/opened → honest criticism.

## 6. Humor rules

- Dry, brief, and attached to content. The best jokes are load-bearing: they compress an attitude toward the material ("the authors describe this step as 'straightforward,' which is doing a lot of work in that sentence").
- Frequency ceiling: a few per 15 minutes. Below the ceiling, humor is seasoning; above it, the episode stops being trustworthy.
- Never punch at the listener. Self-deprecation and gentle irreverence toward the field's pretensions are the safe registers.
- No jokes that depend on timing, silence, or funny voices — TTS flattens them.

## 7. Two-host dialogue rules

The second voice is the listener's proxy, not a hype machine.

- Give the proxy a real epistemic state: they know the listener's baseline, nothing more. Their questions are the actual forming-questions a smart listener would have, asked at the moment they'd form. This mechanizes Radiolab's answer-the-forming-question principle.
- The proxy is allowed to be wrong out loud ("wait, so it's basically just a lookup table?" — "so close, and the way it's not is the whole idea") — a wrong guess corrected teaches more than a right answer stated.
- The proxy demands recaps and translations ("okay, say that again but slower"), which makes the recap cadence feel natural instead of scripted.
- Ban list: "Wow." "Fascinating." "That's incredible." Reaction lines must contain content — a reformulation, an objection, a connection — or be cut.
- Keep turns short. Real dialogue averages 1–3 sentences per turn; monologues with interruptions are fine, but label the show honestly as narrated-with-a-foil rather than pretending symmetry.

## 8. Endings

- The closing recap is a *re-derivation in miniature*, not a table of contents: retell the whole arc in 60–90 seconds using the spine analogy end-to-end, now compressed because the listener owns every piece.
- Then one open door: the question this episode's answer newly makes askable — ideally a natural next-episode seed.
- End clean. No "thanks for listening," no calls to action, no outro filler. Last sentence should be worth being the last sentence.

---

## 9. Sounding human, not generated (the anti-AI-tell layer)

You can follow every rule in sections 1–8 and *still* sound like a machine. This is the failure mode that matters most: a script that hits all its marks — spine analogy, driving question, discovery framing, recap — and is nonetheless unlistenable because it's generated-feeling. The tell is almost never a broken rule. It's the craft applied **evenly**: every technique at the same intensity, every sentence equally polished, every transition frictionless, the narrator constantly announcing how you should feel. See `examples/bloom-filter-ANTI-EXAMPLE.md` for a produced script dissected line by line — read it, because recognizing these in your own draft is most of the work.

**The one diagnosis under all of it:** AI writing is *uniform and symmetric*; human writing is *selective and asymmetric*. You cannot emphasize everything — emphasis **is** the act of choosing. Dwell on the one idea that matters; rush the other three. A script that distributes attention evenly has, in effect, no point of view about what's important, and that evenness is the signature of a machine. Every rule below is a way of breaking the smooth, even surface a language model defaults to.

**Show the feeling; never name it.** The sharpest tell is telling the listener how to react — "here's the genuinely strange part," "something beautiful falls out," "sit with that," "the fascinating thing is." This is the pointing-arrows rule (§3) violated: an arrow says *what to attend to* ("watch the temperature now — it's about to do something it shouldn't"), never *how to feel about it*. If a moment is beautiful or strange, build the beat and let the listener's own "huh" arrive. The narrator applauding their own explanation ("cleaner than you'd expect") is the machine congratulating itself.

**Assert; don't announce.** Cut the throat-clear. These openers are worse spoken than written and belong on a hard ban list: "let's dive in / unpack / break this down," "here's where it gets interesting," "but wait, there's more," "it's important to note that," "the thing about X is." Just say the thing — if it's interesting, the listener will notice. Also watch **"Here's the—"** as reflexive connective tissue; it's a comfortable generation crutch, so burn through two and then vary or cut.

**One antithesis per episode, and earn it.** "It's not X, it's Y" — "not the count, not the size, just: how many switches" — is the single most AI-fingerprinted construction there is. It manufactures emphasis by negating a strawman. Use it **once**, at the moment you're genuinely dislodging a belief the listener actually holds (a real misconception-correction: "you'd think entropy means disorder — it doesn't, quite"). Everywhere else, just assert Y and delete the "not X" half.

**Make the rhythm real, not a metronome.** This is the highest-value, most audible rule, because spoken delivery lives on rhythm. Vary sentence length hard — a two-word sentence against a forty-word build (human sentence-length variance runs far wider than a model's default even band). **But beware the counterfeit:** a repeating long-sentence-then-punchy-fragment pattern is *not* rhythm — predictable alternation is its own tell, a drum machine instead of a drummer. You need the genuine in-between the model omits: the 8-to-12-word conversational aside, and the 30-to-40-word clause-stacked sentence that earns its length before you break to something short. And ration the standalone one-word fragment ("Good." "Except.") — one per section at most; as a section-seam default it flattens into mannerism. Put the payoff word **last** in the sentence: in audio the last word before the pause is what's remembered.

**Leave friction in — this is the move most often missing.** Generated prose never stumbles, never doubles back, never arrives at an idea slightly out of order. Real explanation has texture. At least once an episode, genuinely self-interrupt and repair ("the cache — no, better: think of it as a little notebook the processor keeps on its desk"); let the narrator admit difficulty ("this one took me three tries to get"); reconsider mid-thought ("the best way to see this is — actually, wait, here's a cleaner way"). Because the TTS engine will not improvise hesitation, **the stumble has to be written as text** — the em-dash, the restart, the "wait" are on the page or they never happen. Frictionless perfection is the deepest tell; a mind that's actually working leaves marks.

**Every analogy leaks — say where it does.** A metaphor that maps perfectly from start to finish is too clean to be true, and that cleanness reads as generated. Mark the breakage out loud (this is already §4, but it is the rule most often skipped): the moment the analogy stops fitting is usually the best teaching beat in the episode. An analogy that never resists you is a missed human move and a sign the draft is coasting.

**Don't end on a life lesson.** The reflex to close on manufactured profundity — reframing a mechanism as a truth about the self ("your own tolerance for being wrong, turned into switches") — is a reliable machine tell. End on the *mechanism* (a re-derivation in miniature, §8) or a genuine open door. The last sentence should be **content**, not a mic-drop about the human condition.

**Diction: plain, spoken, Anglo-Saxon.** The words that sound most generated the instant a voice says them: *delve, realm, tapestry, testament, underscore, paramount, myriad, foster, leverage, utilize, robust, seamless, harness, showcase, boast.* Nobody says these to a friend. Use the plain verb — *use* not utilize, *dig into* not delve, *solid* not robust, *important* not "plays a crucial role." Kill zombie nouns: "made a decision" → "decided," "the implementation of" → "building." And drop the reflexive analogy preface — instead of "think of attention as a spotlight," just say "attention is a spotlight."

**But do NOT sterilize — over-correction is its own AI tell.** If you scrub a script of every item above too hard, you get a lifeless, cautious, TED-narrator voice, which is just a *different* flavor of generated. Humans are specific, loose, and idiosyncratic — not clean. So **keep**: contractions, always (their absence is itself a robot tell); the occasional "basically / kind of / pretty much"; first person and real opinions ("this is the part everyone gets wrong," "honestly, the name is terrible"); sentences that open with "And," "But," "So"; one strong original analogy per concept; a single deliberate tricolon at a climax; and genuinely *uneven* enthusiasm — lit up here, waving past the bookkeeping there. The target is not "well-written." It's one specific smart person, out loud, thinking — with all the texture, restraint, and unevenness that implies.
