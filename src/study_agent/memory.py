"""Subject memory, attempts, and attempt-derived performance."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from study_agent import config, paths, schemas
from study_agent.stages import quiz as quiz_stage


@dataclass(frozen=True)
class RetakeRefusal:
    message: str


class SubjectRegistryError(ValueError):
    """The subject is not present in memory/subjects.json."""


class RetakeSourceMissing(ValueError):
    """A retake target cannot be resolved to latest image notes."""


def append_attempt(layout: paths.Layout, attempt: schemas.Attempt) -> Path:
    """Write one append-only attempt file and refuse accidental replacement."""

    target = layout.attempt_file(attempt.subject_slug, attempt.attempt_id)
    if target.exists():
        raise FileExistsError(f"Attempt already exists: {target}")
    paths.write_model(target, attempt)
    return target


def read_attempts(layout: paths.Layout, subject_slug: str) -> Iterable[schemas.Attempt]:
    _require_subject(layout, subject_slug)
    attempts_dir = layout.attempts_dir(subject_slug)
    if not attempts_dir.is_dir():
        return
    for attempt_file in sorted(attempts_dir.glob("*.json")):
        payload = paths.read_json(attempt_file)
        if payload is None:
            continue
        yield schemas.Attempt.model_validate(payload)


def derive_topic_performance(layout: paths.Layout, subject_slug: str) -> list[schemas.TopicPerformance]:
    """Read append-only attempts and derive lifetime topic performance."""

    aggregate: dict[str, Counter[str]] = {}
    for attempt in read_attempts(layout, subject_slug):
        for response in attempt.responses:
            counts = aggregate.setdefault(response.topic, Counter())
            counts["seen"] += 1
            if response.correct:
                counts["correct"] += 1

    return [
        schemas.TopicPerformance(
            topic=topic,
            correct=counts["correct"],
            seen=counts["seen"],
            insufficient_evidence=counts["seen"] < config.MIN_SIGHTINGS_FOR_PERFORMANCE,
        )
        for topic, counts in sorted(aggregate.items())
    ]


def write_deck_contribution(
    run_dir: Path,
    *,
    layout: paths.Layout | None = None,
    contributed_at: str | None = None,
) -> schemas.DeckContribution:
    """Replace one deck's image-path contribution in subject memory."""

    manifest_payload = paths.read_json(paths.manifest_file(run_dir))
    outline_payload = paths.read_json(paths.outline_file(run_dir, schemas.PathKind.image.value))
    if manifest_payload is None:
        raise ValueError(f"Run has no readable manifest: {run_dir}")
    if outline_payload is None:
        raise ValueError(f"Run has no readable image outline: {run_dir}")
    manifest = schemas.Manifest.model_validate(manifest_payload)
    outline = schemas.Outline.model_validate(outline_payload)
    root_layout = layout or paths.Layout(paths.repo_root())
    _require_subject(root_layout, manifest.subject_slug)
    contribution = schemas.DeckContribution(
        subject_slug=manifest.subject_slug,
        deck_slug=manifest.deck_slug,
        deck_sha256=manifest.deck_sha256,
        run_timestamp=manifest.run_timestamp,
        contributed_at=contributed_at or _utc_now(),
        topics=[
            schemas.TopicContribution(
                name=topic.name,
                slides=topic.slides,
                is_new=topic.is_new,
                created_reason=topic.created_reason,
            )
            for topic in outline.topics
        ],
    )
    target = root_layout.contribution_file(manifest.subject_slug, manifest.deck_slug)
    for prior in _contribution_files_for_hash(root_layout, manifest.subject_slug, manifest.deck_sha256):
        if prior != target:
            prior.unlink()
    paths.write_model(target, contribution)
    paths.write_model(root_layout.profile_file(manifest.subject_slug), derive_profile(root_layout, manifest.subject_slug))
    return contribution


