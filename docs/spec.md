# Build spec

The buildable form of the decisions on record. This is the document a build
session reads to implement a stage without reopening a decision.

## How to read this

Authority runs in one direction. The ADRs under `docs/adr/` decide; `CONTEXT.md`
holds the vocabulary and the locked data shapes; this file assembles both into
stage contracts and adds the implementation-level choices nobody had to make
until code was about to be written.

Three kinds of statement appear below, and they are labeled:

- **Locked.** Decided in an ADR. Changing it means a new ADR.
- **Spec-level.** Decided here, because writing code forced the choice and no
  ADR covers it. Cheap to change; change it here.
- **Open.** Genuinely undecided. Listed at the end rather than papered over.

## Amendments to the locked layout

Five things in the locked layout and the decisions around it do not survive
contact with later decisions. Each is recorded here and applied to `CONTEXT.md`.

1. **`review.md` becomes `review-image.md` and `review-text.md`.** The interface
   decision (issue #8) puts the two generated reviews side by side in the
   comparison section, so both paths write a review. One file cannot hold two.
   The naming now matches `outline-image.json` and `outline-text.json`.
2. **The text path runs the review writer, and nothing after it.** ADR 0005
   already gives the text path no quiz. It also gets no contribution to memory,
   per ADR 0004. Its pipeline ends at the review.
3. **`VisualKind` gains `table` and `photo`.** The enum was drawn from five
   decks in one subject. A table of values and a photograph that is not
   decorative both occur in most disciplines and currently have to be
   misfiled as `chart` or `comparison`. Nothing is built yet, so this costs a
   line in an enum. Amends ADR 0002.
4. **ADR 0007's partition covers non-superseded slides.** Coverage is still
   `page_role == content` computed in code. A slide that is an earlier frame of
   an animation build-up is additionally excluded, by a code-side check
   described under "Any deck, not just the course decks". Amends ADR 0007.
5. **The page-geometry clamp is 2576 px, not 1568.** Earlier drafts of this
   file named 1568. That is the *standard* image tier, and ADR 0001 chose
   `claude-opus-5` for the high-resolution tier at 2576 px long edge
   precisely to avoid reading slides at half resolution. The course decks
   render at 2000x1125, so a 1568 clamp would downscale every page of every
   deck the sentence beside it promises renders exactly as before. The clamp
   sits at the high-resolution tier limit instead. ADR 0001's separate 2000 px
   figure applies only to requests carrying more than 20 images, which the
   one-image-per-request design never makes. Spec-level; no ADR changes.

## Environment

- **Python 3.14.2.** The interface prototype was built and probed on it (#8).
- **Dependencies** (spec-level):

  | Package | Role |
  | --- | --- |
  | `anthropic` | the only model client, per ADR 0001 |
  | `pydantic` | strict validation of every schema in `CONTEXT.md` |
  | `streamlit` | the interface, per #8 |
  | `pypdfium2` | PDF page rendering and text extraction |
  | `pillow` | `pypdfium2.to_pil()`, which is how a page becomes a PNG |

  Development only, not imported by the pipeline:

  | Package | Role |
  | --- | --- |
  | `pytest` | the test suite, configured in `pytest.ini` |
  | `mypy` | typechecking, configured in `mypy.ini` |

  Both lists are pinned in `requirements.txt` and `requirements-dev.txt`.
  Pinned rather than floored, because a transitive release breaking the run on
  Friday morning costs more than staying current is worth. Direct dependencies
  only; neither file is a lockfile.

  `pypdfium2` is spec-level and does both jobs with no external binary and a
  permissive license. PyMuPDF is the fallback if extraction quality
  disappoints; it needs an AGPL note in the acknowledgements if adopted. Avoid
  `pdf2image`, which requires a poppler install and breaks the
  no-single-machine-assumptions rule.

- **`ANTHROPIC_API_KEY`** in the environment or a gitignored `.env`. Locked by
  ADR 0001. Never committed; collaborators supply their own.
- **No hardcoded absolute paths.** Everything resolves from the repo root.

## Code layout

Spec-level, all of it.

```
app.py                        Streamlit entrypoint, variant A
src/study_agent/
  config.py                   model id, effort per stage, DPI, caps,
                              PROMPT_VERSION, concurrency
  schemas.py                  every Pydantic model in CONTEXT.md
  paths.py                    run and memory paths, slugs, the latest pointer
  render.py                   PDF to page images and to extracted text
  llm.py                      Anthropic wrapper: structured call, retries,
                              token and cost accounting
  prompts/                    one module per stage, versioned together
  stages/
    page_reader.py
    outline.py
    research.py
    review.py
    quiz.py
    grade.py
  memory.py                   subjects registry, profile, contributions,
                              attempts, retakes
  pipeline.py                 orchestrates one run, writes the manifest
  replay.py                   reads a completed run from disk, no API calls
eval/score_spans.py           the verbatim_spans substring check
```

**Entrypoints** (spec-level):

- `streamlit run app.py` for the interface and the demo.
- `python -m study_agent.pipeline <deck.pdf> --subject <slug>` for a headless
  run, so a run can be produced without driving the UI on camera.
- `python eval/score_spans.py <run-dir>` for the scripted citation check.
- `python -m pytest` and `python -m mypy` for the test suite and the
  typechecker. `src/` is checked strictly; `tests/` is exempted from the
  annotation requirements, since a test full of deliberately malformed fixture
  dicts gains nothing from them. `mypy.ini` names each strictness flag on its
  own line rather than setting `strict`, so relaxing one later is a visible
  edit rather than a dropped flag.

**Prompt versioning.** `PROMPT_VERSION` is one string in `config.py` covering
all prompts, written into `manifest.json`. Bumping it is a manual act. Locked
insofar as ADR 0004 requires the field; the single-string form is spec-level.

## Model calls

Locked by ADR 0001. One provider, one model, `claude-opus-5`, everywhere.
Adaptive thinking everywhere.

| Stage | Calls per run | Effort | Tools |
| --- | --- | --- | --- |
| Page reader | one per slide per path | `low` | none |
| Outline call A, grouping | one per path | `high` | none |
| Outline call B, bridges | one per path | `high` | none |
| Outline repair | at most one per path | `high` | none |
| Research | one per lookup, capped | default | `web_search_20260209` |
| Review writer | one per path | `high` | none |
| Quiz generator | one, image path only | `high` | none |
| Grader | zero | n/a | n/a |
| Question budget | zero | n/a | n/a |

Two stages make no model call at all, and that is the point of them. Coverage,
the partition, the question budget, and grading are arithmetic.

**Retries** (spec-level): two attempts on a transport error or a schema
violation, then the stage's own failure channel. For the page reader that is
`reader_note`; for the outline it is ADR 0007's degrade path; for the review and
quiz it is a failed run.

**Cost accounting** (locked by ADR 0004): token and cost totals per stage go in
`manifest.json`. `llm.py` returns usage with every call and the pipeline
accumulates it.

## Any deck, not just the course decks

Every decision on record was made against five course decks that are
text-native, uniformly 960x540, and free of animation build-up pages. A deck
from another class satisfies none of that by default. This whole section is
spec-level, and it exists so that a chemistry or history deck produces a
defensible run rather than a confident wrong one.

The governing rule: **the pipeline never refuses a deck for being unlike the
course decks, and it never reports a number the deck cannot support.** Where a
measurement does not apply, it says so instead of printing a zero.

### Preflight

Runs before the render stage, writes its findings to `manifest.json` under
`preflight`, and the run summary shows them. It decides what a run is allowed to
claim, not whether it happens.

| Check | Rule | Effect |
| --- | --- | --- |
| Readable | the PDF opens and is not encrypted | the one hard stop; refuse with a message |
| Text-native | fraction of pages whose extracted text is at least 40 characters | below 0.5 the deck is marked image-only |
| Page geometry | pixel dimensions at 150 DPI | downscale so the long edge is at most 2576 px |
| Build-up frames | consecutive-page containment, below | a `superseded` list of slide numbers |
| Length | covered slide count | over roughly 120, expect `topic_cap_exceeded` |

**Image-only decks.** The text path still runs and still writes its artifacts,
because a missing stage is worse than an empty one. But the comparison section
and the results table label it "text path not applicable, this deck is
image-only" rather than reporting it as a score of zero. A baseline that had
nothing to read did not lose the comparison, it never entered it.

**Page geometry.** ADR 0001 pins the render at 150 DPI and treats it as a
decision with a price attached. That price was measured on 960x540 pages. A deck
with larger pages at the same DPI produces larger images and a different cost
per page, so the long edge is clamped to 2576 px after rendering. Below that
nothing changes, which means the course decks render exactly as before.

### Build-up frames

A slide deck exported from presentation software often contains the same slide
several times, each with more content revealed. `CONTEXT.md` records that the
course decks contain none, which is why slide numbers equal PDF page numbers.
Another class's deck will contain them, and the damage is entirely silent:
exposure inflates on whichever topic animated the most, the question budget's
proportional allocation follows that inflation, citations land on a partial
build of a slide, and ADR 0007's "adjacent slide with a null or repeated title"
candidate signal fires on every animation pair and floods the candidate cap
before a real cross-slide fact is ever proposed.

**Detection** runs at render time, from extracted text only, with no model call.
Page N is a build-up frame superseded by page N+1 when all of the following
hold:

- both pages carry at least 20 characters of extracted text,
- the set of normalized non-empty lines on page N is a subset of that set on
  page N+1,
- page N+1 has strictly more such lines.

Chains apply transitively across consecutive pages, and the last frame of a
chain is the survivor. The rule is deliberately conservative: a false negative
leaves some inflation, a false positive silently deletes a real slide, and
subset-plus-strictly-more only fires on a genuine build. Detection is off for
image-only decks, which is recorded rather than assumed, and there is a config
flag to disable it outright.

**What a superseded frame is excluded from:** topic assignment, exposure, the
question budget, and bridged-fact candidate proposal. A citation that resolves
to a superseded frame is rewritten in code to its survivor.

**What it is not excluded from:** it is still rendered, still read, and still
writes its `SlideNote`. Slide numbers must keep equaling PDF page numbers, and
the interface should be able to show a dropped frame rather than have it vanish.

The count is reported in the manifest and in the run summary, so a deck with 40
build-up frames says so out loud.

### Scale

- The cap of 12 topics per deck is unchanged. A long deck sets
  `topic_cap_exceeded`, keeps every topic per ADR 0007, and says so in the run
  summary.
- Ten questions regardless of deck length is ADR 0005 and does not change. On a
  200-slide deck that is thin coverage, so the quiz header states the covered
  slide count it was drawn from rather than leaving the reader to assume
  proportional coverage.
- The research cap of 15 lookups applies per path per deck, unchanged.

### Decks with no eval labels

Figure-only fact recovery is defined only for a deck that has hand-labeled
facts. `eval/figure-only-facts.json` becomes keyed by deck slug rather than
holding one flat list, and any deck without an entry reports the metric as **not
labeled for this deck**.

This is a correctness requirement on the interface, not a nicety. The comparison
scoreboard in issue #8 is stated with the Day 3 numbers in it, 3/4 against 0/4,
112 visuals against 0, 66 slides read against 65. Two of those three are
computable from any run and must be computed from the run. The third is
label-dependent and must render as "not labeled" when the labels are absent. No
number on that screen is a literal.

### Naming

- A new subject is created through an explicit control, never inferred from a
  typed string. Locked by ADR 0003, and it is the whole intake path for another
  class.
- The deck slug is the slugified filename. If that slug already exists in the
  subject under a different sha256, the first eight characters of the sha256 are
  appended. Otherwise two different PDFs that slugify alike would share a run
  directory and overwrite each other's contribution.

### What still degrades, honestly

- `VisualKind` collapses domain-specific figures. Even with `table` and `photo`
  added, a reaction mechanism, a structural formula, and a spectrum all land in
  `diagram` or `chart`. The content survives in `Visual.assertion`; the typed
  layer loses resolution. Named in the limitations section rather than fixed.
- ADR 0005 bans a number that is the fact and allows a number that is the
  reasoning. In a quantitative subject that rule prunes more candidate
  questions, so a short quiz is more likely. The spec already ships short rather
  than padding.
- The research step is a general web search. Its quality on a niche topic is
  whatever the search returns, and every answer carries its citation so a reader
  can judge it.

## The run

One run processes one deck and produces both paths under one manifest. Stage
order, with every boundary written to disk before the next stage reads it:

```
render -> page reader (image) -> outline (image) -> research (image) -> review (image) -> quiz -> grade -> memory
       -> page reader (text)  -> outline (text)  -> research (text)  -> review (text)   [ends]
```

The two paths are independent after render and rejoin only in the comparison
section of the interface and in the results table.

### 1. Render

**Locked:** 150 DPI page images, ADR 0001. Slide numbers are 1-based and equal
PDF page numbers, `CONTEXT.md`.

**In:** a PDF path. **Out:** for each page, a rendered PNG and the page's
extracted text.

Both are produced in one pass so the image path and the text path see the same
page numbering by construction. The extracted text is also what
`eval/score_spans.py` checks `verbatim_spans` against, so it is written to disk
even though the image path never receives it.

**Spec-level:** line endings are normalized to `\n` at extraction and the text
is written and read back without newline translation, so what is on disk is what
pdfium produced. This is a correctness requirement of the span check rather than
a formatting preference: untranslated CRLF grew a second CR on write, and every
verbatim span crossing a line break then scored as a fabrication.

**Spec-level:** rendered pages are written under the run directory as
`pages-render/NNNN.png` and extracted text as `pages-render/NNNN.txt`. ADR 0004
did not list them. The interface needs page images beside reviews and failures
long after the run, and re-rendering on every Streamlit rerun is waste.

**Also spec-level, and it belongs to this stage because it needs the extracted
text and nothing else:** preflight and build-up frame detection, both described
under "Any deck, not just the course decks". Render writes `preflight` into the
manifest, clamps the long edge to 2576 px, and emits the `superseded` slide
list that the outline stage consumes. No model call is involved in any of it.

### 2. Page reader

**Locked:** ADR 0002. One `SlideNote` per slide per path, strict JSON. The image
path never receives extracted text. The reader sees one slide and no neighbours.
`visuals` is the only place figure content is stated in detail. Decorative
images are emitted, never dropped. An empty `concepts` list is valid and is
surfaced rather than suppressed.

**In:** one page image (image path) or one page's extracted text (text path).
**Out:** `pages-image/NNNN.json` or `pages-text/NNNN.json`.

**Concurrency** (spec-level): a bounded pool, default 8 concurrent requests,
configurable in `config.py`. ADR 0001 requires one image per request and
client-side concurrency; it does not fix the width.

**Failure:** a failed or degraded read still writes its file with `reader_note`
set. A missing file never means anything. Resume is "retry every slide whose
`reader_note` is non-null".

### 3. Outline

**Locked:** ADR 0007 in full. Two whole-deck calls plus at most one repair call.
Call A groups and assigns topics over a compacted view of the notes
(`slide_number`, `page_role`, `title`, `concepts`, and each visual's `kind` and
`assertion`, dropping `reading` and `verbatim_spans`). Call B confirms bridged
facts from candidates the code proposed. Coverage is `page_role == content`,
computed in code. Covered slides are partitioned, one topic each. The question
budget is arithmetic. Violations degrade to `unassigned` or `topic_cap_exceeded`
rather than aborting.

**In:** every `SlideNote` for one path, the `superseded` list from render, and
the subject's current topic list from `memory/<subject>/profile.json`.
**Out:** `outline-image.json` or `outline-text.json`.

The candidate proposer is pure code over the notes, using ADR 0007's three
signals: an edge in `Visual.relates_to_slides`, an adjacent slide with a null or
repeated `title`, and adjacent slides sharing a `Concept.name`. Its cap and the
number proposed are both recorded in the outline.

**Superseded frames** (spec-level, amendment 4). A slide on the render stage's
`superseded` list is excluded from the partition, from exposure, from the
question budget, and from candidate proposal, and the compacted view sent to
call A omits it. It is not a `SkippedSlide`, since its `page_role` is genuinely
`content`; the outline carries its own `superseded: [int]` list so the covered
count stays auditable against deck length. On the course decks this list is
always empty and the stage behaves exactly as ADR 0007 specifies.

### 4. Research

**Locked:** ADR 0001 uses the hosted `web_search_20260209` tool with `max_uses`
per request. ADR 0002 makes `Concept.status: named_only` the sole trigger,
capped at 15 lookups per deck. ADR 0004 puts the cache at
`cache/research/<sha256-of-normalized-query>.json`, global and committed, with
the entries a run used copied into `runs/.../research/`.

**In:** the `named_only` concepts from one path's notes. **Out:** cache entries,
plus copies under the run.

**Spec-level, the parts ADR 0004 left as "query, timestamp, results":**

```
CacheEntry
  query             str    as asked
  normalized_query  str    the key's preimage
  asked_at          str    UTC
  model             str
  prompt_version    str
  concept           str    the Concept.name that triggered it
  answer            str    the model's short synthesis
  citations         [{title, url}]
```

**Normalization** (spec-level): lowercase, strip surrounding whitespace,
collapse internal runs of whitespace to one space, strip trailing punctuation.
Nothing cleverer. ADR 0003 already rejected string normalization as a way to
merge near-duplicate topics, and this is a cache key, not a merge.

**Both paths run research** (spec-level), each against its own `named_only`
concepts, sharing the global cache. The cap of 15 applies per path. The text
path is nearly free because it mostly hits cache, and the difference in what
each path thought was worth looking up is itself visible in the artifacts.
Suppressing research on the text path would confound the comparison with a
missing stage.

**A cache hit makes no API call**, which is what makes offline replay possible.

### 5. Review writer

**Locked:** slide-number provenance on every claim, from the project brief.
Effort `high`, ADR 0001. Degraded slides are marked, ADR 0007.

**In:** one path's outline, its slide notes, and the research entries that path
used. **Out:** `review-image.md` or `review-text.md`.

**Spec-level, since no ADR shapes the review:**

- Markdown, one section per outline topic, in outline order.
- Every claim carries a slide citation as `[slide N]` or `[slides N, M]`.
- Only covered slides may be cited. Degraded slides may be cited with the
  degradation noted inline; only the quiz is forbidden from citing them.
- Bridged facts get their own short section, since they are the thing the text
  path structurally cannot produce.
- Research-derived explanation is marked as such and carries its citation, so a
  reader can tell what came from the deck and what came from a lookup.
- No front matter. The interface renders it with `st.markdown`.

### 6. Quiz generator

**Locked:** ADR 0005 in full. Ten four-option questions always. Image path only.
`source: prose | visual`. Dates, named authors, paper titles, "all of the above"
and "none of the above" are banned; numbers are allowed when the number is the
reasoning and banned when the number is the fact. A question that cannot cite a
slide is dropped rather than kept. Degraded slides are never cited, ADR 0007.
The topic split is the outline's arithmetic budget, and the reserved
bridged-fact question is the one the text path provably could not have written.

**In:** the image outline, its notes, the question budget. **Out:** `quiz.json`.

A dropped question leaves the quiz short. **Spec-level:** regenerate once for
the shortfall, then ship short and record the count in the manifest. Ten is the
target, not a loop condition.

### 7. Grader

**Locked:** ADR 0005. Deterministic index comparison, no model call. Returns the
verdict, the explanation, the rationale for the option actually chosen, and a
per-topic rollup. Writes nothing to `profile.json`; appends one attempt file.

**In:** a quiz and the chosen indices. **Out:** one file under
`memory/<subject>/attempts/`.

### 8. Memory

**Locked:** ADR 0003 and ADR 0004. Only the image path writes a contribution.
Deck identity for replacement is the PDF's sha256, so a re-run is idempotent in
`memory/` while still writing a new run directory. `memory/subjects.json` is the
authority on which subjects exist; a directory with no registry entry is an
error. Performance is derived from attempts, never stored, and reports
insufficient evidence below three sightings. `schema_version` mismatch is a
refusal to load, not a migration. Memory is local and never committed.

**Retake:** ADR 0005. Three weakest topics with `seen >= 3` at two questions
each, then four from topics with `seen < 3`, oldest exposure first. Refuses with
no attempts on record. Generates from `pages-image` notes in each contributing
deck's `latest` run, so it needs those directories to still exist and costs no
page reads.

## The interface

**Locked** by issue #8. Streamlit, variant A, one scrolling page, no tabs and no
routing, filmable in a single take. Screen order top to bottom:

1. Subject dropdown, never a typed string, and PDF upload.
2. Seven `st.status` stage boxes that open, log live, and collapse to a summary.
3. Run summary: slides read, topics matched and new, lookups and cache hits,
   cost.
4. Failures and degraded reads, each beside its page image.
5. The lesson review, with a cited slide pulling up its page image and the
   `SlideNote` that produced it.
6. Image path against text path: the three-metric scoreboard with slide 10
   reported as partial on both sides, and the two reviews side by side.
7. Quiz, then grade, then retake.

**No number on any of those screens is a literal** (spec-level). Slides read and
visuals found come from the run. Figure-only fact recovery comes from
`eval/figure-only-facts.json` keyed by deck slug, and renders as "not labeled
for this deck" when there is no entry. An image-only deck renders the text
column as "not applicable" rather than as zero. The Day 3 numbers in issue #8
are what this screen shows for the Day 3 deck, not what it shows.

**The constraint that follows:** Streamlit reruns the whole script on every
interaction, so no run state lives in memory. Every screen reads its stage from
disk. This is why ADR 0004's write-every-boundary rule is load-bearing rather
than convenient.

**Replay mode** (spec-level, required by the demo plan in #11): a run directory
can be pointed at and rendered with zero API calls. `replay.py` reads the
manifest and replays each stage box from the files already written, at a fixed
delay per line so the animation still reads on camera. The committed
`examples/golden/` run is what the demo replays.

## Eval

**Locked** by ADR 0006. `eval/figure-only-facts.json` holds the labels,
`eval/results.md` holds the table already written out empty, and
`eval/score_spans.py` is the one scripted check: every `verbatim_spans` entry
tested as an exact substring of that page's extracted text, image path only, no
model call. Figure-only recovery and quiz citation accuracy are scored by hand.

**Spec-level:** a page whose extracted text is empty or missing is reported as
*unscoreable* rather than counted as a failure, and does not change the exit
code. The check can only ever establish that a span is absent from the text, so
a page with no text is a gap in the evidence and not a fabrication by the
reader. Empty is the case that occurs: render writes a `.txt` for every page,
including the image-only ones pdfium extracts nothing from.

**Spec-level:** `eval/figure-only-facts.json` is keyed by deck slug, so the four
Day 3 labels sit under `day3-principle` and another deck can be labeled later
without disturbing them. Everything the results table reports is about a labeled
deck; a run over an unlabeled deck produces artifacts and a review, not a row in
that table. `eval/score_spans.py` is the exception and works on any run, since
it needs only notes and extracted text.

The abort rule stands: if the full Day 3 image-path run is not producing
`pages-image` notes by Thursday noon, read only the five labeled slides on both
paths.

## Build order

Spec-level, and it is the order that keeps the abort rule reachable.

1. `config.py`, `schemas.py`, `paths.py`, `render.py`, `llm.py`. Preflight and
   build-up detection live in `render.py` and are pure text comparison, so they
   cost minutes and are worth doing here rather than retrofitting.
2. Page reader, both paths, over Day 3 slides 55 to 61. This is the seven-slide
   window the demo plan films live and it holds two of the three strong
   figure-only facts.
3. `eval/score_spans.py`, which needs nothing but notes and extracted text.
4. Outline, then review writer. Both paths now produce something end to end.
5. Quiz, grader, memory.
6. The interface over whatever exists, reading from disk.
7. The full 66-slide run, committed as `examples/golden/`.

Steps 1 and 2 satisfy ADR 0006's abort rule on their own. Everything after that
is upside.

## Open

Named rather than assumed.

- **`Concept.name` normalization across decks and subjects.** Flagged unresolved
  in ADR 0002 and still unresolved. It does not block a build: concepts are not
  the memory vocabulary, topics are.
- **What the README becomes.** Still fog on the map, still waiting on what ships.
- **Whether a second deck is processed.** The demo plan makes `Day1 Tool.pdf` on
  the image path a nice-to-have and the first thing cut.
- **Whether the build-up detection thresholds hold on a real animated deck.**
  They are chosen conservatively and have never been run against one, because
  the course decks contain no build-up frames to test on. The first outside deck
  is the test, and the `superseded` count in the run summary is how it is
  checked: a plausible count on a visibly animated deck, and zero on the course
  decks.
