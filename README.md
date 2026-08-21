# Slide Deck to Study Guide Agent

Final project for ENGR 689 (SPTP: Multimodal LLM Agents), Texas A&M, fall 2026
sprint session. Instructors: Yu Zhang and Cheng Zhang.

**Status: the full pipeline runs — render, the page reader, outline, research,
both lesson reviews, the image-path quiz, the deterministic grader, retakes,
and the Streamlit interface. `eval/results.md` is the one open item: the
protocol and labels are locked and a golden run is committed, but the
figure-only-fact and citation-accuracy tables have not been hand-scored yet.
The table below marks the whole target design, all of which is now built.**

## What it does

Takes a PDF lecture slide deck and produces two things for a student:

1. **A lesson review.** What the deck covered, the key concepts, and why they
   matter, with slide-number citations back into the source deck. The agent
   researches the topics rather than only paraphrasing, so it explains concepts
   the deck merely names.
2. **A knowledge check.** A short multiple-choice quiz over that material. The
   student takes it, sees an answer key with explanations, and can retake it
   weighted toward what they missed.

## The core design decision

Slides are ingested as **page images**, not extracted text. Slide decks are a
visual medium: architecture diagrams, plots, equations, and figure comparisons
carry meaning that PDF text extraction discards.

This was validated by hand on a 66-slide course deck before any code was written.
The image path surfaced four facts present only in the rendered pages and absent
from the extracted text: a textbook-figure definition of an agent, an
encoder-popularity bar chart, a three-directions diagram, and a side-by-side
retrieval comparison.

A text-only path is also planned, kept specifically so the two can be run against
the same deck and compared directly.

## Components

| Component | Role |
|---|---|
| Render | PDF pages to images |
| Page reader | Vision pass over each page, producing structured per-slide notes |
| Outline | Group slides into topics, decide what matters |
| Research | Look up concepts the deck names but does not explain |
| Review writer | Draft the lesson review with slide-number provenance |
| Quiz generator | Write the knowledge check from the outline and notes |
| Grader | Score the attempt, explain each answer |
| Memory | Per-deck artifacts and missed-question history that shape retakes |

All eight run today, both from the CLI (`python -m study_agent.pipeline`) and
from the Streamlit interface (`streamlit run app.py`), which also owns
grading, retakes, and topic memory end to end.

## Setup

Python 3.14. From the repo root:

```
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt    # Windows
.venv/bin/pip install -r requirements-dev.txt        # macOS, Linux
```

`requirements.txt` leads with `-e .`, so this installs the package itself along
with its dependencies. That is what puts `study_agent` on the import path; the
commands below will not resolve without it, and no manual `PYTHONPATH` is needed
or wanted.

Model calls need an Anthropic credential, from `ANTHROPIC_API_KEY` in the
environment or a gitignored `.env` at the repo root.

## Running it

A headless run over one deck, writing a timestamped run directory under `runs/`:

```
python -m study_agent.pipeline "data/course/slides/Day3 Principle.pdf" --subject engr-689
```

Render alone is the default. Add stages as needed:

| Flag | What it adds |
|---|---|
| `--read-pages` | The vision and text passes, one `SlideNote` per slide per path |
| `--slides 55-61` | Restricts the page reads to a slice, for a cheap check |
| `--resume` | With `--read-pages`, retries only the slides whose read failed |
| `--outline` | Groups the notes into topics and writes `outline-{image,text}.json` |
| `--research` | Looks up named-only concepts, capped at 15/deck, into the shared research cache |
| `--review` | Writes both `review-{image,text}.md` lesson reviews |
| `--quiz` | Writes the image-path `quiz.json`, up to 10 questions |

Grading, retakes, and the topic mastery profile are driven from the Streamlit
interface (`streamlit run app.py`), not the CLI.

Then score the image path's quoted spans against the text the renderer
extracted from the same pages:

```
python eval/score_spans.py runs/engr-689/day3-principle/<run-timestamp>
```

The checks are `python -m pytest` and `python -m mypy`, both from the repo root.

## Limitations and failure cases

Failing and degraded outputs are kept on disk rather than discarded — a
`reader_note` marks a failed or degraded slide read instead of silently
dropping it.

- Exercised on this class's five course decks, not on arbitrary decks.
- The text path is a baseline only: it writes a review but generates no quiz
  and makes no memory contribution.
- Research lookups are capped at 15 per deck; the quiz is capped at 10
  questions per deck, 3 per topic.
- Memory is local to the machine — never merged or committed.
- A model contract violation (for example, a slide claimed by two topics)
  degrades gracefully after one repair attempt rather than aborting the run.
- `eval/results.md` is not yet filled in — the protocol and labels are
  locked and a golden run is committed, but hand-scoring hasn't happened.

## Acknowledgements

Model: Anthropic `claude-opus-5`, one page image per request, hosted web
search for the research stage. Libraries: `pydantic`, `streamlit`,
`pypdfium2`. Data: this course's own lecture decks, Fall 2026.
