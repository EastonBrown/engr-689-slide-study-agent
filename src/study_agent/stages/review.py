"""Review writer stage for image and text paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .. import config, llm, paths
from ..prompts import review as review_prompts
from ..schemas import (
    CacheEntry,
    Manifest,
    Outline,
    PageRole,
    PathKind,
    PathStats,
    SlideNote,
    StageUsage,
    Strict,
)


REVIEW_STAGE = "review"
_SINGLE_CITATION = re.compile(r"\[slide (\d+)\]")
_MULTI_CITATION = re.compile(r"\[slides ([0-9,\s]+)\]")
_SOURCE_LINK = re.compile(r"\[[^\]]+\]\(https?://[^)]+\)")


class ReviewDraft(Strict):
    markdown: str = Field(description="Markdown review with slide/source citations.")


@dataclass(frozen=True)
class ReviewRequest:
    path_kind: PathKind
    outline: Outline
    notes: list[SlideNote]
    research_entries: list[CacheEntry]


@dataclass(frozen=True)
class ReviewWriteResult:
    markdown: str
    usage: StageUsage


class ReviewWriter(Protocol):
    def write(self, request: ReviewRequest) -> ReviewWriteResult:
        """Write one path's lesson review."""


class ReviewContractError(RuntimeError):
    """Generated review markdown violated the issue #21 contract."""


class AnthropicReviewWriter:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or llm.create_client()

    def write(self, request: ReviewRequest) -> ReviewWriteResult:
        result = llm.structured_call(
            self.client,
            response_model=ReviewDraft,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": review_prompts.WRITE.format(
                                path_kind=request.path_kind.value
                            ),
                        },
                        {"type": "text", "text": request.outline.model_dump_json()},
                        {
                            "type": "text",
                            "text": "[" + ",".join(note.model_dump_json() for note in request.notes) + "]",
                        },
                        {
                            "type": "text",
                            "text": "["
                            + ",".join(
                                entry.model_dump_json()
                                for entry in request.research_entries
                            )
                            + "]",
                        },
                    ],
                }
            ],
            max_tokens=config.MAX_TOKENS_REVIEW,
            effort=config.EFFORT_REVIEW,
            stage=REVIEW_STAGE,
            system=review_prompts.SYSTEM,
        )
        return ReviewWriteResult(markdown=result.output.markdown, usage=result.usage)


def _add_usage(first: StageUsage, second: StageUsage) -> StageUsage:
    return StageUsage(
        stage=first.stage,
        calls=first.calls + second.calls,
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        cache_read_tokens=first.cache_read_tokens + second.cache_read_tokens,
        web_searches=first.web_searches + second.web_searches,
        cost_usd=first.cost_usd + second.cost_usd,
    )


def rewrite_superseded_citations(
    markdown: str, superseded_survivors: dict[int, int]
) -> str:
    """Rewrite single-slide citations that point at superseded frames."""

    def replace_single(match: re.Match[str]) -> str:
        slide = int(match.group(1))
        return f"[slide {superseded_survivors.get(slide, slide)}]"

    def replace_multi(match: re.Match[str]) -> str:
        slides = [
            superseded_survivors.get(int(piece.strip()), int(piece.strip()))
            for piece in match.group(1).split(",")
            if piece.strip()
        ]
        unique = list(dict.fromkeys(slides))
        return "[slides " + ", ".join(str(slide) for slide in unique) + "]"

    return _MULTI_CITATION.sub(replace_multi, _SINGLE_CITATION.sub(replace_single, markdown))


def _citation_slides(markdown: str) -> list[int]:
    slides = [int(match.group(1)) for match in _SINGLE_CITATION.finditer(markdown)]
    for match in _MULTI_CITATION.finditer(markdown):
        slides.extend(
            int(piece.strip()) for piece in match.group(1).split(",") if piece.strip()
        )
    return slides


def _section_titles(markdown: str) -> list[str]:
    return [
        line[2:].strip()
        for line in markdown.splitlines()
        if line.startswith("# ") and not line.startswith("## ")
    ]


def _nonempty_section_lines(markdown: str) -> list[str]:
    return [
        line.strip()
        for line in markdown.splitlines()
        if line.strip() and not line.startswith("#")
    ]


def validate_review_markdown(
    markdown: str,
    *,
    outline: Outline,
    notes_by_slide: dict[int, SlideNote],
    superseded_survivors: dict[int, int],
    research_entries: list[CacheEntry],
) -> list[str]:
    """Return human-readable contract violations in a generated review."""

    errors: list[str] = []
    if markdown.startswith("---"):
        errors.append("front matter")

    topic_names = [topic.name for topic in outline.topics]
    section_titles = [
        title
        for title in _section_titles(markdown)
        if title not in {"Bridged Facts", "Research"}
    ]
    if section_titles != topic_names:
        errors.append("section order does not match outline")
    for line in _nonempty_section_lines(markdown):
        if line.startswith("- "):
            line = line[2:].strip()
        if (
            "Research-derived" not in line
            and not _SINGLE_CITATION.search(line)
            and not _MULTI_CITATION.search(line)
        ):
            errors.append(f"uncited claim: {line}")

    covered = {slide for topic in outline.topics for slide in topic.slides}
    skipped = {item.slide_number for item in outline.skipped}
    bridged_slides = {
        superseded_survivors.get(slide, slide)
        for fact in outline.bridged_facts
        for slide in fact.slides
    }
    for slide in _citation_slides(markdown):
        if slide in skipped:
            errors.append(f"skipped slide {slide} is cited")
        if slide in superseded_survivors:
            errors.append(f"superseded slide {slide} is cited")
        note = notes_by_slide.get(slide)
        if slide not in covered and slide not in bridged_slides:
            errors.append(f"uncovered slide {slide} is cited")
        if note is not None and note.reader_note is not None:
            marker = f"degraded: {note.reader_note}"
            if marker not in markdown:
                errors.append(f"degraded slide {slide} lacks inline degradation note")

    if outline.bridged_facts and "# Bridged Facts" not in markdown:
        errors.append("bridged facts section missing")
    if research_entries:
        if "Research-derived" not in markdown:
            errors.append("Research-derived explanation is not marked")
        if not _SOURCE_LINK.search(markdown):
            errors.append("research citation link missing")
    return errors


