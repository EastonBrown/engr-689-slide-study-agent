# ADR 0006: The eval protocol and the results table

- Status: accepted
- Date: 2026-08-19
- Resolves: [Lock the eval protocol and the results table](https://github.com/EastonBrown/engr-689-slide-study-agent/issues/9)
- Builds on: [ADR 0002](0002-per-slide-note-schema.md), [ADR 0004](0004-artifact-layout-and-memory-schema.md), [ADR 0005](0005-quiz-answer-key-and-retake-schema.md)

## Context

The charting session left this as "concept overlap against the instructors' real
quizzes, plus citation accuracy". Both of those score the image path against
itself. Neither produces a number in which the text path appears, which would
leave the text baseline built, run, paid for, and then absent from the results
slide, and would leave the project's central claim unmeasured.

Figure-only fact recovery is the one metric where the two paths produce
different numbers, and it is the cheapest of the three, because the labeling is
already done: four facts in the Day 3 deck are hand-labeled in
`data/course/README.md`, with what text extraction returns for each recorded
alongside.

The constraint is a Thursday deadline inside a two-day build, with the scoring
done by one person by hand.

## Decision

### Two metrics, not three

Figure-only fact recovery is the primary metric. Citation accuracy is secondary.
Concept overlap against Quiz 3 is dropped, not deferred.

Concept overlap sounds like the rigorous one and is the only metric of the three
with no defensible hit rule at a sample of one quiz. Deciding when a generated
question and an instructor question cover "the same concept" is a judgment call
with no ground truth, and "if time allows" is how a metric ends up half-scored
the night before. It is dropped explicitly and named as a limitation in the
presentation rather than left as a gap.

### What a recovery hit is

For each labeled fact and each path, read that slide's `SlideNote` from the run
and judge whether the fact is present. A hit is the fact appearing **anywhere in
the note**, in any field. The field it landed in is recorded as a second column,
because a fact recovered in `visuals[].assertion` is a stronger result than the
same fact recovered only in `reading`, and the difference is worth showing
without letting it move the headline number.

The loose rule is deliberate. At a sample this small a strict rule turns one
judgment call into a 25 percent swing. The rule is fixed here, before the run,
so it cannot be tuned after the results are seen.

Scored by hand by one person. Four facts times two paths is eight judgments,
which is well under an hour.

### The headline is n=3, and slide 10 is reported on its own line

Facts 1 to 3 (slides 61, 28 with its repeat at 48, and 55 to 56) form the
headline denominator. Fact 4 (slide 10, the pinhole-camera geometry) is reported
as a separate, named known-weak case that both paths handle poorly.

Slide 10's labels do extract, so under the "anywhere in the note" rule the text
path will plausibly appear to recover it while missing the spatial relation that
is the entire content of the slide. Counting it in the headline flatters the
baseline and understates the system on the strength of a case already recorded
as weak. Splitting it out is the harder-on-ourselves reading, and it matches the
interface decision in issue 8, where the on-camera scoreboard is 3/4 against 0/4
with slide 10 called out separately. The results slide and the demo screen then
tell the same story.

### Citation accuracy is two checks, both image path only

1. **Quiz citations, by hand.** For each of the ten questions in the generated
   quiz, judge whether the cited slides support the stem. Ten judgments.
2. **`verbatim_spans` exact match, scripted.** For every slide in the run, check
   each `verbatim_spans` entry as an exact substring of that page's extracted
   text. No model call, no human.

The text path is not scored on either. ADR 0002 already records that
`verbatim_spans` is degenerate by construction on the text path, since its spans
are copied from the text it was given, and ADR 0005 records that the text path
generates no quiz. So this is reported as an image-path hallucination check, not
as a comparison. Labelling it otherwise would be dishonest.

### One run for the table, plus a repeatability probe

The table is filled from the single committed golden run, stated as single-run.
Alongside it, the page reader is re-run five times on each of the five labeled
slides (61, 28, 55, 56, 10) on the image path only, and the per-fact hit count
out of five is reported.

That is 25 page reads, which is a rounding error against a 66-slide deck, and it
directly answers the first question anyone asks about a non-deterministic
pipeline. It also makes the golden run defensible as the committed artifact
rather than a cherry-pick. Three full runs of the deck would triple the cost to
answer the same question less cheaply.

### The results table, written out empty

Filled in on Thursday as data entry, not design.

```
Figure-only fact recovery, Day 3 deck (single run)

| Fact                                  | Slide(s) | Image | Text | Field       |
| Russell and Norvig sensors/actuators  | 61       |       |      |             |
| CLIP dominance in the bar chart       | 28, 48   |       |      |             |
| Generation composes, retrieval cannot | 55-56    |       |      |             |
| Total                                 |          |   /3  |  /3  |             |
| Pinhole geometry (known-weak case)    | 10       |       |      |             |

Repeatability, image path, 5 re-reads per labeled slide:
  slide 61 __/5   slide 28 __/5   slides 55-56 __/5   slide 10 __/5

Citation accuracy, image path only:
  quiz slide_citations supported by the cited slide: __/10
  verbatim_spans found verbatim in that page's extracted text: __/__
```

One table carries the claim and two lines carry the caveats.

### The eval lives in a committed `eval/` directory

```
eval/figure-only-facts.json   the four labeled facts, machine readable
eval/results.md               the table above, filled in
eval/score_spans.py           the verbatim_spans checker
```

The labels currently exist only as a Markdown table in `data/course/README.md`,
which a script cannot read and a hand-scorer will retype. They move into JSON,
with the README table left in place as the human-readable account of why each
fact was chosen.

Explicitly not inside the run directory. ADR 0004 makes a run an artifact the
pipeline produced, and hand-entered scores are not that. `runs/` is also
gitignored, so an eval living there would delete the results table on the next
machine.

### The abort rule

If the full Day 3 image-path run is not producing `pages-image` notes by
**Thursday 2026-08-20 noon**, drop citation accuracy and the repeatability probe
and score figure-only recovery by running the page reader over only the five
labeled slides, both paths. That is ten page reads and costs minutes.

The rule is written down now, while it is cheap to decide, so the call is not
made under pressure at 11pm. The four labeled facts are the entire claim, and
reading five slides is not a pipeline, so the headline number survives even a
bad Thursday.

## Consequences

- The text path now has exactly one job in the results: the Image and Text
  columns of the recovery table. That is a narrower role than "the baseline"
  suggested, and it is the honest one.
- The headline number is n=3. It will be challenged in the room as a small
  sample, and the answer is that it is small, hand-labeled, and stated as such,
  with the repeatability probe standing in for the variance question.
- Dropping concept overlap means the instructors' quizzes are no longer used as
  ground truth for anything. They remain the format target for ADR 0005 and are
  still acknowledged as course material.
- `eval/score_spans.py` is the one piece of production code this map's decisions
  call for. It is a substring check over JSON files, with no model call.
