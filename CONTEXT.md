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
`data/course/README.md`. These are the ground truth for the headline metric.

**Subject.** The namespace for memory. A topic mastery profile accumulates
across every deck in a subject; a different class gets its own profile.

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

## Decisions on record

- [ADR 0001](docs/adr/0001-model-provider-and-vision-model.md): Anthropic
  `claude-opus-5` at every stage, one page image per request at 150 DPI, hosted
  web search for the research step.
- [ADR 0002](docs/adr/0002-per-slide-note-schema.md): the slide note schema
  above.
