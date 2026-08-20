"""Disk-backed data for the Streamlit interface."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from study_agent import config, memory, paths, schemas
from study_agent.stages import grade

_SLIDE_CITATION = re.compile(r"\[slide(?:s)? ([0-9,\\s]+)\]", re.IGNORECASE)

STAGES: tuple[tuple[str, str], ...] = (
    ("render", "Render"),
    ("page_reader", "Page reader"),
    ("outline", "Outline"),
    ("research", "Research"),
    ("review", "Review"),
    ("quiz", "Quiz"),
    ("grade", "Grade"),
)


@dataclass(frozen=True)
class SubjectOption:
    slug: str
    display_name: str


@dataclass(frozen=True)
class StageState:
    key: str
    name: str
    state: str
    summary: str
    log_lines: list[str]


@dataclass(frozen=True)
class RunSummary:
    run_dir: Path
    subject_slug: str
    deck_slug: str
    deck_filename: str
    run_timestamp: str
    slides_read: int
    topics_matched: int
    topics_new: int
    research_lookups: int
    research_cache_hits: int
    total_cost_usd: float
    image_only: bool
    superseded_count: int
    text_native_pages: int
    page_count: int


@dataclass(frozen=True)
class DegradedRead:
    path_kind: str
    slide_number: int
    reader_note: str
    image_path: Path
    note: schemas.SlideNote


@dataclass(frozen=True)
class ReviewCitation:
    slide_number: int
    image_path: Path
    note: schemas.SlideNote


@dataclass(frozen=True)
class ReviewDocument:
    markdown: str
    citations: list[ReviewCitation]


@dataclass(frozen=True)
class PathComparison:
    path_kind: str
    slides_read: int | None
    visuals_found: int | None
    not_applicable: bool = False
    note: str | None = None


@dataclass(frozen=True)
class ComparisonScoreboard:
    image: PathComparison
    text: PathComparison
    figure_only_label: str
    slide_10_label: str


def subject_options(layout: paths.Layout) -> list[SubjectOption]:
    payload = paths.read_json(layout.subjects_file())
    if payload is None:
        return []
    registry = schemas.SubjectsRegistry.model_validate(payload)
    return [
        SubjectOption(slug=subject.slug, display_name=subject.display_name)
        for subject in sorted(registry.subjects, key=lambda item: item.display_name.lower())
    ]


def active_run_file(layout: paths.Layout) -> Path:
    return layout.runs_dir() / ".active-run"


def write_active_run(layout: paths.Layout, run_dir: Path) -> None:
    paths.write_text(active_run_file(layout), str(run_dir))


def read_active_run(layout: paths.Layout) -> Path | None:
    target = active_run_file(layout)
    if not target.is_file():
        return None
    raw = target.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    return Path(raw)


def clear_active_run(layout: paths.Layout) -> None:
    target = active_run_file(layout)
    if target.exists():
        target.unlink()


def create_subject(layout: paths.Layout, display_name: str) -> SubjectOption:
    cleaned = display_name.strip()
    if not cleaned:
        raise ValueError("Subject name is required.")
    option = SubjectOption(slug=paths.slugify(cleaned), display_name=cleaned)
    existing = subject_options(layout)
    if option.slug not in {item.slug for item in existing}:
        payload = paths.read_json(layout.subjects_file())
        current = (
            schemas.SubjectsRegistry.model_validate(payload)
            if payload is not None
            else schemas.SubjectsRegistry(subjects=[])
        )
        registry = schemas.SubjectsRegistry(
            subjects=current.subjects
            + [
                schemas.SubjectEntry(
                    slug=option.slug,
                    display_name=option.display_name,
                    created_at=paths.utc_timestamp(),
                )
            ]
        )
        paths.write_model(layout.subjects_file(), registry)
        profile = schemas.Profile(
            schema_version=config.SCHEMA_VERSION,
            subject_slug=option.slug,
            topics=[],
        )
        paths.write_model(layout.profile_file(option.slug), profile)
    return option


def latest_run_summary(layout: paths.Layout, subject_slug: str) -> RunSummary | None:
    run_dir = _latest_run_for_subject(layout, subject_slug)
    if run_dir is None:
        return None
    return run_summary(run_dir)


def run_summary(run_dir: Path) -> RunSummary | None:
    manifest = _load_manifest(run_dir)
    if manifest is None:
        return None
    image = _path_stat(manifest, schemas.PathKind.image)
    text = _path_stat(manifest, schemas.PathKind.text)
    topics = _topic_counts(run_dir)
    return RunSummary(
        run_dir=run_dir,
        subject_slug=manifest.subject_slug,
        deck_slug=manifest.deck_slug,
        deck_filename=manifest.deck_filename,
        run_timestamp=manifest.run_timestamp,
        slides_read=manifest.preflight.page_count,
        topics_matched=topics[0],
        topics_new=topics[1],
        research_lookups=image.research_lookups + text.research_lookups,
        research_cache_hits=image.research_cache_hits + text.research_cache_hits,
        total_cost_usd=manifest.total_cost_usd,
        image_only=manifest.preflight.image_only,
        superseded_count=manifest.preflight.superseded_count,
        text_native_pages=manifest.preflight.text_native_pages,
        page_count=manifest.preflight.page_count,
    )


def stage_states(run_dir: Path) -> list[StageState]:
    manifest = _load_manifest(run_dir)
    completed = _completed_stages(manifest)
    return [_stage_state(run_dir, manifest, key, name, completed) for key, name in STAGES]


def degraded_reads(run_dir: Path) -> list[DegradedRead]:
    items: list[DegradedRead] = []
    for path_kind in (schemas.PathKind.image.value, schemas.PathKind.text.value):
        for target in sorted(paths.notes_dir(run_dir, path_kind).glob("*.json")):
            payload = paths.read_json(target)
            if payload is None:
                continue
            note = schemas.SlideNote.model_validate(payload)
            if note.reader_note:
                items.append(
                    DegradedRead(
                        path_kind=path_kind,
                        slide_number=note.slide_number,
                        reader_note=note.reader_note,
                        image_path=paths.page_render_png(run_dir, note.slide_number),
                        note=note,
                    )
                )
    return items


def review_document(run_dir: Path, path_kind: str) -> ReviewDocument | None:
    target = paths.review_file(run_dir, path_kind)
    if not target.is_file():
        return None
    markdown = target.read_text(encoding="utf-8")
    citations: list[ReviewCitation] = []
    seen: set[int] = set()
    for slide_number in _citation_numbers(markdown):
        if slide_number in seen:
            continue
        seen.add(slide_number)
        payload = paths.read_json(paths.page_note(run_dir, path_kind, slide_number))
        if payload is None:
            continue
        citations.append(
            ReviewCitation(
                slide_number=slide_number,
                image_path=paths.page_render_png(run_dir, slide_number),
                note=schemas.SlideNote.model_validate(payload),
            )
        )
    return ReviewDocument(markdown=markdown, citations=citations)


def comparison_scoreboard(
    run_dir: Path,
    *,
    eval_file: Path | None = None,
) -> ComparisonScoreboard:
    manifest = _load_manifest(run_dir)
    if manifest is None:
        raise ValueError(f"Run has no readable manifest: {run_dir}")
    image = _comparison_path(run_dir, manifest, schemas.PathKind.image)
    if manifest.preflight.image_only:
        text = PathComparison(
            path_kind=schemas.PathKind.text.value,
            slides_read=None,
            visuals_found=None,
            not_applicable=True,
            note="text path not applicable, this deck is image-only",
        )
    else:
        text = _comparison_path(run_dir, manifest, schemas.PathKind.text)
    figure_only, slide_10 = _figure_only_labels(run_dir, manifest, eval_file or paths.Layout().figure_only_facts_file())
    return ComparisonScoreboard(
        image=image,
        text=text,
        figure_only_label=figure_only,
        slide_10_label=slide_10,
    )


def submit_quiz_answers(
    layout: paths.Layout,
    run_dir: Path,
    choices_by_question: dict[str, int | None],
    *,
    attempt_id: str | None = None,
    taken_at: str | None = None,
) -> schemas.GradeResult:
    quiz_payload = paths.read_json(paths.quiz_file(run_dir))
    if quiz_payload is None:
        raise ValueError(f"Run has no readable quiz: {run_dir}")
    quiz = schemas.Quiz.model_validate(quiz_payload)
    choices = [choices_by_question.get(question.question_id) for question in quiz.questions]
    return grade.grade_quiz_file(
        paths.quiz_file(run_dir),
        choices,
        layout=layout,
        attempt_id=attempt_id,
        taken_at=taken_at,
    )


def latest_grade_result(layout: paths.Layout, run_dir: Path) -> schemas.GradeResult | None:
    quiz_payload = paths.read_json(paths.quiz_file(run_dir))
    manifest = _load_manifest(run_dir)
    if quiz_payload is None or manifest is None:
        return None
    quiz = schemas.Quiz.model_validate(quiz_payload)
    attempts = [
        attempt
        for attempt in memory.read_attempts(layout, manifest.subject_slug)
        if attempt.quiz_sha256 == paths.sha256_file(paths.quiz_file(run_dir))
    ]
    if not attempts:
        return None
    latest = sorted(attempts, key=lambda item: item.taken_at)[-1]
    choices = [
        None if response.unanswered else response.chosen_index
        for response in latest.responses
    ]
    return grade.grade_quiz(
        quiz,
        choices,
        quiz_sha256=latest.quiz_sha256,
        attempt_id=latest.attempt_id,
        taken_at=latest.taken_at,
    )


def generate_retake_for_subject(layout: paths.Layout, subject_slug: str) -> schemas.Quiz | str:
    result = memory.generate_retake(layout, subject_slug)
    if isinstance(result, memory.RetakeRefusal):
        return result.message
    return result


def latest_retake(layout: paths.Layout, subject_slug: str) -> schemas.Quiz | None:
    retakes_dir = layout.retakes_dir(subject_slug)
    if not retakes_dir.is_dir():
        return None
    retakes: list[schemas.Quiz] = []
    for target in sorted(retakes_dir.glob("*.json")):
        payload = paths.read_json(target)
        if payload is not None:
            retakes.append(schemas.Quiz.model_validate(payload))
    if not retakes:
        return None
    return sorted(retakes, key=lambda item: item.generated_at)[-1]


def _latest_run_for_subject(layout: paths.Layout, subject_slug: str) -> Path | None:
    subject_dir = layout.runs_dir() / subject_slug
    if not subject_dir.is_dir():
        return None
    candidates: list[tuple[str, Path]] = []
    for deck_dir in sorted(path for path in subject_dir.iterdir() if path.is_dir()):
        latest = layout.latest_run_dir(subject_slug, deck_dir.name)
        if latest is not None:
            candidates.append((latest.name, latest))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _load_manifest(run_dir: Path) -> schemas.Manifest | None:
    payload = paths.read_json(paths.manifest_file(run_dir))
    return schemas.Manifest.model_validate(payload) if payload is not None else None


def _path_stat(manifest: schemas.Manifest, path_kind: schemas.PathKind) -> schemas.PathStats:
    for item in manifest.paths:
        if item.path == path_kind:
            return item
    return schemas.PathStats(path=path_kind)


def _completed_stages(manifest: schemas.Manifest | None) -> dict[str, set[schemas.PathKind]]:
    if manifest is None:
        return {}
    completed: dict[str, set[schemas.PathKind]] = {}
    for path_stat in manifest.paths:
        for stage in path_stat.completed_stages:
            completed.setdefault(stage, set()).add(path_stat.path)
    return completed


def _topic_counts(run_dir: Path) -> tuple[int, int]:
    payload = paths.read_json(paths.outline_file(run_dir, schemas.PathKind.image.value))
    if payload is None:
        return 0, 0
    outline = schemas.Outline.model_validate(payload)
    matched = sum(1 for topic in outline.topics if not topic.is_new)
    new = sum(1 for topic in outline.topics if topic.is_new)
    return matched, new


def _citation_numbers(markdown: str) -> list[int]:
    numbers: list[int] = []
    for match in _SLIDE_CITATION.finditer(markdown):
        for raw in match.group(1).split(","):
            raw = raw.strip()
            if raw.isdigit():
                numbers.append(int(raw))
    return numbers


def _comparison_path(
    run_dir: Path,
    manifest: schemas.Manifest,
    path_kind: schemas.PathKind,
) -> PathComparison:
    stat = _path_stat(manifest, path_kind)
    notes = _notes(run_dir, path_kind)
    return PathComparison(
        path_kind=path_kind.value,
        slides_read=stat.slides_succeeded,
        visuals_found=sum(len(note.visuals) for note in notes),
    )


def _notes(run_dir: Path, path_kind: schemas.PathKind) -> list[schemas.SlideNote]:
    notes: list[schemas.SlideNote] = []
    for target in sorted(paths.notes_dir(run_dir, path_kind.value).glob("*.json")):
        payload = paths.read_json(target)
        if payload is not None:
            notes.append(schemas.SlideNote.model_validate(payload))
    return notes


def _figure_only_labels(
    run_dir: Path,
    manifest: schemas.Manifest,
    eval_file: Path,
) -> tuple[str, str]:
    payload = paths.read_json(eval_file)
    facts = _facts_for_deck(payload, manifest.deck_slug)
    if facts is None:
        return "not labeled for this deck", "not labeled for this deck"
    headline = [fact for fact in facts if fact.get("in_headline")]
    weak = [fact for fact in facts if not fact.get("in_headline") and 10 in _fact_slides(fact)]
    image_hits = sum(1 for fact in headline if _fact_hit(run_dir, schemas.PathKind.image, fact))
    text_hits = sum(1 for fact in headline if _fact_hit(run_dir, schemas.PathKind.text, fact))
    slide_10 = "partial on both sides" if weak else "not labeled for this deck"
    return f"{image_hits}/{len(headline)} vs {text_hits}/{len(headline)}", slide_10


def _facts_for_deck(payload: object, deck_slug: str) -> list[dict[str, object]] | None:
    if not isinstance(payload, dict):
        return None
    decks = payload.get("decks")
    if isinstance(decks, dict):
        deck_payload = decks.get(deck_slug)
        if isinstance(deck_payload, dict):
            facts = deck_payload.get("facts")
            if isinstance(facts, list):
                return [fact for fact in facts if isinstance(fact, dict)]
        return None
    if payload.get("deck_slug") == deck_slug:
        facts = payload.get("facts")
        if isinstance(facts, list):
            return [fact for fact in facts if isinstance(fact, dict)]
    return None


def _fact_hit(run_dir: Path, path_kind: schemas.PathKind, fact: dict[str, object]) -> bool:
    fact_text = str(fact.get("fact", "")).lower()
    for slide in _fact_slides(fact):
        payload = paths.read_json(paths.page_note(run_dir, path_kind.value, slide))
        if payload is None:
            continue
        note = schemas.SlideNote.model_validate(payload)
        if fact_text and fact_text in note.model_dump_json().lower():
            return True
    return False


def _fact_slides(fact: dict[str, object]) -> list[int]:
    raw_slides = fact.get("slides", [])
    slides = raw_slides if isinstance(raw_slides, list) else []
    return [slide for slide in slides if isinstance(slide, int)]


def _stage_state(
    run_dir: Path,
    manifest: schemas.Manifest | None,
    key: str,
    name: str,
    completed: dict[str, set[schemas.PathKind]],
) -> StageState:
    complete_paths = completed.get(key, set())
    required_paths = _required_paths(key)
    if required_paths and complete_paths >= required_paths:
        return StageState(
            key=key,
            name=name,
            state="complete",
            summary=_stage_summary(manifest, key),
            log_lines=_stage_logs(run_dir, manifest, key),
        )
    if complete_paths:
        return StageState(
            key=key,
            name=name,
            state="partial",
            summary=f"{name} partial: {', '.join(sorted(path.value for path in complete_paths))}.",
            log_lines=_stage_logs(run_dir, manifest, key),
        )
    return StageState(
        key=key,
        name=name,
        state="pending",
        summary=f"{name} waiting for artifacts.",
        log_lines=[],
    )


def _required_paths(key: str) -> set[schemas.PathKind]:
    if key in {"render", "page_reader", "outline", "research", "review"}:
        return {schemas.PathKind.image, schemas.PathKind.text}
    if key == "quiz":
        return {schemas.PathKind.image}
    return set()


def _stage_summary(manifest: schemas.Manifest | None, key: str) -> str:
    if manifest is None:
        return "Complete."
    if key == "render":
        return f"{manifest.preflight.page_count} pages rendered."
    if key == "page_reader":
        return f"{manifest.preflight.page_count} slides read."
    if key == "outline":
        return "Topics grouped."
    if key == "research":
        image = _path_stat(manifest, schemas.PathKind.image)
        text = _path_stat(manifest, schemas.PathKind.text)
        return f"{image.research_lookups + text.research_lookups} lookups."
    if key == "review":
        return "Review written."
    if key == "quiz":
        return f"{manifest.quiz_questions} questions."
    return "Complete."


def _stage_logs(run_dir: Path, manifest: schemas.Manifest | None, key: str) -> list[str]:
    if manifest is None:
        return []
    if key == "render":
        return [
            f"preflight: image_only={manifest.preflight.image_only}",
            f"superseded frames: {manifest.preflight.superseded_count}",
        ]
    if key == "page_reader":
        return [f"degraded reads: {len(degraded_reads(run_dir))}"]
    if key == "research":
        image = _path_stat(manifest, schemas.PathKind.image)
        text = _path_stat(manifest, schemas.PathKind.text)
        return [f"cache hits: {image.research_cache_hits + text.research_cache_hits}"]
    return []
