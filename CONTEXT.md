# Domain context

The slide-deck-to-study-guide agent for ENGR 689. This file holds the shared
vocabulary and the locked data contracts. Decisions and their reasoning live in
`docs/adr/`; this file states what the terms mean and what the shapes are.

## Glossary

**Deck.** One PDF lecture slide deck. The unit a run operates on.

**Slide.** One page of a deck. Slide numbers are 1-based and equal the PDF page
number, which holds because the course decks contain no animation-duplicate
pages.

**Page reader.** The stage that looks at one slide and returns one slide note.
Runs once per slide, concurrently across the deck.

**Image path.** The system. Slides are rendered to page images at 150 DPI and
the page reader sees the image.

**Text path.** The baseline, and only the baseline. The page reader sees the
slide's extracted text instead of its image. Same schema, same prompt, same
model. It exists so the results table can isolate the input modality.

**Slide note.** What the page reader returns for one slide. The system's
load-bearing interface. See the schema below and ADR 0002.

**Visual.** One figure on a slide: a diagram, chart, equation, comparison,
screenshot, or a decorative image. Carries what the figure asserts, separately
from the prose reading of the page.

**Concept.** Something the slide names, along with whether the slide explains
it. A concept the deck names but does not explain is what the research stage
looks up.

**Figure-only fact.** A fact present in a slide's image that survives poorly or
not at all through text extraction. Four are hand-labeled in the Day 3 deck; see
`data/course/README.md` for why each was chosen and
`eval/figure-only-facts.json` for the machine-readable labels. These are the
ground truth for the headline metric.

**Recovery hit.** The unit of the headline metric: one labeled figure-only fact
appearing anywhere in that slide's slide note, in any field, on one path. Scored
by hand, eight judgments in total. The field it landed in is recorded but does
not change the hit. See ADR 0006.

**Known-weak case.** The fourth figure-only fact, on Day 3 slide 10, whose
labels do extract even though the spatial relation between them does not. It is
reported on its own line and sits outside the headline denominator, which is
therefore three rather than four.

**Repeatability probe.** Five re-reads of each labeled slide on the image path,
reported as hits out of five per fact. It stands in for a variance estimate at
25 page reads rather than at the cost of three full runs.

**Subject.** The namespace for memory. A topic mastery profile accumulates
across every deck in a subject; a different class gets its own profile.

**Topic.** A chapter-level unit of subject matter that mastery accumulates
against. Topics are the memory vocabulary. They are coarser than concepts,
capped at 12 per deck, and drawn from a list the subject accumulates as decks
are processed rather than one authored up front. See ADR 0003.

**Topic assignment.** The outline stage's mapping of a deck's concepts onto the
subject's topic list. For each topic the deck covers it either reuses an
existing topic name verbatim or declares a new one with a reason. The page
reader takes no part in this.

**Topic mastery profile.** The per-subject record of what its topics are and how
they stand. Holds two axes that are never collapsed into one score: exposure and
performance.

**Exposure.** How much of a subject's material touched a topic, measured in
slides. Not mastery, and never reported as mastery.

**Performance.** How a learner did on a topic when quizzed. Keyed by topic and
kept apart from exposure. Derived by reading the attempts directory, never
stored, and always the pair (correct, seen) rather than a percentage. Below
three sightings a topic reports insufficient evidence instead of a score. See
ADR 0005.

**Question.** One multiple-choice item: a stem, exactly four options, one
correct index, and the slides and topic it traces back to. See the schema below.

**Quiz.** Ten questions generated for one deck from the image path, written to
`quiz.json` in the run directory. The text path generates no quiz.

**Retake.** A ten-question quiz generated against a subject profile rather than
a deck, targeting the three weakest topics and the least-tested ones. Questions
are always fresh, built from slide notes already on disk. Lives in `memory/`,
not in a run.

**Deck contribution.** One deck's share of a topic mastery profile, stored
separately so profile totals are derived. Re-running a deck replaces its
contribution, which makes a re-run idempotent.

**Run.** One pass of the pipeline over one deck, producing both paths together.
Identified on disk by a UTC timestamp and identified for the purpose of
replacing a contribution by the deck's content hash.

