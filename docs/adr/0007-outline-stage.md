# ADR 0007: The outline stage

- Status: accepted
- Date: 2026-08-20
- Resolves: [Lock the outline stage: grouping, coverage, and cross-slide facts](https://github.com/EastonBrown/engr-689-slide-study-agent/issues/10)
- Amended: 2026-08-20, "Which 30 the cap keeps", while fixing [issue 32](https://github.com/EastonBrown/engr-689-slide-study-agent/issues/32). The cap of 30 is unchanged; which 30 it keeps is now specified, because a prefix could not reach slides 55 to 56.
- Amended: 2026-08-20, "The three-per-topic cap is hard", resolving [issue 35](https://github.com/EastonBrown/engr-689-slide-study-agent/issues/35). Ten questions is the quiz target, not permission to exceed the cap; a small deck ships short after the quiz generator's one regeneration attempt.
- Builds on: [ADR 0002](0002-per-slide-note-schema.md), [ADR 0003](0003-cross-deck-topic-taxonomy.md), [ADR 0004](0004-artifact-layout-and-memory-schema.md), [ADR 0005](0005-quiz-answer-key-and-retake-schema.md)

## Context

[ADR 0002](0002-per-slide-note-schema.md) made the page reader blind to its
neighbours, so everything needing a view of the whole deck landed here.
[ADR 0003](0003-cross-deck-topic-taxonomy.md) then made this stage the topic
assigner. [ADR 0005](0005-quiz-answer-key-and-retake-schema.md) requires every
question to name a topic and cite at least one slide, and both of those come
from here. That makes the outline the largest unspecified stage in the pipeline
and the one the rubric's Planning row is about.

Five decks, 286 slides, 66 in the Day 3 deck the eval targets. Two things in
that deck constrain the design directly: the encoder-popularity chart appears on
slide 28 and again on slide 48, twenty slides apart, and the generation-versus-
retrieval comparison exists only across slides 55 and 56, where slide 56
extracts to zero characters.

The recurring theme in what follows is which decisions the model makes and which
the code makes. Every place the code can decide, it does, because those are the
numbers that end up on a presentation slide and have to be defensible in one
sentence.

## Decision

### A topic is a set of slides, not a run of them

A topic owns an ordered list of slide numbers. The slides need not be
contiguous, and a topic may reappear anywhere later in the deck. Topics are
ordered by their first slide.

Contiguous runs were the simpler model and the Day 3 deck rules them out: slides
28 and 48 are the same material, and a contiguous model must either call them
two different topics or invent a run that swallows the twenty slides between
them.

Covered slides are **partitioned**: every covered slide belongs to exactly one
topic. This is what keeps ADR 0003's `exposure` honest. If a slide could belong
to two topics, exposure would stop summing to the deck's covered slide count and
a topic could inflate its own exposure by overlapping its neighbours. With a
partition, `exposure` is the length of the slide list and needs no explanation.

### Coverage is computed in code from `page_role`

A slide is **covered** when its `page_role` is `content`. A slide is **skipped**
when its role is `title`, `agenda`, `section_break`, `references`, or `blank`.
The model does not get a vote.

Concept density and presence of non-decorative visuals were the alternatives,
and both require a second model judgment about a slide that has already been
read once. The failure mode that judgment introduces is undetectable: eleven
content slides quietly dropped from a 66-slide deck, and a review that reads
perfectly well without them.

Skipped slides stay in the outline as an explicit list with their role, so the
interface shows them as skipped rather than as missing, and so the count of
covered slides is auditable against the deck length.

Skipped means no topic, no exposure, and no citation in the review.

### A degraded slide still counts

A slide whose `page_role` is `content` and whose `reader_note` is non-null is
covered and keeps its exposure, because exposure measures how much of the
subject's material touched a topic and the slide was really there. It is flagged
`degraded` in the outline, the review marks it, and the quiz generator may not
cite it at all.

This follows from coverage being a function of `page_role` alone, so it is
stated rather than left to fall out of the rule by accident. It keeps a bad read
out of a question that cannot be defended on camera, without pretending the
slide did not exist.

### Cross-slide facts: the code proposes, the model confirms

A **bridged fact** is a fact that exists only across two or more slides. Slides
55 to 56 are the case that has to work.

Assembly is two steps. First the code proposes candidate slide pairs from three
signals:

- an edge in the reader's `Visual.relates_to_slides`, which ADR 0002 makes
  advisory,
- adjacent slides where the second has a null `title` or repeats the first's
  `title`,
- adjacent slides sharing a `Concept.name`.

Then one model call either composes a joined fact from a candidate or rejects
it. It cannot propose a pair that was not offered.

Letting the model hunt freely over all 66 notes would find slides 55 to 56 and
would also find several connections that are not there. There is no ground truth
that would catch a fabricated one, and a fabricated cross-slide fact is the
confident-and-wrong failure mode at its worst: it reads as the most impressive
output the pipeline produces.

The candidate set is capped at 30, and both the cap and the number of candidates
proposed before it are recorded in the outline, so a deck that was truncated is
distinguishable from one that fit.

**Which 30 the cap keeps.** A slide pair is one candidate however many of the
three signals proposed it, and the signals are merged onto it. Two of them, the
repeated title and the shared concept, fire on most consecutive content pairs,
so a 66-slide deck proposes roughly 65 pairs against a cap of 30 and the cap
always binds. Keeping the first 30 confines every candidate to the opening half
of the deck, which is the part least likely to hold a cross-slide fact and, on
the Day 3 deck, excludes slides 55 to 56 outright: the one pair this stage
exists to find. The cap therefore ranks pairs and then samples:

- a pair carrying a visual edge first, since that edge is deliberate and is the
  only signal that can propose a non-adjacent pair,
- then a pair two adjacency signals agree on,
- then a pair one signal proposed.

Inside whichever rank overflows the remaining slots, the sample is spread evenly
across the deck rather than taken as a prefix. The ranking is code, not a
judgment call, so it is auditable against the recorded pre-cap count.

Both paths run identical code and an identical prompt. On the text path slide 56
carries nothing, so the pair cannot be composed, and that failure is a
measurement rather than a missing feature.

### The question budget is arithmetic

ADR 0005 fixes a ten-question target. The split across topics is computed in
code, with no model call:

1. If the outline produced any bridged facts, one question is reserved for one
   of them.
2. The rest are allocated by largest-remainder proportional allocation over each
   topic's covered slide count, capped at three questions per topic.
3. A topic allocated zero questions is recorded as untested for this deck. It is
   not padded up to one.

The three-per-topic cap is hard. If the bridged-fact reservation plus the capped
topic allocation cannot reach ten, the outline ships the attainable budget. The
quiz generator may regenerate once for a shortfall, then records and ships the
short quiz. Raising the cap to force ten would make a small deck look like it
supports ten independent questions about the same topic.

The reserved question is the single question the text path provably could not
have written, which is what makes it worth a fixed slot rather than a share.

Zero is a real answer because ADR 0005's retake already looks for exactly that
signal when it fills its last four slots from topics with `seen < 3`. Padding
every topic up to one question would erase it.

A question's material is its topic's slide notes, and `source` is `visual` when
it comes from a `Visual.assertion`.

### Two model calls, both over the whole deck

- **Call A** does grouping and topic assignment together, over a compacted view
  of every note: `slide_number`, `page_role`, `title`, `concepts`, and each
  visual's `kind` and `assertion`. It drops `reading` and `verbatim_spans`.
- **Call B** confirms the bridge candidates, with the full notes for those
  slides only.

Allocation makes no call.

Grouping and topic assignment are one act under ADR 0003, where a topic is named
by either reusing a subject topic verbatim or declaring a new one with a reason,
so splitting them would mean naming things twice.

Per-topic calls were the tempting middle option and they are wrong here for a
structural reason rather than a cost one: a per-topic call cannot produce a
partition, because no call knows what the others claimed, and it cannot hold the
subject's topic list consistently across calls, which is the entire mechanism of
ADR 0003. Compaction is what buys controllability, not fragmentation.

### Contract violations degrade, they do not abort

The partition and ADR 0003's cap of 12 topics per deck are both things a model
can violate. Validation is in code, followed by one repair call naming the
specific violations. If the repair still fails:

- a slide claimed by two topics resolves to the first topic listed,
- a covered slide left unassigned is recorded in an explicit `unassigned` list
  and is not invented into a topic,
- more than 12 topics sets `topic_cap_exceeded` and keeps them all.

The run continues. ADR 0004 writes every stage boundary, so the outline exists
either way, and two days before a demo a hard failure trades a real artifact for
a purity point. Each of the three outcomes is visible in the artifact, which
makes it material for the limitations section rather than a silent
papering-over.

## Consequences

- The outline is the first stage where the code makes more decisions than the
  model does. Coverage, the partition repair, and the question budget are all
  arithmetic, which is what makes the exposure and coverage numbers defensible
  on a slide.
- `unassigned` and `topic_cap_exceeded` are two failure surfaces that did not
  exist before and that the interface has to show. They belong in the failures
  section issue #8 already put on the page.
- The bridged-fact candidate rule is a heuristic and will miss pairs whose only
  link is visual and non-adjacent. That is a stated limitation, and the
  alternative is a fabrication risk with no ground truth to catch it.
- The cap binds on every full-length deck, so the ranking decides what the model
  is allowed to see. A pair proposed by one adjacency signal in a deck rich in
  visual edges may never be offered, and nothing downstream can tell that it
  existed beyond the pre-cap count. Raising the cap is the lever if the eval
  shows a real bridge being ranked out.
- The text path now has a second place it visibly loses, on top of figure-only
  fact recovery: it cannot compose slides 55 to 56. Whether that becomes a
  reported number or stays a demonstration is the eval's call, and ADR 0006 has
  already fixed the table.
- A deck with no bridged facts produces a quiz allocated purely proportionally.
  Both cases need exercising before the demo.