def _load_notes(run_dir: Path, path_kind: PathKind) -> list[SlideNote]:
    notes: list[SlideNote] = []
    for target in sorted(paths.notes_dir(run_dir, path_kind.value).glob("*.json")):
        payload = paths.read_json(target)
        if payload is not None:
            notes.append(SlideNote.model_validate(payload))
    return notes


def _load_research_entries(run_dir: Path, path_kind: PathKind) -> list[CacheEntry]:
    entries: list[CacheEntry] = []
    path_dir = paths.run_research_path_dir(run_dir, path_kind.value)
    for target in sorted(path_dir.glob("*.json")):
        payload = paths.read_json(target)
        if payload is not None:
            entries.append(CacheEntry.model_validate(payload))
    return entries


def _survivors_from_notes(notes: list[SlideNote], superseded: list[int]) -> dict[int, int]:
    superseded_set = set(superseded)
    content_slides = sorted(
        note.slide_number
        for note in notes
        if note.page_role == PageRole.content and note.slide_number not in superseded_set
    )
    survivors: dict[int, int] = {}
    for slide in superseded:
        later = [candidate for candidate in content_slides if candidate > slide]
        if later:
            survivors[slide] = later[0]
    return survivors


def _load_manifest(run_dir: Path) -> Manifest | None:
    payload = paths.read_json(paths.manifest_file(run_dir))
    return Manifest.model_validate(payload) if payload is not None else None


def _update_manifest(
    run_dir: Path,
    manifest: Manifest | None,
    usage_by_path: dict[PathKind, StageUsage],
) -> None:
    if manifest is None:
        return
    stats_by_path = {stat.path: stat for stat in manifest.paths}
    usage = StageUsage(stage=REVIEW_STAGE)
    for path_kind, path_usage in usage_by_path.items():
        existing = stats_by_path.get(path_kind, PathStats(path=path_kind))
        stages = list(existing.completed_stages)
        if REVIEW_STAGE not in stages:
            stages.append(REVIEW_STAGE)
        stats_by_path[path_kind] = existing.model_copy(
            update={
                "completed_stages": stages,
                "review_calls": path_usage.calls,
                "review_input_tokens": path_usage.input_tokens,
                "review_output_tokens": path_usage.output_tokens,
                "review_cost_usd": path_usage.cost_usd,
            }
        )
        usage = _add_usage(usage, path_usage)
    stage_usage = [item for item in manifest.stage_usage if item.stage != REVIEW_STAGE]
    if usage.calls:
        stage_usage.append(usage)
    manifest = manifest.model_copy(
        update={
            "paths": list(stats_by_path.values()),
            "stage_usage": stage_usage,
            "total_cost_usd": sum(item.cost_usd for item in stage_usage),
        }
    )
    paths.write_model(paths.manifest_file(run_dir), manifest)


def review_run(
    run_dir: Path,
    *,
    writer: ReviewWriter | None = None,
) -> None:
    """Write review-image.md and review-text.md, then update the manifest."""

    run_dir = Path(run_dir)
    writer = writer or AnthropicReviewWriter()
    usage_by_path: dict[PathKind, StageUsage] = {}
    for path_kind in (PathKind.image, PathKind.text):
        research_entries = _load_research_entries(run_dir, path_kind)
        outline_payload = paths.read_json(paths.outline_file(run_dir, path_kind.value))
        if outline_payload is None:
            continue
        outline = Outline.model_validate(outline_payload)
        notes = _load_notes(run_dir, path_kind)
        notes_by_slide = {note.slide_number: note for note in notes}
        survivors = _survivors_from_notes(notes, outline.superseded)
        result = writer.write(
            ReviewRequest(
                path_kind=path_kind,
                outline=outline,
                notes=notes,
                research_entries=research_entries,
            )
        )
        markdown = rewrite_superseded_citations(result.markdown, survivors)
        errors = validate_review_markdown(
            markdown,
            outline=outline,
            notes_by_slide=notes_by_slide,
            superseded_survivors=survivors,
            research_entries=research_entries,
        )
        if errors:
            raise ReviewContractError("; ".join(errors))
        paths.write_text(paths.review_file(run_dir, path_kind.value), markdown)
        usage_by_path[path_kind] = result.usage
    _update_manifest(run_dir, _load_manifest(run_dir), usage_by_path)
