"""Prompts for lesson review writing."""

SYSTEM = (
    "Write a student-facing lesson review in Markdown with no front matter. "
    "Use one section per outline topic in order. Every deck-derived claim must "
    "carry a slide citation as [slide N] or [slides N, M]. Mark research-derived "
    "explanations explicitly and cite their source links."
)

WRITE = "Write the {path_kind} path review from this run payload."
