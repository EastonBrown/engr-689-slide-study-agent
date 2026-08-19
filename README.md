# Slide Deck to Study Guide Agent

Final project for ENGR 689 (SPTP: Multimodal LLM Agents), Texas A&M, fall 2026
sprint session. Instructors: Yu Zhang and Cheng Zhang.

**Status: scaffolding. The pipeline described below is the target design, not yet
implemented. This section will be replaced with real setup and run instructions
as components land.**

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

To be written once dependencies are pinned.

## Running it

To be written.

## Limitations and failure cases

To be documented as they are found. Failing outputs are kept rather than
discarded.

## Acknowledgements

External models, libraries, datasets, and any borrowed figures will be credited
here as they are added.
