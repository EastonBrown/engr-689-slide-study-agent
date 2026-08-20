"""Disk-backed data for the Streamlit interface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from study_agent import config, paths, schemas

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
