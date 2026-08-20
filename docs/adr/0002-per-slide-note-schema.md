# ADR 0002: The per-slide note schema

- Status: accepted
- Date: 2026-08-19
- Resolves: [Lock the per-slide note schema](https://github.com/EastonBrown/engr-689-slide-study-agent/issues/4)
- Builds on: [ADR 0001](0001-model-provider-and-vision-model.md)

## Context

One `SlideNote` is what the page reader returns for a single slide. It is the
most load-bearing interface in the system. Every downstream stage consumes it,
both the image path and the text-extraction baseline produce it, and the
evaluation measures what it captured. The schema is fixed here so that any
stage can be implemented without reopening the question.

Constraints carried in from elsewhere: page images are the ingestion path and
text extraction exists only as the baseline; ADR 0001 pins one page image per
request, which means the reader sees exactly one slide and no neighbours; the
decks are text-native, uniformly sized, and free of animation-duplicate pages,
so a PDF page number is a citable slide number.

## Decision

### Shape

Seven content fields, strict JSON, produced through structured output and
validated with a Pydantic model. One object per slide.

```
SlideNote
  slide_number    int          1-based, equals the PDF page number
  page_role       PageRole     title | agenda | section_break | content
                               | references | blank
  title           str | null   null when the page shows no title
  reading         str          the page as a whole, in prose
  visuals         [Visual]
  concepts        [Concept]
  verbatim_spans  [str]        at most 3
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

`reader_note` is a failure channel rather than an eighth content field; the
seven-field count refers to the content payload.

### Figures are typed, not prose

Figure content is a typed `visuals` list rather than being folded into
`reading`. The project's entire claim is that figures carry meaning text
extraction discards, so the thing being claimed gets its own field. It is also
what the on-camera inspector panel points at.

Decorative images are emitted with `kind: decorative` and a null `assertion`
rather than dropped. Dropping them makes "the reader judged this unimportant"
indistinguishable from "the reader missed it", and the count of non-decorative
visuals per deck is a free number for the results table. The Day 1 principles
deck carries 229 embedded images across 65 slides, so most images are not
load-bearing and this distinction does real work.

Full structured representation per figure type, for example chart series and
rankings as data, was rejected. It is a day of work for figure types that
appear once each.

### `reading` and `visuals` do not overlap

Prompt-level constraint, not a hope: `reading` covers the page as a whole and
may name a figure without unpacking it; `visuals` is the only place figure
content is stated in detail. Without the rule the reader describes the same
diagram twice, and it does so on exactly the slides that matter most.

### The reader does not decide what is figure-only

The page reader runs blind. It never receives the page's extracted text, not
even as a spelling aid for small type. The cost is occasional garbled proper
nouns; the benefit is that the comparison stays image versus text rather than
image-plus-text versus text.

Figure-only fact recovery is scored by hand against the four pre-labeled Day 3
facts recorded in `data/course/README.md`. A side-by-side diff of image-path
and text-path notes on the same slide is built for the demo, but it is a
visualization, not the reported metric. Asking the reader to mark what the
image adds, by handing it the extracted text, was rejected: it contaminates the
reader with the baseline's output and would not survive scrutiny.

### Cross-slide facts are joined downstream

The reader sees one page, so a fact spanning two slides cannot be assembled by
it. Day 3 slides 55 and 56 are the case that matters: slide 55 gives three
captions with no images, slide 56 extracts to zero characters, and the fact
only exists across the pair.

The outline stage, which sees every note at once, is where adjacent slides are
joined. The reader's only contribution is `Visual.relates_to_slides`, which
lets it say "this appears to continue slide 55" without having seen it.

A two-image window was rejected because it breaks ADR 0001's resolution
argument as soon as any request exceeds 20 image blocks. Passing the previous
slide's note as context was rejected because it serializes a stage that is
otherwise concurrent across all 66 slides, and that concurrency is what keeps a
full run inside the demo's patience.

### Concepts carry the research hook

`concepts` is a list of objects, not strings. A `status` of `named_only` is
what triggers a research lookup; `explained_here` and `assumed_prior` do not.
`assumed_prior` is the category that would otherwise spend the budget looking
up "what is a neural network". Lookups are capped at 15 per deck, which is the
number behind `max_uses` in ADR 0001.

Strings would force a second model pass whose only job was deciding what to
look up.

### The baseline emits the identical schema

The text-extraction path uses the same schema, the same prompt, the same model,
and the same effort setting. Only the content block differs: a page image on
one path, extracted page text on the other. That is what makes the results
table an ablation of the input modality rather than a comparison of two
different systems.

The consequence is that `verbatim_spans` is degenerate on the baseline. Its
spans are copied from the text it was given, so it string-matches at close to
100% by construction. Both numbers are reported and the asymmetry is stated
outright in the limitations section.

### Empty pages produce structure, not inventions

`page_role` distinguishes title, agenda, section-break, references, and blank
pages from content. The reader may emit an empty `concepts` list rather than
inventing one. A page typed `content` that yields no concepts is surfaced as a
signal, not suppressed as a bug: Day 3 slide 56 is exactly that page on the
text path, and it is one of the better demonstrations in the project.

### Failures live inside the artifact

`reader_note` is set when the vision pass returns something unusable, refuses,
or the page is genuinely illegible. Failure cases are graded twice in this
course, so they are kept inside the artifact where the inspector panel can
display one, rather than in a run log that has to be searched on Friday
morning.

## Consequences

- `verbatim_spans` turns citation checking into a string match rather than a
  model judgement, which is the difference between a metric computable inside
  the build window and one that is not. It is capped at three spans per slide.
- The outline stage inherits real work: it owns topic grouping, coverage, and
  now cross-slide fact assembly. It is the largest unspecified stage remaining.
- Concurrency across slides is preserved, since no note depends on another.
- The image path will occasionally misread small type with no fallback. This is
  an accepted, named limitation rather than a defect to fix.
- How `Concept.name` is normalized across decks and subjects is not decided
  here. It belongs to the cross-deck memory taxonomy.
- Where notes are written on disk is not decided here. It belongs to the
  artifact layout.