**Attempt.** One quiz sitting. Append-only, tagged with the subject, deck, run,
and the topics it touched. Performance is derived from attempts and is never
stored as a number.

**Golden run.** The one run committed to the repo, so collaborators and the
demo have real artifacts without spending tokens or needing a network.

**Research cache.** The global, committed store of research lookups, keyed by a
hash of the normalized query. Shared across every run and every subject.

## The on-disk layout

Locked by [ADR 0004](docs/adr/0004-artifact-layout-and-memory-schema.md). Flat
JSON throughout; no database. `runs/` and `memory/` are gitignored,
`examples/golden/`, `cache/research/`, and `eval/` are committed.

```
runs/<subject-slug>/<deck-slug>/<utc-timestamp>/
  manifest.json          schema_version, deck sha256 and slug, subject, UTC
                         start and end, model id, prompt version, DPI,
                         per-path slides attempted and succeeded, count of
                         non-null reader_note, research lookups and cache
                         hits, token and cost totals per stage
  pages-image/NNNN.json  one SlideNote per slide
  pages-text/NNNN.json   one SlideNote per slide
  outline-image.json
  outline-text.json
  research/              copies of the cache entries this run used
  review.md
  quiz.json
runs/<subject-slug>/<deck-slug>/latest    names the newest timestamp

memory/subjects.json                              slug, display name, created
memory/<subject-slug>/profile.json                schema_version, topic list,
                                                  exposure
memory/<subject-slug>/contributions/<deck-slug>.json
memory/<subject-slug>/attempts/<attempt-id>.json
memory/<subject-slug>/retakes/<retake-id>.json    a quiz built from the profile
                                                  rather than from a deck

cache/research/<sha256-of-normalized-query>.json  query, timestamp, results
examples/golden/                                  one committed run plus the
                                                  memory state it produced

eval/figure-only-facts.json                       the four labeled facts and
                                                  the repeatability probe
eval/results.md                                   the results table, filled by
                                                  hand from the golden run
eval/score_spans.py                               verbatim_spans substring check
```

### Rules that travel with the layout

- A run holds both paths under one manifest, so the results table reads one
  directory instead of pairing two runs and trusting they matched.
- Only the image path writes a deck contribution. The text path is a
  measurement, and letting it contribute would double every topic's exposure.
- A failed or degraded slide still writes its file, with `reader_note` set.
  Resume is "retry every slide whose `reader_note` is non-null"; a missing file
  never means anything.
- A re-run writes a new timestamped directory. Idempotency happens in `memory/`,
  by replacing the contribution, never by overwriting a run.
- `memory/subjects.json` is the authority on which subjects exist. A directory
  with no registry entry is an error, not a subject.
- Memory is local to a machine and never merged or committed.
- `schema_version` appears in `manifest.json` and `profile.json` and nowhere
  else. A mismatch is a refusal to load, not a migration.

## The slide note schema

Locked by [ADR 0002](docs/adr/0002-per-slide-note-schema.md). Strict JSON,
validated with a Pydantic model, one object per slide. Both paths emit it.

```
SlideNote
  slide_number    int          1-based, equals the PDF page number
  page_role       PageRole     title | agenda | section_break | content
                               | references | blank
  title           str | null   null when the page shows no title
  reading         str          the page as a whole, in prose
  visuals         [Visual]
  concepts        [Concept]
  verbatim_spans  [str]        at most 3; exact strings visible on the page
  reader_note     str | null   set only when the read failed or degraded

Visual
  kind              VisualKind   diagram | chart | equation | comparison
                                 | screenshot | decorative
  description       str
  assertion         str | null   what the figure claims; null when decorative
  relates_to_slides [int]        possibly empty

Concept
  name            str
  status          ConceptStatus  explained_here | named_only | assumed_prior
  why_it_matters  str
```

### Rules that travel with the schema

- `reading` covers the page as a whole and may name a figure without unpacking
  it. `visuals` is the only place figure content is stated in detail. This is a
  prompt constraint, not a convention.
- Decorative images are emitted with `kind: decorative` and a null `assertion`,
  never dropped.
- `status: named_only` is the only trigger for a research lookup. Lookups are
  capped at 15 per deck.
- The image path never receives extracted text. The comparison is image versus
  text, not image-plus-text versus text.
