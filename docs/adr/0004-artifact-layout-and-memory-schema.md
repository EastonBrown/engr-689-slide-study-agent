# ADR 0004: The artifact layout and memory schema

- Status: accepted
- Date: 2026-08-19
- Resolves: [Lock the artifact layout and memory schema](https://github.com/EastonBrown/engr-689-slide-study-agent/issues/6)
- Builds on: [ADR 0002](0002-per-slide-note-schema.md), [ADR 0003](0003-cross-deck-topic-taxonomy.md)

## Context

ADR 0002 fixed what one slide read returns and ADR 0003 fixed how topics
accumulate across decks, but neither said where any of it lands. Two different
lifetimes are tangled here, and confusing them is the failure mode: a run
artifact belongs to one deck on one day, while the subject profile outlives
every run that fed it. ADR 0003 already promised that re-running a deck is
idempotent, which is a claim about storage that storage had not yet been asked
to keep.

The constraints are a two-day build window, collaborators on other machines, a
live demo that must survive a bad network, and a rubric that scores the layer
built around the model rather than the model itself. Inspectable intermediate
artifacts are that layer made visible, so writing them is a presentation
decision as much as an engineering one.

## Decision

### Two trees, separate lifetimes

`runs/` holds per-deck run artifacts. `memory/` holds subject-level state.
Nothing in `memory/` is derived by scanning `runs/` at load time, and nothing in
`runs/` is rewritten when memory changes. Both are gitignored.

### A run is a timestamped directory, a deck is a hash

```
runs/<subject-slug>/<deck-slug>/<utc-timestamp>/
  manifest.json
  pages-image/0001.json ... 0066.json
  pages-text/0001.json ... 0066.json
  outline-image.json
  outline-text.json
  research/<sha256-of-query>.json      copies of the cache entries this run used
  review.md
  quiz.json
runs/<subject-slug>/<deck-slug>/latest   file naming the newest timestamp
```

`deck-slug` is slugified from the PDF filename, so `Day3 Principle.pdf` becomes
`day3-principle`. Deck identity for the purpose of replacing a contribution is
the `sha256` of the PDF bytes, recorded in the manifest and never in a path.
Paths are for humans and filenames differ across machines; the hash is for
identity and does not.

A re-run writes a new timestamped directory rather than overwriting the old one.
Idempotency lives in `memory/`, where the contribution is replaced, not on the
run tree, where history is cheap and is occasionally the only evidence of what
went wrong.

### Every stage boundary is written, one file per slide

Page reads are written per slide, not as one array per deck. The page reader
runs concurrently across the deck, so a crash on slide 40 keeps the 39 reads
already paid for, and resume becomes a directory listing rather than
bookkeeping. Outline, research results, review, and quiz are each written at
their boundary.

### Both paths share one run directory

The image path and the text path are the two halves of one modality ablation. A
text run with no image twin has no meaning in this project, so they are produced
together under one manifest with one model, one prompt version, and one DPI
setting recorded once. The results table then reads a directory instead of
joining two runs on a deck hash and trusting they were configured alike.

Per-path completion is recorded in the manifest, so re-running only one path
leaves a legibly partial run rather than a silently mismatched pair.

### Only the image path writes to memory

The image path is the system; the text path is a measurement of it. If both
emitted contributions, every topic's exposure would be counted twice and the
profile would be quietly wrong in a way no error surfaces. The text path's
outline output is written to the run directory and read only by the results
table.

This is stated as a rule because symmetry makes it exactly the thing a later
build session gets wrong by accident.

### Flat JSON, no database

The memory model is relational and the volume is not: five decks, at most 12
topics each, a handful of quiz sittings. SQLite would buy query convenience and
cost a migration story this build window cannot fund. JSON files are diffable in
review, greppable during debugging, and readable on camera without a database
browser.

### The profile stores containers and identity; performance is derived

```
memory/subjects.json
memory/<subject-slug>/profile.json
memory/<subject-slug>/contributions/<deck-slug>.json
memory/<subject-slug>/attempts/<attempt-id>.json
```

`profile.json` holds the topic list and each topic's exposure. A contribution
holds one deck's slide citations and its share of exposure, in one file that is
replaced wholesale on a re-run. Attempts are append-only, one file per quiz
sitting, each tagged with the subject, the deck, the run it came from, and the
topics it touched.

Performance is never stored as a number. It is derived by reading the attempts
directory, which keeps the two axes ADR 0003 refused to collapse structurally
separate rather than separate by convention. History is per subject with a deck
tag on each record, so the per-deck view and the per-subject view come from one
store rather than from two that can disagree.

This ADR owns the containers and the identity of an attempt. What lives inside
an attempt file is owned by the quiz schema.

### Subjects come from a registry, not a directory listing

`memory/subjects.json` is the authority: slug, display name, created date. ADR
0003 requires a subject to be chosen rather than typed, and a dropdown needs a
display name, which a directory listing has nowhere to hold. A directory with no
registry entry is an error the app reports rather than a subject it silently
adopts.

### A failed slide still writes a file

A hard failure or a degraded read writes its slide file with `reader_note` set
and the content fields best-effort. A missing file is ambiguous between crashed,
not yet reached, and skipped, and resume logic cannot tell those apart. With
this rule, resume is "retry every slide whose `reader_note` is non-null", and
the failure-case collection the rubric scores twice is a grep rather than a
process someone has to remember to follow.

### One golden run is committed

`examples/golden/` holds one complete run of the Day 3 Principle deck, both
paths, plus the subject memory state it produced. `runs/` and `memory/` remain
gitignored.

This buys three things: collaborators can build the interface against real
artifacts without spending tokens, the presentation has a replay that works with
no network, and the repo itself shows the artifact shape to anyone reading it.
The cost is a standing obligation to regenerate it whenever a schema moves.

### Memory is local and never merged

Each machine keeps its own `memory/` tree. There is no merge, no sync, and no
committed profile. Reconciling divergent profiles across machines is a
distributed-systems problem worth no rubric points; the presentation runs on one
machine, and the committed golden example is the shared reference.

### The research cache is global and committed

`cache/research/<sha256-of-normalized-query>.json`, one file per lookup, holding
the query, the timestamp, and the results. Not scoped to a run or a subject,
because the point is that a concept met as `named_only` in both Day 1 and Day 2
costs one lookup rather than two. Committed, so a fresh clone demos offline.

### Artifacts carry a schema version

One `schema_version` integer at the top of `manifest.json` and of `profile.json`,
and nowhere else. Not per-file, not semver. The loader compares it against the
current constant and refuses with a message naming the regeneration step. The
schemas are two days old and still moving while a golden run sits committed
against them; two days does not fund a migration path, so it funds a loud
failure instead of a silent one.

## Consequences

- Regenerating the golden run becomes a step in every schema change. If that
  step is skipped, the version check fails loudly, which is the intended
  outcome.
- Re-running one path leaves a partial run directory. The manifest records this,
  and the results table has to handle a run where one path is absent.
- Run directories accumulate with no cleanup story. Over a two-day window on
  five decks this is measured in megabytes and is not worth solving.
- Committing the research cache means committing third-party search results into
  a public repo. They are cached snippets carrying their source URLs, and they
  are acknowledged as external resources per the rubric.
- Deriving performance on every read means the profile alone cannot answer "how
  is this learner doing"; the attempts directory has to be present. That is the
  intent, but it does make the profile file less useful in isolation than its
  name suggests.
