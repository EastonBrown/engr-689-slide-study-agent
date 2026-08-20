# ADR 0005: The quiz, answer key, graded attempt, and retake schema

- Status: accepted
- Date: 2026-08-19
- Resolves: [Lock the quiz, answer key, and retake schema](https://github.com/EastonBrown/engr-689-slide-study-agent/issues/7)
- Builds on: [ADR 0002](0002-per-slide-note-schema.md), [ADR 0003](0003-cross-deck-topic-taxonomy.md), [ADR 0004](0004-artifact-layout-and-memory-schema.md)
- Amends: [ADR 0004](0004-artifact-layout-and-memory-schema.md), which gains a `retakes/` directory

## Context

ADR 0003 fixed that a topic carries `performance` as an axis kept separate from
exposure, and explicitly deferred what performance contains. ADR 0004 fixed that
an attempt is one append-only file per sitting and explicitly deferred what is
inside it. Both deferrals land here, along with the quiz itself.

The format target is not invented. The instructors' own Quizzes 1 to 3 are in
the repo, and Quiz 3 covers the same Day 3 deck the eval targets. Reading it
fixes most of the surface: 10 questions, 25 minutes, 1% each, exactly four
options, one correct, no "all of the above" and no "none of the above". Stems
lean scenario-shaped rather than definitional, and distractors sit at the same
level of abstraction as the answer. One thing the quiz shows that the ticket for
this decision got wrong: Quiz 3 Q2 is a numeric question, computing how
self-attention cost scales when resolution doubles at a fixed patch size. A flat
ban on numbers would not match the target.

The constraint behind almost every choice below is that this is a two-day build
with a live demo. A feature that is genuinely good and costs a second
consistency surface loses to one that is adequate and costs an integer.

## Decision

### Ten questions, always

Fixed at 10 regardless of deck length. It matches the instructors' format
exactly, which keeps the concept-overlap metric a like-for-like comparison
rather than one confounded by quiz length. Deck lengths vary from 38 to 66
slides, so a scaling rule would move the number from 10 to at most 15 while
adding a parameter that has to be defended and earns nothing.

### The question object

```
Question
  question_id          str          "<deck-slug>-q<NN>", stable within the quiz
  stem                 str
  options              [str]        exactly 4
  correct_index        int          0..3
  explanation          str          why the correct option is correct
  distractor_rationale [str | null] exactly 4; entry at correct_index is null
  slide_citations      [int]        at least 1, slide numbers in this deck
  topic                str          a topic name from the subject's topic list
  source               Source       prose | visual
```

`source` is the load-bearing addition. It records whether the answer came from a
slide's prose reading or from a `Visual.assertion`, which is the only thing that
turns "the image path can ask questions the text path structurally cannot" into
a countable claim rather than an anecdote. It costs one enum.

`distractor_rationale` earns its place twice. It is what the grader hands back
when a specific wrong option was chosen, and it forces the generator to
construct distractors that are each wrong for a stated reason rather than
filler.

There is no difficulty field. Self-reported difficulty from the model is noise
that would have to be caveated rather than used.

### One quiz per run, from the image path

ADR 0004 already writes `quiz.json` singular inside the run directory while
pages and outline are per-path, so the quiz comes from the image outline only.
That is held rather than promoted to a second ablation surface. The modality
ablation is carried by the slide notes and the four hand-labeled figure-only
facts, which is where it is measurable. A second quiz would double generation
cost and produce two artifacts that nobody has time to hand-score. The count of
questions with `source: visual` gives the interesting half of that comparison at
no cost.

### The style contract

Banned: dates, named authors, paper titles. These test recall of trivia.

Numbers are allowed when the number is the reasoning and banned when the number
is the fact. Quiz 3 Q2 is the allowed shape. "How many layers does X have" is
the banned shape.

Structural rules, read off the instructors' quizzes: exactly four options, one
correct, no "all of the above" and no "none of the above", distractors at the
same level of abstraction as the answer, stems prefer a scenario over a
definition request.

Every question carries at least one slide citation. A question the generator
cannot cite is dropped, not kept. Whether those citations are correct is the
eval protocol's problem, not this schema's.

### The grader is deterministic

The correct answer is an index, so grading is an index comparison. No model
call, no tokens, no failure mode in front of the class. Every piece of feedback
is already in the question object, so the grader is a lookup and a group-by.

It returns, per question, the verdict, the `explanation`, and the
`distractor_rationale` for the option actually chosen rather than all three,
plus a per-topic rollup for the sitting. The rollup is the bridge to memory: a
sitting produces "topic X, 1 of 3" rather than "6 out of 10", and topic-level
numbers are the only thing a retake can steer on.

### The attempt record

```
Attempt
  attempt_id     str            UTC timestamp plus a short random suffix
  subject_slug   str
  deck_slug      str | null     null for a retake
  run_timestamp  str | null     null for a retake
  quiz_sha256    str            the quiz file exactly as asked
  kind           AttemptKind    first_pass | retake
  taken_at       str            UTC
  responses      [Response]

Response
  question_id    str
  topic          str
  chosen_index   int
  correct        bool
```

The chosen index is stored, not just correctness, because it is what lets a
distractor-confusion pattern be shown later and it costs one integer per
question. The full quiz is not embedded: that would duplicate `quiz.json` in a
second place and give two copies that can disagree, which is the failure ADR
0004 works hardest to avoid. The hash lets an attempt prove which quiz it was,
and the text is one dereference away.

Writing back to the profile is exactly this: append one attempt file. Nothing in
`profile.json` changes when a quiz is graded.

### Performance is a pair, and small n is reported as such

Performance for a topic is derived by reading the attempts directory and is the
pair `(correct, seen)`. Never a bare percentage, and never stored.

Lifetime raw counts, no recency weighting. Weighting would mean choosing a decay
constant that cannot be justified from data this project does not have.

A topic with `seen < 3` is reported as "not enough evidence" rather than given a
score. One wrong answer on a topic seen once is noise, and rendering it as 0% is
a lie. This mirrors ADR 0003's rule that exposure and performance are never
collapsed: the honest answer is sometimes that there is no answer yet.

### The retake

A retake is generated against the subject profile, not against one deck, so it
belongs to memory rather than to any run. ADR 0004's layout gains one directory:

```
memory/<subject-slug>/retakes/<retake-id>.json
```

Not a synthetic run directory. A run is one pass over one deck, and inventing a
fake deck slug to reuse the directory shape would corrupt the one identity ADR
0004 keeps cleanest. Not ephemeral either, because the attempt record points at
a quiz by hash and expects to dereference it.

**Target selection.** Ten questions again, to hold the format. Rank topics with
`seen >= 3` by ratio ascending and take the worst three, two questions each.
Fill the remaining four from topics with `seen < 3`, oldest exposure first. If
fewer than three topics qualify as weak, the undertested pool absorbs the
remainder.

Splitting the retake between weak and undertested topics is the version that is
honest about its own uncertainty. Targeting only the worst three would hammer
topics that might be weak by accident, and would leave insufficient-evidence
topics permanently unresolved. This way the profile converges.

If the profile has no attempts at all, the retake refuses rather than
improvising. A tool that declines when it lacks grounds is a better
demonstration than one that guesses.

**Fresh questions, from notes already on disk.** A retake never reuses a
question verbatim. Reuse tests whether the specific item is remembered, which is
the failure mode a study tool should avoid, and it is trivially gamed on the
second sitting.

The mechanism: resolve each target topic to its `slide_citations` in the
profile, load those specific `pages-image/NNNN.json` notes from the `latest` run
of each contributing deck, and generate from those notes alone. No page is read
again, because the notes are already written. Retake questions carry the same
`source` marker and cite real slides in whatever deck they came from.

This is the one place the memory layer visibly does work rather than merely
accumulating, and it is worth saying out loud during the demo.

### Not decided here

There is no question bank. A per-subject store of every question ever generated
would need dedup across decks and a staleness rule when a deck is re-run, which
is a second memory tree to keep consistent in service of a feature that will be
demoed twice. A quiz-scoped `question_id` plus `quiz_sha256` on the attempt
answers "was this seen before" for any quiz still on disk, which is all of them.
If the bank is wanted later it is a separate ticket, not a smuggled addition.

## Consequences

- ADR 0004's layout is amended. `memory/<subject-slug>/retakes/` is new, and
  `CONTEXT.md` carries the amended tree.
- The retake reads `pages-image` notes from other decks' run directories, so it
  is the first thing that makes `memory/` depend on `runs/` being present. If a
  contributing deck's run directory is deleted, retake generation for its topics
  fails. This is accepted; both trees are local and neither is cleaned up inside
  the build window.
- `Attempt.deck_slug` and `run_timestamp` being nullable means every consumer
  has to handle the retake case. That is the price of retakes not belonging to a
  deck, and it is preferable to a fake deck slug.
- Performance being a pair rather than a number means the interface cannot show
  a single mastery score. That is intended, and the "not enough evidence" state
  is a limitation worth putting on a slide rather than one worth hiding.
- Deterministic grading means the grader cannot give free-form feedback on why a
  learner's reasoning went wrong. It can only replay text written at generation
  time. For multiple choice this is sufficient and it removes a live model call
  from the demo path.
- Ten fixed questions over a 66-slide deck covers a small fraction of the
  material. The quiz is a demonstration of the pipeline, not a study product,
  which is already stated as out of scope on the map.
