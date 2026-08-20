"""Subject memory, attempts, and attempt-derived performance."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable

from study_agent import config, paths, schemas


def append_attempt(layout: paths.Layout, attempt: schemas.Attempt) -> Path:
    """Write one append-only attempt file and refuse accidental replacement."""

    target = layout.attempt_file(attempt.subject_slug, attempt.attempt_id)
    if target.exists():
        raise FileExistsError(f"Attempt already exists: {target}")
    paths.write_model(target, attempt)
    return target


def read_attempts(layout: paths.Layout, subject_slug: str) -> Iterable[schemas.Attempt]:
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
