"""Prompt for the image-path knowledge check."""

GENERATE_QUIZ = """Write multiple-choice knowledge-check questions from the supplied image-path outline and slide notes.

Return only the requested structured object. Follow the question budget exactly when
possible. Each question must have exactly four options and four distractor rationales;
the rationale at the correct index must be null. Cite one or more covered slides, and
use source=visual only when the answer depends on a visual assertion. Use topic=
bridged_fact for the single reserved bridged-fact question. Never cite degraded,
skipped, superseded, or unassigned slides.

Do not ask for dates, named authors, paper titles, all of the above, or none of the
above. Numbers may appear only when the learner must use the number in reasoning,
not when the number itself is the fact. Prefer scenario-shaped stems and distractors
at the same level of abstraction as the answer.

If a question cannot be supported by a slide citation, omit it rather than inventing
one."""

GENERATE_RETAKE = """Write fresh multiple-choice retake questions from the supplied stored image-path notes.

Follow the supplied retake question budget by topic. Do not reuse any question stem
listed under QUESTIONS TO AVOID VERBATIM. Every question must have exactly four
options, four distractor rationales with null at the correct index, and at least one
real slide citation from the supplied notes. Never cite a degraded note. Keep the
same bans and visual/prose source rules as the original quiz prompt."""
