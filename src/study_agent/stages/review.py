"""Write and validate the Markdown lesson review for both paths."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

from .. import config, llm, paths
from ..prompts import review as review_prompts
from ..schemas import (
    CacheEntry,
    ConceptStatus,
    Manifest,
    Outline,
    PathKind,
    ReviewDraft,
    SlideNote,
    StageUsage,
)


REVIEW_STAGE = "review"
_CITATION = re.compile(r"\[(slides?\s+([0-9]+(?:\s*,\s*[0-9]+)*))\]")


class ReviewError(RuntimeError):
    """The model returned a review that violates citation constraints."""


class Reviewer(Protocol):
    usage: StageUsage

    def write(self, context: str) -> str:
        """Write one complete Markdown review."""


class AnthropicReviewer:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or llm.create_client()
        self.usage = StageUsage(stage=REVIEW_STAGE)

    def write(self, context: str) -> str:
        result = llm.structured_call(
            self.client,
            response_model=ReviewDraft,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": review_prompts.WRITE_REVIEW},
                        {"type": "text", "text": context},
                    ],
                }
            ],
            max_tokens=config.MAX_TOKENS_REVIEW,
            effort=config.EFFORT_REVIEW,
            stage=REVIEW_STAGE,
        )
        self.usage = _add_usage(self.usage, result.usage)
        return result.output.markdown


def _add_usage(first: StageUsage, second: StageUsage) -> StageUsage:
    return StageUsage(
        stage=REVIEW_STAGE,
        calls=first.calls + second.calls,
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        cache_read_tokens=first.cache_read_tokens + second.cache_read_tokens,
        web_searches=first.web_searches + second.web_searches,
        cost_usd=first.cost_usd + second.cost_usd,
    )


def _load_notes(run_dir: Path, path_kind: PathKind) -> list[SlideNote]:
    notes: list[SlideNote] = []
    for source in sorted(paths.notes_dir(run_dir, path_kind.value).glob("*.json")):
        payload = paths.read_json(source)
        if payload is not None:
            notes.append(SlideNote.model_validate(payload))
    return notes


def _load_outline(run_dir: Path, path_kind: PathKind) -> Outline:
    payload = paths.read_json(paths.outline_file(run_dir, path_kind.value))
    if payload is None:
        raise ReviewError(f"missing {path_kind.value} outline")
    return Outline.model_validate(payload)


def _load_research(run_dir: Path, concepts: set[str]) -> list[CacheEntry]:
    entries: list[CacheEntry] = []
    for source in sorted(paths.run_research_dir(run_dir).glob("*.json")):
        payload = paths.read_json(source)
        if payload is not None:
            entry = CacheEntry.model_validate(payload)
            if entry.concept in concepts:
                entries.append(entry)
    return entries


def _context(outline: Outline, notes: list[SlideNote], research: list[CacheEntry]) -> str:
    return (
        "OUTLINE:\n"
        + outline.model_dump_json()
        + "\nSLIDE NOTES:\n"
        + "\n".join(note.model_dump_json() for note in notes)
        + "\nRESEARCH ENTRIES:\n"
        + "\n".join(entry.model_dump_json() for entry in research)
    )


def _survivor(slide: int, superseded: set[int]) -> int:
    candidate = slide + 1
    while candidate in superseded:
        candidate += 1
    return candidate


def rewrite_citations(markdown: str, superseded: list[int]) -> str:
    """Rewrite citations pointing at build-up frames to their survivor."""

    superseded_set = set(superseded)

    def replace(match: re.Match[str]) -> str:
        prefix = "slides" if match.group(1).startswith("slides") else "slide"
        numbers = [int(item.strip()) for item in match.group(2).split(",")]
        rewritten = [
            str(_survivor(number, superseded_set)) if number in superseded_set else str(number)
            for number in numbers
        ]
        return f"[{prefix} {', '.join(rewritten)}]"

    return _CITATION.sub(replace, markdown)


def validate_citations(markdown: str, covered: set[int]) -> None:
    """Reject citations to skipped, unassigned, or unknown slides."""

    for match in _CITATION.finditer(markdown):
        numbers = [int(item.strip()) for item in match.group(2).split(",")]
        invalid = [number for number in numbers if number not in covered]
        if invalid:
            raise ReviewError(f"review cites uncovered slide(s): {invalid}")


def annotate_degraded_citations(markdown: str, degraded: set[int]) -> str:
    """Make the required degradation note explicit beside affected citations."""

    if not degraded:
        return markdown
    lines: list[str] = []
    for line in markdown.splitlines(keepends=True):
        cited = {
            int(item.strip())
            for match in _CITATION.finditer(line)
            for item in match.group(2).split(",")
        }
        if cited & degraded and "degrad" not in line.lower():
            newline = "\n" if line.endswith("\n") else ""
            lines.append(line.rstrip("\r\n") + " (degraded read)" + newline)
        else:
            lines.append(line)
    return "".join(lines)


def _mark_complete(run_dir: Path, usage: StageUsage) -> None:
    payload = paths.read_json(paths.manifest_file(run_dir))
    if payload is None:
        return
    manifest = Manifest.model_validate(payload)
    updated = []
    for stat in manifest.paths:
        stages = list(stat.completed_stages)
        if REVIEW_STAGE not in stages:
            stages.append(REVIEW_STAGE)
        updated.append(stat.model_copy(update={"completed_stages": stages}))
    stage_usage = [item for item in manifest.stage_usage if item.stage != REVIEW_STAGE]
    stage_usage.append(usage)
    paths.write_model(
        paths.manifest_file(run_dir),
        manifest.model_copy(
            update={
                "paths": updated,
                "stage_usage": stage_usage,
                "total_cost_usd": sum(item.cost_usd for item in stage_usage),
            }
        ),
    )


def review_run(
    run_dir: Path,
    *,
    reviewer: Reviewer | None = None,
) -> None:
    """Write review-image.md and review-text.md, one model call per path."""

    reviewer = reviewer or AnthropicReviewer()
    for path_kind in (PathKind.image, PathKind.text):
        outline = _load_outline(Path(run_dir), path_kind)
        notes = _load_notes(Path(run_dir), path_kind)
        concepts = {
            concept.name
            for note in notes
            for concept in note.concepts
            if concept.status == ConceptStatus.named_only
        }
        research = _load_research(Path(run_dir), concepts)
        markdown = reviewer.write(_context(outline, notes, research))
        markdown = rewrite_citations(markdown, outline.superseded)
        covered = {slide for topic in outline.topics for slide in topic.slides}
        validate_citations(markdown, covered)
        degraded = {
            slide
            for topic in outline.topics
            for slide in topic.degraded_slides
        }
        markdown = annotate_degraded_citations(markdown, degraded)
        paths.write_text(paths.review_file(Path(run_dir), path_kind.value), markdown)
    _mark_complete(Path(run_dir), getattr(reviewer, "usage", StageUsage(stage=REVIEW_STAGE)))