- The page reader sees one slide and no neighbours. Facts spanning slides are
  assembled by the outline stage; the reader's only signal is
  `Visual.relates_to_slides`.
- An empty `concepts` list is a valid answer and is surfaced rather than
  suppressed.
- `verbatim_spans` is degenerate on the text path by construction, since its
  spans are copied from the text it was given. Reported anyway, with the
  asymmetry stated.

## The topic record

Locked by [ADR 0003](docs/adr/0003-cross-deck-topic-taxonomy.md). One entry per
topic in a subject's topic mastery profile.

```
Topic
  name             str          reused verbatim across decks once it exists
  first_seen_deck  str
  decks            [str]        every deck that contributed
  slide_citations  [(deck, slide_number)]
  exposure         int          slide count
  performance      derived      (correct, seen) read from attempts; see below
  created_reason   str | null   set when the topic was declared new
```

### Rules that travel with the record

- The topic list for a subject starts empty. The first deck matches nothing and
  reports so plainly; there is no bootstrap pass.
- Every run reports "N topics, M matched, K new".
- `exposure` and `performance` are never averaged together.
- Near-duplicate topics are flagged for a human, never merged automatically.
- A subject is picked from a dropdown of existing subjects or created
  explicitly, never inferred from a typed string.

## The quiz schema

Locked by [ADR 0005](docs/adr/0005-quiz-answer-key-and-retake-schema.md). The
format target is the instructors' own Quizzes 1 to 3: ten questions, four
options, one correct.

```
Question
  question_id          str          "<deck-slug>-q<NN>", stable within the quiz
  stem                 str
  options              [str]        exactly 4
  correct_index        int          0..3
  explanation          str          why the correct option is correct
  distractor_rationale [str | null] exactly 4; entry at correct_index is null
  slide_citations      [int]        at least 1
  topic                str          a topic name from the subject's topic list
  source               Source       prose | visual

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

### Rules that travel with the schema

- Ten questions, always, whatever the deck length.
- Only the image path generates a quiz. `source: visual` counts how many
  questions the text path could not have asked.
- Banned in a stem or an option: dates, named authors, paper titles. Also no
  "all of the above" and no "none of the above". Numbers are allowed when the
  number is the reasoning and banned when the number is the fact.
- A question that cannot cite a slide is dropped, not kept.
- The grader is deterministic and makes no model call. It returns the verdict,
  the explanation, the rationale for the option actually chosen, and a per-topic
  rollup.
- Grading writes nothing to `profile.json`. It appends one attempt file.
- A retake targets the three weakest topics with `seen >= 3` at two questions
  each, then fills the remaining four from topics with `seen < 3`, oldest
  exposure first. With no attempts on record it refuses rather than improvising.
- A retake never reuses a question. It resolves each target topic to its
  `slide_citations` and generates from those `pages-image` notes in the `latest`
  run of each contributing deck, so it costs no page reads and needs those run
  directories to still exist.

## Decisions on record

- [ADR 0001](docs/adr/0001-model-provider-and-vision-model.md): Anthropic
  `claude-opus-5` at every stage, one page image per request at 150 DPI, hosted
  web search for the research step.
- [ADR 0002](docs/adr/0002-per-slide-note-schema.md): the slide note schema
  above.
- [ADR 0003](docs/adr/0003-cross-deck-topic-taxonomy.md): the cross-deck topic
  taxonomy and the topic record above.
- [ADR 0004](docs/adr/0004-artifact-layout-and-memory-schema.md): the on-disk
  layout above, flat JSON with no database, one committed golden run, and
  memory that stays local to a machine.
- [ADR 0005](docs/adr/0005-quiz-answer-key-and-retake-schema.md): the quiz,
  attempt, and retake schemas above, a deterministic grader, and performance as
  a derived (correct, seen) pair.
- [ADR 0006](docs/adr/0006-eval-protocol-and-results-table.md): two metrics
  rather than three, figure-only fact recovery primary over a headline
  denominator of three with slide 10 called out separately, citation accuracy
  as an image-path-only check, one golden run plus a repeatability probe, the
  empty results table, a committed `eval/` directory, and a Thursday-noon abort
  rule.
