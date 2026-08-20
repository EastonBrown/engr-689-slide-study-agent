# ADR 0003: The cross-deck topic taxonomy

- Status: accepted
- Date: 2026-08-19
- Resolves: [Decide the topic taxonomy for cross-deck memory](https://github.com/EastonBrown/engr-689-slide-study-agent/issues/5)
- Builds on: [ADR 0002](0002-per-slide-note-schema.md)

## Context

Memory is subject-namespaced: a topic mastery profile accumulates across every
deck in a subject. That only works if the same idea, met in two different decks,
lands on the same topic. ADR 0002 deliberately left this open, since
`Concept.name` is free text emitted by a page reader that sees one slide and no
neighbours. If those strings reach the profile unmediated, Day 1 contributes
"attention mechanisms", Day 2 contributes "self-attention", and nothing ever
matches. The profile then looks alive while doing nothing, which is worse than
having no memory feature at all.

The course material sets the test. Five decks in one subject, with Days 1 and 2
taught as a continuous thread and Day 3 restarting from computer vision. A
taxonomy that cannot match anything across Days 1 and 2 is broken; one that
matches heavily between Day 2 and Day 3 is probably lying.

## Decision

### The vocabulary is accumulated, never authored

A subject starts with an empty topic list. Every deck run may add to it. No
topic list is written by hand before a deck is processed, and none is seeded.

Hand-authoring the list would mean hand-authoring the thing the pipeline is
supposed to produce, and the empty-profile case would never be exercised.

### The outline stage assigns topics, not the page reader

The page reader keeps emitting free-text `Concept.name` per slide, unchanged.
Mapping concepts onto subject topics is a deck-level step owned by the outline
stage, which sees every slide note at once and the subject's current topic list.

Per-slide concept names are the worst possible input for a vocabulary that has
to be stable across decks, because each one is produced blind to the other 65
slides.

### Matching is model-in-the-loop reuse, not similarity

The subject's current topic list goes into the outline prompt. For each topic
the deck covers, the outline stage must either return an existing topic name
verbatim or declare a new topic with a one-line `created_reason`.

Embedding similarity with a threshold was the obvious alternative and was
rejected: it adds a dependency and a number tuned by feel inside a two-day
window, and it produces a match with no human-readable justification. String
normalization was rejected because it does not address the failure at all, since
"attention mechanisms" and "self-attention" normalize to two different strings
and always will.

### Topics are capped at 12 per deck

Uncapped, one-per-concept topics would make the topic list a second copy of the
concept list, 30 to 60 entries per deck, and any two decks would overlap
somewhere by accident. The cap forces chapter-level topics, which is the only
granularity at which "mastery" means anything to a person reading the profile.

### Two axes, never collapsed

A topic carries `exposure` and `performance` as separate fields. They are never
averaged into a single mastery score. Exposure alone is not mastery, and
performance alone leaves the profile empty until someone takes a quiz.

### A deck's contribution is replaceable

The profile stores each deck's contribution separately and derives totals.
Re-running a deck replaces its prior contribution rather than appending, so a
re-run is idempotent. Model-in-the-loop matching is non-deterministic and decks
will be re-run repeatedly during the build, so an append-only profile would
inflate every time it was tested.

### Near-duplicates are surfaced, never auto-merged

The reuse-or-new decision is the only matching mechanism. When the list
accumulates near-duplicates anyway, the profile view flags them as candidates
for a human to resolve. Automatic merging stacks a second threshold problem on
the first and can silently collapse two genuinely distinct topics, which is
unrecoverable once their counts are combined.

### The subject is chosen, not typed

Upload offers a dropdown of subjects already on disk plus an explicit new
subject field. A bare free-text field would produce "ENGR 689" and "engr689" as
two profiles, which is the same silent-no-op failure one level up.

### The empty profile is the ordinary path

The first deck into a subject matches nothing, and that is reported plainly
rather than special-cased. Every run reports counts of the form "N topics, M
matched, K new". The first run reads "12 topics, 0 matched, 12 new"; the second
run is where the number becomes evidence.

## Consequences

- Matching is non-deterministic. The same deck processed twice can produce
  different matches. This is a named limitation, not a defect, and idempotent
  per-deck contributions keep it from corrupting the profile.
- The demo has a shape: Day 1 then Day 2 shows matching across a continuous
  thread, and Day 3 should match very little because it restarts from computer
  vision. The low number is the honest result and gets shown.
- Near-duplicate topics will appear. Whether the human merge action is
  implemented or the candidate list is display-only is a build-time call.
- The outline stage grows again. It already owns grouping, coverage, and
  cross-slide fact assembly; it now also owns topic assignment against the
  subject list.
- What `performance` contains is not decided here. This ADR fixes that it is a
  separate axis keyed by topic; attempts and retakes belong to the quiz schema.
- Where the profile is written on disk is not decided here. It belongs to the
  artifact layout.
