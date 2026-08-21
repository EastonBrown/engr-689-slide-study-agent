# Slide Deck to Study Guide Agent

Final project for ENGR 689 (SPTP: Multimodal LLM Agents), Texas A&M, fall 2026
sprint session. Instructors: Yu Zhang and Cheng Zhang.

**Status: end to end on one deck. Every stage in the table below runs, and one
complete run over a 66-slide course deck is committed under `examples/golden/`,
both paths, with the quiz it generated and the memory it wrote. The interface
runs that pipeline and replays that run. What is not claimed is breadth: the
system has been exercised on the course decks, not on arbitrary ones, and the
limitations section is still being filled in.**

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

## Planned components

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
| `--resume` | Reopens the latest run for this deck instead of starting a new one; with `--read-pages`, retries only the slides whose read failed |
| `--outline` | Groups the notes into topics and writes `outline-{image,text}.json` |

## The interface, and replaying a finished run

```
streamlit run app.py
```

Choose a subject, upload a deck, and press the button. Every screen is
reconstructed from the run directory on disk, so a rerun, a refresh, or a
crashed stage never loses what has already been written.

One complete run is committed under `examples/golden/` (66 slides, both
paths). Selecting the PDF it was produced from,
`data/course/slides/Day3 Principle.pdf`, puts the interface in replay mode:
the upload is matched to that run by content hash, the run is installed into
`runs/` and `memory/`, and the seven stage boxes animate from the files that
run actually wrote. Replay makes no API calls and needs no key. Two knobs:

| Variable | What it does |
|---|---|
| `STUDY_AGENT_REPLAY_DELAY` | Seconds per replayed log line, default 0.06 |
| `STUDY_AGENT_REPLAY_STAGE_DELAY` | Seconds held on a finished stage box, default 0.6 |
| `STUDY_AGENT_REPLAY_RUN` | Points the interface at any completed run directory instead of an upload |

At the defaults the golden run's 192 lines replay in about sixteen seconds. A
run that stopped before a later stage replays what exists and marks the rest
absent.

Then score the image path's quoted spans against the text the renderer
extracted from the same pages:

```
python eval/score_spans.py runs/engr-689/day3-principle/<run-timestamp>
```

The checks are `python -m pytest` and `python -m mypy`, both from the repo root.

## Limitations and failure cases

To be documented as they are found. Failing outputs are kept rather than
discarded.

## Acknowledgements

External models, libraries, datasets, and any borrowed figures will be credited
here as they are added.
