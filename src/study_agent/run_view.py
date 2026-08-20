"""What one run looks like on screen, read entirely from disk.

Issue #25. Streamlit reruns the whole script on every interaction, so the
interface cannot hold a run in memory: every screen has to be reconstructable
from the run directory alone. That is why ADR 0004's write-every-stage-boundary
rule is load-bearing rather than convenient, and this module is where that rule
is cashed in.

Nothing here imports Streamlit and nothing here calls a model. `app.py` is a
rendering layer over these functions, which keeps the numbers on camera
testable without driving a browser. `replay.py` (issue #27) reads the same
views to animate a completed run.

No number produced here is a literal. Counts come from the manifest, from the
outline files, or from counting artifacts on disk, and a stage that has written
nothing reports as pending rather than as a failure or as a zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pydantic import ValidationError

from . import paths
from .schemas import Manifest, Outline, PathKind, PathStats, SlideNote

# The seven stage boxes, in the order they appear down the page. Locked by
# issue #8 (variant A) and by the screen order in docs/spec.md. The keys are
# also what `pipeline.stage_log` tags its lines with, so the interface can
# route a live line into the right box without parsing the message.
STAGE_RENDER = "render"
STAGE_PAGE_READER_IMAGE = "page_reader_image"
STAGE_PAGE_READER_TEXT = "page_reader_text"
STAGE_OUTLINE = "outline"
STAGE_RESEARCH = "research"
STAGE_REVIEW = "review"
STAGE_QUIZ = "quiz"

STAGE_KEYS: tuple[str, ...] = (
    STAGE_RENDER,
    STAGE_PAGE_READER_IMAGE,
    STAGE_PAGE_READER_TEXT,
    STAGE_OUTLINE,
    STAGE_RESEARCH,
    STAGE_REVIEW,
    STAGE_QUIZ,
)

STAGE_LABELS: dict[str, str] = {
    STAGE_RENDER: "Render and preflight",
    STAGE_PAGE_READER_IMAGE: "Page read, image path",
    STAGE_PAGE_READER_TEXT: "Page read, text path (baseline)",
    STAGE_OUTLINE: "Outline",
    STAGE_RESEARCH: "Research",
    STAGE_REVIEW: "Review",
    STAGE_QUIZ: "Quiz",
}

# How many replayed log lines a collapsed box keeps. A 66-slide read produces
# 66 of them and the box is scrolled past on camera, not read.
DETAIL_LIMIT = 200


class StageState(str, Enum):
    """Where a stage stands, decided by what is on disk.

    `pending` is the state that matters for issue #25: the review, research,
    and quiz stages do not exist yet, and their boxes have to read as not run
    rather than as broken, so this ticket can land while they are in flight.
    """

    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"


@dataclass(frozen=True)
class StageView:
    key: str
    label: str
    state: StageState
    summary: str
    detail: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FailureView:
    """One degraded read, with the page image that produced it.

    ADR 0002's `reader_note` is the failure channel: a slide that could not be
    read cleanly still writes its file. `image_path` is None when the render
    artifact itself is gone, which is the case that has to render as an absence
    rather than as a broken image.
    """

    path: str
    slide_number: int
    reader_note: str | None
    image_path: Path | None


@dataclass(frozen=True)
class RunSummary:
    subject_slug: str
    deck_slug: str
    deck_filename: str
    run_timestamp: str
    model: str
    prompt_version: str
    dpi: int
    started_at: str
    ended_at: str | None
    page_count: int
    slides_read: int
    slides_total: int
    degraded: int
    text_slides_read: int
    text_slides_total: int
    topics_matched: int
    topics_new: int
    outline_ran: bool
    research_lookups: int
    research_cache_hits: int
    cost_usd: float
    superseded_count: int
    superseded: list[int]
    image_only: bool
    downscaled: bool
    readable: bool


# --- Reading the run directory ----------------------------------------------


def load_manifest(run_dir: Path) -> Manifest | None:
    """The run's manifest, or None when there is not one that parses.

    A run directory with no manifest is a directory the pipeline never
    finished creating, so it is not a run to display.
    """

    payload = paths.read_json(paths.manifest_file(Path(run_dir)))
    if payload is None:
        return None
    try:
        return Manifest.model_validate(payload)
    except ValidationError:
        return None


def _path_stats(manifest: Manifest | None, path_kind: PathKind) -> PathStats:
    if manifest is not None:
        for stat in manifest.paths:
            if stat.path is path_kind:
                return stat
    return PathStats(path=path_kind)


def _stage_complete(manifest: Manifest | None, stage: str) -> bool:
    """Whether any path recorded the stage as finished.

    Read per path rather than globally: the page reader marks image and text
    separately, and a run that read only the image path must not show the text
    box as done.
    """

    if manifest is None:
        return False
    return any(stage in stat.completed_stages for stat in manifest.paths)


def load_outline(run_dir: Path, path_kind: PathKind) -> Outline | None:
    payload = paths.read_json(paths.outline_file(Path(run_dir), path_kind.value))
    if payload is None:
        return None
    try:
        return Outline.model_validate(payload)
    except ValidationError:
        return None


def _note_files(run_dir: Path, path_kind: PathKind) -> list[Path]:
    directory = paths.notes_dir(Path(run_dir), path_kind.value)
    if not directory.is_dir():
        return []
    return sorted(target for target in directory.glob("*.json") if target.stem.isdigit())


def _rendered_pages(run_dir: Path) -> int:
    directory = Path(run_dir) / "pages-render"
    if not directory.is_dir():
        return 0
    return len([target for target in directory.glob("*.png") if target.stem.isdigit()])


def _research_files(run_dir: Path) -> list[Path]:
    directory = paths.run_research_dir(Path(run_dir))
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def _review_files(run_dir: Path) -> list[Path]:
    return [
        target
        for path_kind in (PathKind.image, PathKind.text)
        for target in [paths.review_file(Path(run_dir), path_kind.value)]
        if target.is_file()
    ]


# --- The seven stage boxes --------------------------------------------------


def stage_views(run_dir: Path) -> list[StageView]:
    """One view per stage box, in screen order, for any run directory.

    Safe on a directory that does not exist: every box reads as pending, which
    is what the screen shows before the first run of a session.
    """

    run_dir = Path(run_dir)
    manifest = load_manifest(run_dir)
    return [
        _render_view(run_dir, manifest),
        _page_reader_view(run_dir, manifest, PathKind.image),
        _page_reader_view(run_dir, manifest, PathKind.text),
        _outline_view(run_dir, manifest),
        _research_view(run_dir, manifest),
        _review_view(run_dir, manifest),
        _quiz_view(run_dir, manifest),
    ]


def _view(key: str, state: StageState, summary: str, detail: list[str]) -> StageView:
    return StageView(
        key=key,
        label=STAGE_LABELS[key],
        state=state,
        summary=summary,
        detail=detail[:DETAIL_LIMIT],
    )


def _render_view(run_dir: Path, manifest: Manifest | None) -> StageView:
    rendered = _rendered_pages(run_dir)
    if manifest is None and rendered == 0:
        return _view(STAGE_RENDER, StageState.pending, "not run", [])

    if manifest is None:
        return _view(
            STAGE_RENDER,
            StageState.running,
            f"{rendered} page images written, no manifest yet",
            [],
        )

    preflight = manifest.preflight
    detail = [
        f"{preflight.page_count} pages at {preflight.page_width_px}"
        f"x{preflight.page_height_px} px",
        f"{preflight.text_native_pages} of {preflight.page_count} pages are text-native",
    ]
    if preflight.downscaled:
        detail.append("long edge downscaled to the resolution tier")
    if preflight.image_only:
        detail.append("deck is image-only: the text path runs but is not comparable")
    if preflight.superseded:
        listed = ", ".join(str(slide) for slide in preflight.superseded)
        detail.append(f"build-up frames superseded: {listed}")
    elif preflight.buildup_detection_ran:
        detail.append("build-up detection ran and found no superseded frame")

    summary = f"{preflight.page_count} pages at {manifest.dpi} DPI"
    if preflight.superseded_count:
        summary += f", {preflight.superseded_count} superseded"
    if not preflight.readable:
        return _view(STAGE_RENDER, StageState.failed, "deck would not open", detail)
    state = (
        StageState.complete
        if _stage_complete(manifest, "render")
        else StageState.running
    )
    return _view(STAGE_RENDER, state, summary, detail)


def _page_reader_view(
    run_dir: Path, manifest: Manifest | None, path_kind: PathKind
) -> StageView:
    key = (
        STAGE_PAGE_READER_IMAGE
        if path_kind is PathKind.image
        else STAGE_PAGE_READER_TEXT
    )
    files = _note_files(run_dir, path_kind)
    stats = _path_stats(manifest, path_kind)
    complete = "page_reader" in stats.completed_stages

    if not files and not complete:
        return _view(key, StageState.pending, "not run", [])

    detail: list[str] = []
    degraded_on_disk = 0
    for target in files:
        slide = int(target.stem)
        payload = paths.read_json(target)
        if payload is None:
            degraded_on_disk += 1
            detail.append(f"slide {slide}: note would not parse")
            continue
        try:
            note = SlideNote.model_validate(payload)
        except ValidationError:
            degraded_on_disk += 1
            detail.append(f"slide {slide}: note does not match the schema")
            continue
        if note.reader_note:
            degraded_on_disk += 1
            detail.append(f"slide {slide}: DEGRADED, {note.reader_note}")
        else:
            detail.append(
                f"slide {slide}: {len(note.visuals)} visual(s), "
                f"{len(note.concepts)} concept(s)"
            )

    if complete:
        attempted = stats.slides_attempted or len(files)
        summary = f"{stats.slides_succeeded} of {attempted} slides read"
        if stats.reader_notes:
            summary += f", {stats.reader_notes} degraded"
        return _view(key, StageState.complete, summary, detail)

    # Mid-stage, or a stage that aborted before it could claim completion. The
    # files on disk are the only truth available, and they are enough: ADR
    # 0004 makes every finished slide its own file.
    summary = f"{len(files)} notes written so far"
    if degraded_on_disk:
        summary += f", {degraded_on_disk} degraded"
    return _view(key, StageState.running, summary, detail)


def _outline_view(run_dir: Path, manifest: Manifest | None) -> StageView:
    outlines = {
        path_kind: load_outline(run_dir, path_kind)
        for path_kind in (PathKind.image, PathKind.text)
    }
    present = {kind: value for kind, value in outlines.items() if value is not None}
    complete = _stage_complete(manifest, "outline")
    if not present and not complete:
        return _view(STAGE_OUTLINE, StageState.pending, "not run", [])

    detail: list[str] = []
    image_outline = present.get(PathKind.image) or next(iter(present.values()), None)
    for path_kind, outline in present.items():
        detail.append(f"{path_kind.value} path: {len(outline.topics)} topics")
        for topic in outline.topics:
            kind = "new topic" if topic.is_new else "matched topic"
            detail.append(
                f"  {kind}: {topic.name} ({len(topic.slides)} slide(s))"
            )
        if outline.bridged_facts:
            detail.append(
                f"  {len(outline.bridged_facts)} bridged fact(s) from "
                f"{outline.candidates_proposed} candidate(s)"
            )
        if outline.unassigned:
            detail.append(f"  unassigned slides: {outline.unassigned}")
        if outline.topic_cap_exceeded:
            detail.append("  topic cap exceeded, every topic kept")

    if image_outline is None:
        return _view(STAGE_OUTLINE, StageState.running, "no outline written yet", detail)
    new = sum(1 for topic in image_outline.topics if topic.is_new)
    matched = len(image_outline.topics) - new
    summary = f"{len(image_outline.topics)} topics, {matched} matched, {new} new"
    state = StageState.complete if complete else StageState.running
    return _view(STAGE_OUTLINE, state, summary, detail)


def _research_view(run_dir: Path, manifest: Manifest | None) -> StageView:
    files = _research_files(run_dir)
    stats = _path_stats(manifest, PathKind.image)
    complete = "research" in stats.completed_stages
    if not files and not complete:
        return _view(STAGE_RESEARCH, StageState.pending, "not run", [])
    summary = (
        f"{stats.research_lookups} lookups, {stats.research_cache_hits} cache hits"
    )
    detail = [target.stem for target in files]
    state = StageState.complete if complete else StageState.running
    return _view(STAGE_RESEARCH, state, summary, detail)


def _review_view(run_dir: Path, manifest: Manifest | None) -> StageView:
    files = _review_files(run_dir)
    complete = _stage_complete(manifest, "review")
    if not files and not complete:
        return _view(STAGE_REVIEW, StageState.pending, "not run", [])
    detail = [f"{target.name}, {len(paths.read_text(target).splitlines())} lines" for target in files]
    summary = f"{len(files)} review(s) written"
    state = StageState.complete if complete else StageState.running
    return _view(STAGE_REVIEW, state, summary, detail)


def _quiz_view(run_dir: Path, manifest: Manifest | None) -> StageView:
    payload = paths.read_json(paths.quiz_file(Path(run_dir)))
    complete = _stage_complete(manifest, "quiz")
    if payload is None and not complete:
        return _view(STAGE_QUIZ, StageState.pending, "not run", [])
    questions = payload.get("questions", []) if isinstance(payload, dict) else []
    visual = sum(1 for question in questions if question.get("source") == "visual")
    detail = [
        f"{question.get('question_id', '?')} [{question.get('source', '?')}] "
        f"slides {question.get('slide_citations', [])}"
        for question in questions
    ]
    summary = f"{len(questions)} questions, {visual} visual, {len(questions) - visual} prose"
    state = StageState.complete if complete else StageState.running
    return _view(STAGE_QUIZ, state, summary, detail)


# --- The run summary --------------------------------------------------------


def run_summary(run_dir: Path) -> RunSummary | None:
    """The numbers under the stage boxes. None when there is no manifest."""

    run_dir = Path(run_dir)
    manifest = load_manifest(run_dir)
    if manifest is None:
        return None

    image = _path_stats(manifest, PathKind.image)
    text = _path_stats(manifest, PathKind.text)
    outline = load_outline(run_dir, PathKind.image)
    new_topics = sum(1 for topic in outline.topics if topic.is_new) if outline else 0
    matched = (len(outline.topics) - new_topics) if outline else 0

    return RunSummary(
        subject_slug=manifest.subject_slug,
        deck_slug=manifest.deck_slug,
        deck_filename=manifest.deck_filename,
        run_timestamp=manifest.run_timestamp,
        model=manifest.model,
        prompt_version=manifest.prompt_version,
        dpi=manifest.dpi,
        started_at=manifest.started_at,
        ended_at=manifest.ended_at,
        page_count=manifest.preflight.page_count,
        slides_read=image.slides_succeeded,
        slides_total=image.slides_attempted or manifest.preflight.page_count,
        degraded=image.reader_notes,
        text_slides_read=text.slides_succeeded,
        text_slides_total=text.slides_attempted or manifest.preflight.page_count,
        topics_matched=matched,
        topics_new=new_topics,
        outline_ran=outline is not None,
        research_lookups=image.research_lookups,
        research_cache_hits=image.research_cache_hits,
        cost_usd=manifest.total_cost_usd,
        superseded_count=manifest.preflight.superseded_count,
        superseded=list(manifest.preflight.superseded),
        image_only=manifest.preflight.image_only,
        downscaled=manifest.preflight.downscaled,
        readable=manifest.preflight.readable,
    )


# --- Failures and degraded reads --------------------------------------------


def failures(run_dir: Path) -> list[FailureView]:
    """Every note that did not read cleanly, ordered by slide then path.

    A note that will not parse counts as a failure rather than as an absence.
    ADR 0002's rule is that a missing file never means anything, so a file that
    exists and cannot be read is the one case worth surfacing loudly.
    """

    run_dir = Path(run_dir)
    found: list[FailureView] = []
    for path_kind in (PathKind.image, PathKind.text):
        for target in _note_files(run_dir, path_kind):
            slide = int(target.stem)
            payload = paths.read_json(target)
            reader_note: str | None
            if payload is None:
                reader_note = "the note file on disk would not parse"
            else:
                try:
                    reader_note = SlideNote.model_validate(payload).reader_note
                except ValidationError:
                    reader_note = "the note file on disk would not parse as a SlideNote"
            if reader_note is None:
                continue
            image = paths.page_render_png(run_dir, slide)
            found.append(
                FailureView(
                    path=path_kind.value,
                    slide_number=slide,
                    reader_note=reader_note,
                    image_path=image if image.is_file() else None,
                )
            )
    order = {PathKind.image.value: 0, PathKind.text.value: 1}
    return sorted(found, key=lambda item: (item.slide_number, order[item.path]))


# --- Finding the run to show ------------------------------------------------


def runs_for_subject(layout: paths.Layout, subject_slug: str) -> list[Path]:
    """Every run directory under a subject, newest first.

    The run timestamp names the directory and sorts, which is exactly why ADR
    0004 chose that name. A directory with no parseable manifest is skipped:
    it is a run the pipeline never finished creating.
    """

    subject_dir = layout.runs_dir() / subject_slug
    if not subject_dir.is_dir():
        return []
    found = [
        run_dir
        for deck_dir in subject_dir.iterdir()
        if deck_dir.is_dir()
        for run_dir in deck_dir.iterdir()
        if run_dir.is_dir() and load_manifest(run_dir) is not None
    ]
    return sorted(found, key=lambda run_dir: run_dir.name, reverse=True)


def latest_run(layout: paths.Layout, subject_slug: str) -> Path | None:
    """The newest run across every deck in the subject, or None."""

    found = runs_for_subject(layout, subject_slug)
    return found[0] if found else None