def derive_profile(layout: paths.Layout, subject_slug: str) -> schemas.Profile:
    """Build the subject profile's exposure totals from contribution files."""

    _require_subject(layout, subject_slug)
    records: dict[str, schemas.TopicRecord] = {}
    for contribution in read_contributions(layout, subject_slug):
        for topic in contribution.topics:
            record = records.get(topic.name)
            if record is None:
                record = schemas.TopicRecord(
                    name=topic.name,
                    first_seen_deck=contribution.deck_slug,
                    decks=[],
                    slide_citations=[],
                    exposure=0,
                    created_reason=topic.created_reason,
                )
                records[topic.name] = record
            if contribution.deck_slug not in record.decks:
                record.decks.append(contribution.deck_slug)
            record.slide_citations.extend((contribution.deck_slug, slide) for slide in topic.slides)
            record.exposure += len(topic.slides)

    return schemas.Profile(
        schema_version=config.SCHEMA_VERSION,
        subject_slug=subject_slug,
        topics=list(records.values()),
    )


def read_contributions(layout: paths.Layout, subject_slug: str) -> Iterable[schemas.DeckContribution]:
    _require_subject(layout, subject_slug)
    contributions_dir = layout.contributions_dir(subject_slug)
    if not contributions_dir.is_dir():
        return
    contributions: list[schemas.DeckContribution] = []
    for contribution_file in sorted(contributions_dir.glob("*.json")):
        payload = paths.read_json(contribution_file)
        if payload is None:
            continue
        contributions.append(schemas.DeckContribution.model_validate(payload))
    for contribution in sorted(
        contributions,
        key=lambda item: (item.contributed_at, item.run_timestamp, item.deck_slug),
    ):
        yield contribution


def generate_retake(
    layout: paths.Layout,
    subject_slug: str,
    *,
    generator: quiz_stage.QuizGenerator | None = None,
    retake_id: str | None = None,
    generated_at: str | None = None,
) -> schemas.Quiz | RetakeRefusal:
    """Generate a memory-scoped retake from latest image notes."""

    attempts = list(read_attempts(layout, subject_slug))
    if not attempts:
        return RetakeRefusal("No attempts on record; cannot generate a retake.")
    generator = generator or quiz_stage.AnthropicQuizGenerator()
    retake_id = retake_id or paths.new_attempt_id()
    generated_at = generated_at or _utc_now()
    profile = derive_profile(layout, subject_slug)
    budget = _retake_budget(profile, derive_topic_performance(layout, subject_slug))
    if not budget:
        return RetakeRefusal("No profile topics are available for a retake.")

    try:
        notes = _load_retake_notes(layout, subject_slug, profile, [topic for topic, _ in budget])
    except RetakeSourceMissing as error:
        return RetakeRefusal(str(error))
    outline = _retake_outline(subject_slug, profile, budget)
    result = generator.generate(
        quiz_stage.QuizRequest(
            outline=outline,
            notes=notes,
            target_count=config.QUIZ_QUESTIONS,
        )
    )
    accepted, dropped = quiz_stage.filter_questions(result.draft.questions, outline=outline, notes=notes)
    quiz = quiz_stage.materialize_quiz(
        quiz_id=retake_id,
        subject_slug=subject_slug,
        deck_slug=None,
        run_timestamp=None,
        kind=schemas.AttemptKind.retake,
        generated_at=generated_at,
        covered_slide_count=len({note.slide_number for note in notes}),
        question_id_prefix=retake_id,
        questions=accepted[: config.QUIZ_QUESTIONS],
        dropped=dropped + max(0, len(accepted) - config.QUIZ_QUESTIONS),
    )
    paths.write_model(layout.retake_file(subject_slug, retake_id), quiz)
    return quiz


