"""Prompt for the citation-bearing lesson review."""

WRITE_REVIEW = """Write a student-readable lesson review in Markdown.

Use exactly one Markdown section (a ## heading) for each supplied outline topic,
in outline order. Every factual claim must end with a citation in the exact form
[slide N] or [slides N, M], and citations may name only covered slides. If a
slide is degraded, say so inline when citing it. Add a separate ## Bridged facts
section only when confirmed bridged facts are supplied. Mark research-derived
explanations as **Research:** and include the research citation's URL in Markdown
link form. Do not add front matter, a title before the topic sections, or claims
not supported by the supplied notes and research.

Return only the Markdown body."""
