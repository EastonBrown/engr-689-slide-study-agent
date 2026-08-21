# Project Rundown: Slide Deck to Study Guide Agent

Handoff document for building ENGR 689 final presentation slides. This describes
the course context, the grading rubric, and what the project actually does and
does not do. Use it as ground truth; do not invent capabilities or results not
stated here.

## Course context

ENGR 689 (SPTP: Multimodal LLM Agents), Texas A&M, fall 2026 sprint session.
Instructors: Yu Zhang and Cheng Zhang. This project is the final project, worth
60% of the course grade, split three ways:

- Presentation: 20%
- Slides: 20%
- Code/Demo: 20%

Timeline:
- Build window was 2026-08-19 to 2026-08-20 only (two days).
- Friday 2026-08-21, in class: 15-minute live presentation. Cannot be
  pre-recorded.
- Friday 2026-08-21, 11:59pm: slides, code link, demo link submitted via
  Canvas.

## What the rubric actually rewards

This is the single most important thing for slide design: **novelty earns
nothing.** The rubric explicitly states the project does not need to do
anything ChatGPT itself cannot do. What is graded is the layer built around
the LLM core — the interface, the workflow, the tools, the memory, the
planning, the data handling — and how visibly that effort is demonstrated on
screen.

Implications for the slides and the talk track:
- Limitations and failure cases are scored twice (once in the live
  presentation, once in the slides). Do not hide weak results — show them.
- Every model, library, dataset, and borrowed figure needs a credit line.
- The interface was designed to be filmed: which slide is being read, what
  was extracted, and why a question was written should all be legible on
  screen. Slides showing the actual interface mid-run make this argument
  better than a bullet list describing it.
- Coding style and repo cleanliness are not graded. Don't spend slide space on
  code quality.
- The repo must be public and verified reachable logged-out.

## What the project does

Takes a PDF lecture slide deck and produces two things for a student:

1. **A lesson review** — what the deck covered, the key concepts, and why they
   matter, with slide-number citations back into the source deck. It researches
   topics the deck names but doesn't explain, rather than only paraphrasing.
2. **A knowledge check** — a short multiple-choice quiz over that material. The
   student takes it, sees an answer key with explanations, and can retake a
   quiz weighted toward what they missed.

## The core design decision (this is the thesis of the project)

Slides are ingested as **page images**, not extracted PDF text. A slide deck is
a visual medium — architecture diagrams, plots, equations, and figure
comparisons carry meaning that text extraction discards.

This was validated by hand, before any code was written, on a real 66-slide
course deck. The image path surfaced four facts present only in the rendered
page images and absent from extracted text:
- A textbook-figure definition of an agent
- An encoder-popularity bar chart
- A three-directions diagram
- A side-by-side retrieval comparison

A second path — the **text path** — runs the identical pipeline but feeds the
page reader extracted PDF text instead of the image. It exists purely as a
baseline, so the two paths can be run on the same deck and compared directly.
This image-vs-text comparison is the evaluation story and should be a slide on
its own.

## Pipeline stages

| Stage | Role |
|---|---|
| Render | PDF pages to images (150 DPI) |
| Page reader | Vision (or text) pass over each page, producing one structured `SlideNote` per slide, run concurrently across the deck |
| Outline | Groups slides into topics, decides what's covered vs. skipped, confirms cross-slide "bridged facts," allocates the quiz question budget |
| Research | Looks up concepts the deck names but doesn't explain (capped at 15 lookups/deck), backed by a committed, shared cache keyed by query hash |
| Review writer | Drafts the lesson review with slide-number provenance |
| Quiz generator | Writes the knowledge check from the outline and notes (image path only) |
| Grader | Deterministic, no model call — scores the attempt, explains each answer, rolls up performance by topic |
| Memory | Per-subject topic mastery profile (exposure and performance, tracked separately, never averaged) that shapes retakes |

Model: Anthropic `claude-opus-5` at every stage, one page image per request at
150 DPI / 2576px clamp, with hosted web search for the research step.

## Interface and demo

A Streamlit app (`streamlit run app.py`): choose a subject, upload a deck,
press the button. Every screen reconstructs itself from the run directory on
disk, so a rerun, refresh, or crashed stage never loses completed work.

**Replay mode** exists specifically for the live demo and for grading without
burning API credits: one full run over a real 66-slide deck (both paths, quiz,
memory writes) is committed to the repo under `examples/golden/`. Selecting
that same source PDF in the interface replays that run — matched by content
hash — with the seven stage boxes animating from the actual log lines that run
produced. No API calls, no key needed, ~16 seconds at default replay speed.
This is the safe fallback if live API calls are flaky during the presentation.

## Memory and retakes

Memory is scoped per "subject" (e.g., one class). A topic mastery profile
accumulates across every deck in a subject, tracking two axes kept separate on
purpose: **exposure** (how much material touched a topic, in slides) and
**performance** (correct/seen from quiz attempts — never collapsed into a
percentage, and reported as "insufficient evidence" below 3 sightings). A
retake generates a fresh 10-question quiz targeting the three weakest topics
plus the least-tested ones, built from slide notes already on disk (no new
page reads).

## Evaluation

Two metrics (ADR 0006):
1. **Figure-only fact recovery** (primary) — of 3 hand-labeled facts present
   only in slide images (a 4th, on slide 10, is a known-weak case reported
   separately since its labels extract as text even though the spatial
   relation that is the actual content does not), how many does each path
   recover.
2. **Citation accuracy** (image path only) — whether quiz `slide_citations`
   and `verbatim_spans` are actually supported by the cited slide, as a
   hallucination check.

**Status as of the last commit: the results table in `eval/results.md` is not
yet filled in.** The pipeline runs end-to-end and the golden run is committed,
but hand-scoring the fact-recovery and citation-accuracy tables has not
happened yet. Do not present numeric results that aren't in that file — say
the pipeline and eval protocol are built and the scoring pass is in progress,
if that's still true when the deck is built.

## Explicit limitations (say these out loud — they're scored twice)

- Exercised on the five course decks for this class, not on arbitrary decks.
- The text path is a baseline only — it generates a review but no quiz and
  makes no memory contribution.
- Research lookups capped at 15/deck; quiz capped at 10 questions/deck,
  topics capped at 3 questions each.
- Memory is local to the machine — never merged or committed.
- A contract violation from the model (e.g., a slide claimed by two topics)
  degrades gracefully after one repair attempt rather than aborting the run.

## What's explicitly out of scope

Model training, a real large-scale dataset, a full eval harness beyond the
hand-scored table above, web scraping, or anything gated behind an API
waitlist.

## For the slide builder

Good candidate slides, roughly in presentation order:
1. Problem/motivation — students don't have a fast way to turn a slide deck
   into a study guide + quiz.
2. The core design bet — image path vs. text path, with the four hand-found
   figure-only facts as the concrete hook.
3. Pipeline diagram — the 8-stage table above.
4. Live or replayed demo — screenshot or clip of the Streamlit interface
   walking through a run.
5. Memory/retake mechanic — exposure vs. performance, retake targeting.
6. Eval protocol and whatever results are actually filled in by presentation
   time — pull live from `eval/results.md`, don't pre-write numbers here.
7. Limitations, honestly stated.
8. Acknowledgements — Anthropic Claude (`claude-opus-5`), pydantic, streamlit,
   pypdfium2, and the course decks themselves as the data source.