def _retake_budget(
    profile: schemas.Profile,
    performance: list[schemas.TopicPerformance],
) -> list[tuple[str, int]]:
    performance_by_topic = {item.topic: item for item in performance}
    enough = [
        item
        for item in performance
        if not item.insufficient_evidence and item.seen >= config.MIN_SIGHTINGS_FOR_PERFORMANCE
    ]
    enough.sort(key=lambda item: (item.correct / item.seen, item.topic))
    selected: list[tuple[str, int]] = [
        (item.topic, config.RETAKE_QUESTIONS_PER_WEAK_TOPIC)
        for item in enough[: config.RETAKE_WEAK_TOPICS]
    ]
    selected_names = {topic for topic, _ in selected}
    remaining = config.QUIZ_QUESTIONS - sum(count for _, count in selected)
    undertested = [
        topic.name
        for topic in profile.topics
        if topic.name not in selected_names
        and performance_by_topic.get(topic.name, _empty_performance(topic.name)).insufficient_evidence
    ]
    for index, topic_name in enumerate(undertested):
        if remaining <= 0:
            break
        topics_left = len(undertested) - index
        count = max(config.RETAKE_QUESTIONS_PER_WEAK_TOPIC, remaining // topics_left)
        if remaining % topics_left:
            count += 1
        count = min(count, remaining)
        selected.append((topic_name, count))
        remaining -= count
    return selected


def _empty_performance(topic: str) -> schemas.TopicPerformance:
    return schemas.TopicPerformance(topic=topic, correct=0, seen=0, insufficient_evidence=True)


def _load_retake_notes(
    layout: paths.Layout,
    subject_slug: str,
    profile: schemas.Profile,
    target_topics: list[str],
) -> list[schemas.SlideNote]:
    target_set = set(target_topics)
    notes: list[schemas.SlideNote] = []
    seen: set[tuple[str, int]] = set()
    for topic in profile.topics:
        if topic.name not in target_set:
            continue
        for deck_slug, slide_number in topic.slide_citations:
            key = (deck_slug, slide_number)
            if key in seen:
                continue
            seen.add(key)
            run_dir = layout.latest_run_dir(subject_slug, deck_slug)
            if run_dir is None:
                raise RetakeSourceMissing(f"Missing latest run for deck {deck_slug}.")
            payload = paths.read_json(paths.page_note(run_dir, schemas.PathKind.image.value, slide_number))
            if payload is None:
                raise RetakeSourceMissing(
                    f"Missing latest image note for deck {deck_slug} slide {slide_number}."
                )
            notes.append(schemas.SlideNote.model_validate(payload))
    return notes


def _retake_outline(
    subject_slug: str,
    profile: schemas.Profile,
    budget: list[tuple[str, int]],
) -> schemas.Outline:
    by_name = {topic.name: topic for topic in profile.topics}
    return schemas.Outline(
        deck_slug=subject_slug,
        path=schemas.PathKind.image,
        topics=[
            schemas.OutlineTopic(
                name=topic_name,
                slides=[slide for _, slide in by_name[topic_name].slide_citations],
                is_new=False,
                created_reason=None,
            )
            for topic_name, _ in budget
            if topic_name in by_name
        ],
        skipped=[],
        superseded=[],
        unassigned=[],
        bridged_facts=[],
        candidates_proposed=0,
        candidate_cap=config.CANDIDATE_CAP,
        topic_cap_exceeded=False,
        question_budget=budget,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_subject(layout: paths.Layout, subject_slug: str) -> None:
    payload = paths.read_json(layout.subjects_file())
    if payload is None:
        raise SubjectRegistryError(f"memory/subjects.json is required before reading subject {subject_slug}.")
    registry = schemas.SubjectsRegistry.model_validate(payload)
    if all(subject.slug != subject_slug for subject in registry.subjects):
        raise SubjectRegistryError(f"Subject {subject_slug} is not registered in memory/subjects.json.")


def _contribution_files_for_hash(
    layout: paths.Layout,
    subject_slug: str,
    deck_sha256: str,
) -> list[Path]:
    matches: list[Path] = []
    for contribution_file in sorted(layout.contributions_dir(subject_slug).glob("*.json")):
        payload = paths.read_json(contribution_file)
        if payload is None:
            continue
        contribution = schemas.DeckContribution.model_validate(payload)
        if contribution.deck_sha256 == deck_sha256:
            matches.append(contribution_file)
    return matches
