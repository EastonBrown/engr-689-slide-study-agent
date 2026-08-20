"""Prompts for quiz generation."""

SYSTEM = (
    "Generate multiple-choice quiz questions from the image-path outline and "
    "slide notes. Exactly four options, one correct index, no dates, named "
    "authors, paper titles, all-of-the-above, or none-of-the-above. Numbers "
    "are allowed only when the number is part of reasoning, not a recalled "
    "fact. Every question must cite slides and name its topic. Do not cite "
    "degraded or skipped slides. Follow the outline question budget exactly; "
    "if a bridged_fact slot exists, produce exactly one visual-source bridged "
    "fact question for it."
)

WRITE = (
    "Generate quiz questions for this image-path payload. If this is a "
    "regeneration request, generate only the requested shortfall."
)
