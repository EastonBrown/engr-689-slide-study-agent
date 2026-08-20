"""Page reader stage for image and text paths."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from .. import config, llm, paths
from ..schemas import (
    Manifest,
    PageRole,
    PathKind,
    PathStats,
    SlideNote,
    SlideNoteDraft,
    StageUsage,
)


SYSTEM_PROMPT = """Read exactly one lecture slide and return one SlideNoteDraft.

The image path receives only the rendered slide image. The text path receives
only extracted text. Use the same schema either way. The reader sees no
neighbouring slides. Keep figure content in visuals; reading may name a visual
but must not duplicate its assertion. Emit decorative visuals rather than
dropping them. Empty concepts are valid. Set reader_note only when the read is
failed or degraded.
"""


class PageReadFailed(RuntimeError):
    """A slide read exhausted its retries or failed before a usable note."""

    def __init__(self, message: str, usage: StageUsage | None = None) -> None:
        super().__init__(message)
        self.usage = usage or StageUsage(stage=PAGE_READER_STAGE)


PAGE_READER_STAGE = "page_reader"


@dataclass(frozen=True)
class PageReadRequest:
    run_dir: Path
    path_kind: PathKind
    slide_number: int
    image_path: Path | None
    extracted_text: str | None


@dataclass(frozen=True)
class PageReadResult:
    note: SlideNoteDraft
    usage: StageUsage


class PageReader(Protocol):
    def read(self, request: PageReadRequest) -> PageReadResult:
        """Read one slide into a draft note."""


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


class AnthropicPageReader:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or llm.create_client()

    def read(self, request: PageReadRequest) -> PageReadResult:
        result = llm.structured_call(
            self.client,
            response_model=SlideNoteDraft,
            messages=[{"role": "user", "content": _message_content(request)}],
            max_tokens=config.MAX_TOKENS_PAGE_READER,
            effort=config.EFFORT_PAGE_READER,
            stage=PAGE_READER_STAGE,
            system=SYSTEM_PROMPT,
        )
        return PageReadResult(note=result.output, usage=result.usage)


def _message_content(request: PageReadRequest) -> list[dict[str, object]]:
    intro: dict[str, object] = {
        "type": "text",
        "text": f"Read slide {request.slide_number} on the {request.path_kind.value} path.",
    }
    if request.path_kind == PathKind.image:
        if request.image_path is None:
            raise PageReadFailed("image path has no rendered image")
        data = base64.b64encode(request.image_path.read_bytes()).decode("ascii")
        return [
            intro,
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": data,
                },
            },
        ]
    return [
        intro,
        {
            "type": "text",
            "text": request.extracted_text or "",
        },
    ]


def _slides_from_rendered_pages(run_dir: Path) -> list[int]:
    slides: list[int] = []
    for target in sorted((run_dir / "pages-render").glob("*.txt")):
        try:
            slides.append(int(target.stem))
        except ValueError:
            continue
    return slides


def _request_for(run_dir: Path, path_kind: PathKind, slide_number: int) -> PageReadRequest:
    if path_kind == PathKind.image:
        return PageReadRequest(
            run_dir=run_dir,
            path_kind=path_kind,
            slide_number=slide_number,
            image_path=paths.page_render_png(run_dir, slide_number),
            extracted_text=None,
        )
    text_path = paths.page_render_txt(run_dir, slide_number)
    return PageReadRequest(
        run_dir=run_dir,
        path_kind=path_kind,
        slide_number=slide_number,
        image_path=None,
        extracted_text=text_path.read_text(encoding="utf-8") if text_path.is_file() else "",
    )


def _should_read(
    run_dir: Path, path_kind: PathKind, slide_number: int, resume: bool
) -> bool:
    if not resume:
        return True
    existing = paths.read_json(paths.page_note(run_dir, path_kind.value, slide_number))
    if existing is None:
        return True
    try:
        note = SlideNote.model_validate(existing)
    except ValidationError:
        return True
    return note.reader_note is not None


def _failed_note(slide_number: int, message: str) -> SlideNote:
    return SlideNote(
        slide_number=slide_number,
        page_role=PageRole.content,
        title=None,
        reading="",
        visuals=[],
        concepts=[],
        verbatim_spans=[],
        reader_note=message,
    )


def _write_one_note(
    run_dir: Path, reader: PageReader, request: PageReadRequest
) -> tuple[PathKind, SlideNote, StageUsage]:
    try:
        result = reader.read(request)
        note = SlideNote(slide_number=request.slide_number, **result.note.model_dump())
        usage = result.usage
    except llm.StructuredCallError as error:
        note = _failed_note(request.slide_number, str(error))
        usage = error.usage
    except PageReadFailed as error:
        note = _failed_note(request.slide_number, str(error))
        usage = error.usage
    paths.write_model(paths.page_note(run_dir, request.path_kind.value, request.slide_number), note)
    return request.path_kind, note, usage


def _load_manifest(run_dir: Path) -> Manifest | None:
    payload = paths.read_json(paths.manifest_file(run_dir))
    return Manifest.model_validate(payload) if payload is not None else None


def _update_manifest(
    run_dir: Path,
    manifest: Manifest | None,
    counts: dict[PathKind, tuple[int, int, int]],
    usage: StageUsage,
) -> None:
    if manifest is None:
        return

    stats_by_path = {stat.path: stat for stat in manifest.paths}
    for path_kind, (attempted, succeeded, reader_notes) in counts.items():
        existing = stats_by_path.get(path_kind, PathStats(path=path_kind))
        stages = list(existing.completed_stages)
        if "page_reader" not in stages:
            stages.append("page_reader")
        stats_by_path[path_kind] = existing.model_copy(
            update={
                "slides_attempted": attempted,
                "slides_succeeded": succeeded,
                "reader_notes": reader_notes,
                "completed_stages": stages,
            }
        )

    stage_usage = [item for item in manifest.stage_usage if item.stage != PAGE_READER_STAGE]
    stage_usage.append(usage)
    manifest = manifest.model_copy(
        update={
            "paths": list(stats_by_path.values()),
            "stage_usage": stage_usage,
            "total_cost_usd": sum(item.cost_usd for item in stage_usage),
        }
    )
    paths.write_model(paths.manifest_file(run_dir), manifest)


def read_run_pages(
    run_dir: Path,
    *,
    reader: PageReader | None = None,
    paths_to_read: list[PathKind] | None = None,
    slide_numbers: range | list[int] | None = None,
    resume: bool = False,
    max_concurrency: int = config.READER_CONCURRENCY,
) -> None:
    """Read rendered pages into per-slide notes and update the manifest."""

    run_dir = Path(run_dir)
    reader = reader or AnthropicPageReader()
    selected_paths = paths_to_read or [PathKind.image, PathKind.text]
    selected_slides = list(slide_numbers) if slide_numbers is not None else _slides_from_rendered_pages(run_dir)

    requests = [
        _request_for(run_dir, path_kind, slide)
        for path_kind in selected_paths
        for slide in selected_slides
        if _should_read(run_dir, path_kind, slide, resume)
    ]
    usage = StageUsage(stage=PAGE_READER_STAGE)
    counts: dict[PathKind, list[int]] = {
        path_kind: [0, 0, 0] for path_kind in selected_paths
    }

    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        futures = [executor.submit(_write_one_note, run_dir, reader, request) for request in requests]
        for future in as_completed(futures):
            path_kind, note, item_usage = future.result()
            counts[path_kind][0] += 1
            if note.reader_note is None:
                counts[path_kind][1] += 1
            else:
                counts[path_kind][2] += 1
            usage = _add_usage(usage, item_usage)

    _update_manifest(
        run_dir,
        _load_manifest(run_dir),
        {
            path_kind: (values[0], values[1], values[2])
            for path_kind, values in counts.items()
        },
        usage,
    )
