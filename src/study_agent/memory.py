"""Stage 8: the subject registry, the topic profile, and derived performance.

Three rules from ADR 0003 and ADR 0004 shape everything here, and each one is
enforced in code rather than left to callers:

* `memory/subjects.json` is the authority on which subjects exist. A directory
  under `memory/` with no registry entry is an error, not a subject, so a
  half-deleted tree cannot quietly come back to life.
* A subject is created only by `create_subject`. Nothing else touches the
  registry, so no run can conjure a subject out of a name it was handed.
* Performance is derived from the attempts directory on every read and is never
  stored. `profile.json` holds exposure and nothing about correctness.

Contributions live here because they rebuild the subject profile. Retake
generation lives in `stages/retake.py`; this module owns the registry, profile,
contributions, and attempts.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from . import config, paths
from .paths import Layout
from .schemas import (
    Attempt,
    DeckContribution,
    Manifest,
    Outline,
    PathKind,
    Profile,
    SubjectEntry,
    SubjectsRegistry,
    TopicContribution,
    TopicRecord,
    TopicPerformance,
)


_ALPHANUMERIC = re.compile(r"[a-z0-9]", re.IGNORECASE)


class MemoryUnreadable(RuntimeError):
    """A file that has to exist and parse does not, or does not."""


class UnknownSubject(RuntimeError):
    """A subject slug with no entry in `memory/subjects.json`."""


class SubjectExists(RuntimeError):
    """`create_subject` on a slug the registry already holds."""


class SchemaVersionMismatch(RuntimeError):
    """A stored `schema_version` this build does not read. Never migrated."""


# --- The registry -----------------------------------------------------------


def load_registry(layout: Layout | None = None) -> SubjectsRegistry:
    """`memory/subjects.json`. Missing reads as empty; corrupt is a refusal.

    The two are not the same thing. No file at all is the ordinary state of a
    fresh checkout, since `memory/` is gitignored. A file that does not parse
    means the authority on which subjects exist has been damaged, and reading
    that as "no subjects" would invite `create_subject` to overwrite it.
    """

    layout = layout or Layout()
    target = layout.subjects_file()
    if not target.is_file():
        return SubjectsRegistry()
    payload = paths.read_json(target)
    if payload is None:
        raise MemoryUnreadable(f"{target} exists but does not parse as JSON")
    try:
        return SubjectsRegistry.model_validate(payload)
    except ValidationError as error:
        raise MemoryUnreadable(f"{target} is not a subjects registry: {error}") from error


def list_subjects(layout: Layout | None = None) -> list[SubjectEntry]:
    """Every registered subject, in creation order. This fills the dropdown."""

    return load_registry(layout).subjects


def find_subject(subject_slug: str, layout: Layout | None = None) -> SubjectEntry | None:
    for entry in list_subjects(layout):
        if entry.slug == subject_slug:
            return entry
    return None


def require_subject(subject_slug: str, layout: Layout | None = None) -> SubjectEntry:
    """The registry entry, or an error. The gate in front of every read below.

    Deliberately does not look at the filesystem: a subject directory is not
    evidence that a subject exists.
    """

    entry = find_subject(subject_slug, layout)
    if entry is None:
        raise UnknownSubject(
            f"no subject {subject_slug!r} in the registry; "
            "create it explicitly before running a deck against it"
        )
    return entry


def create_subject(display_name: str, layout: Layout | None = None) -> SubjectEntry:
    """Register a subject and write its empty profile. The only writer here.

    Both files are written, because a registry entry whose profile is missing
    would fail every subsequent read, and ADR 0003 wants a new subject usable
    immediately rather than after the first run.
    """

    layout = layout or Layout()
    name = display_name.strip()
    if not _ALPHANUMERIC.search(name):
        raise ValueError(f"{display_name!r} does not name a subject")
    slug = paths.slugify(name)

    registry = load_registry(layout)
    if any(entry.slug == slug for entry in registry.subjects):
        raise SubjectExists(f"subject {slug!r} already exists")

    # An unregistered subject directory on disk is the half-deleted tree the
    # module docstring names: the registry is gone but the subject's
    # accumulated topics, attempts, retakes, and contributions are not. Writing
    # over it would destroy every deck that subject has ever seen, silently, so
    # this refuses and leaves the choice to a human.
    #
    # The directory is the test, not `profile.json`. A tree whose profile is
    # the one file that did not survive is in exactly the same state, and
    # adopting its attempts into a freshly created subject would carry a
    # stranger's history into the retake weighting.
    subject = layout.subject_dir(slug)
    if subject.exists():
        raise MemoryUnreadable(
            f"{subject} already exists but {slug!r} is not in the registry. "
            "Move or delete it rather than losing what it holds."
        )
    profile = layout.profile_file(slug)

    entry = SubjectEntry(slug=slug, display_name=name, created_at=paths.utc_iso())
    registry.subjects.append(entry)
    # The registry goes first. A failure between the two writes then leaves a
    # subject whose profile is missing, which `load_profile` reports plainly,
    # rather than an orphan directory that blocks its own slug forever.
    paths.write_model(layout.subjects_file(), registry)
    paths.write_model(profile, _empty_profile(slug))
    return entry


def _empty_profile(subject_slug: str) -> Profile:
    return Profile(schema_version=config.SCHEMA_VERSION, subject_slug=subject_slug, topics=[])


# --- The profile ------------------------------------------------------------


def load_profile(subject_slug: str, layout: Layout | None = None) -> Profile:
    """The subject's topic list. Refuses on a `schema_version` it cannot read."""

    layout = layout or Layout()
    require_subject(subject_slug, layout)

    target = layout.profile_file(subject_slug)
    payload = paths.read_json(target)
    if payload is None:
        raise MemoryUnreadable(
            f"{subject_slug!r} is registered but {target} is missing or does not parse"
        )

    stored_version = payload.get("schema_version") if isinstance(payload, dict) else None
    if stored_version != config.SCHEMA_VERSION:
        raise SchemaVersionMismatch(
            f"{target} is schema_version {stored_version!r}, this build reads "
            f"{config.SCHEMA_VERSION}. Nothing is migrated; move or delete the file."
        )

    try:
        return Profile.model_validate(payload)
    except ValidationError as error:
        raise MemoryUnreadable(f"{target} is not a profile: {error}") from error


def save_profile(profile: Profile, layout: Layout | None = None) -> None:
    layout = layout or Layout()
    require_subject(profile.subject_slug, layout)
    paths.write_model(layout.profile_file(profile.subject_slug), profile)


def topic_exposure(subject_slug: str, layout: Layout | None = None) -> dict[str, int]:
    """Topic name to slides seen. The other axis from performance, never mixed."""

    return {record.name: record.exposure for record in load_profile(subject_slug, layout).topics}


# --- Deck contributions ----------------------------------------------------


def _load_contributions(subject_slug: str, layout: Layout) -> list[DeckContribution]:
    require_subject(subject_slug, layout)
    directory = layout.contributions_dir(subject_slug)
    if not directory.is_dir():
        return []
    contributions: list[DeckContribution] = []
    for target in sorted(directory.glob("*.json"), key=lambda path: path.name):
        payload = paths.read_json(target)
        if payload is None:
            raise MemoryUnreadable(f"{target} exists but does not parse as JSON")
        try:
            contributions.append(DeckContribution.model_validate(payload))
        except ValidationError as error:
            raise MemoryUnreadable(f"{target} is not a deck contribution: {error}") from error
    return contributions


def _rebuild_profile_from_contributions(
    subject_slug: str, layout: Layout
) -> Profile:
    """Derive topic exposure and citations from the contribution files."""

    topics: dict[str, TopicRecord] = {}
    for contribution in sorted(
        _load_contributions(subject_slug, layout),
        key=lambda item: (item.contributed_at, item.deck_slug),
    ):
        for item in contribution.topics:
            record = topics.get(item.name)
            if record is None:
                record = TopicRecord(
                    name=item.name,
                    first_seen_deck=contribution.deck_slug,
                    created_reason=item.created_reason if item.is_new else None,
                )
                topics[item.name] = record
            if contribution.deck_slug not in record.decks:
                record.decks.append(contribution.deck_slug)
            record.slide_citations.extend(
                (contribution.deck_slug, slide) for slide in item.slides
            )
            record.exposure += len(item.slides)

    profile = Profile(
        schema_version=config.SCHEMA_VERSION,
        subject_slug=subject_slug,
        topics=list(topics.values()),
    )
    save_profile(profile, layout)
    return profile


def contribute_run(
    run_dir: Path, layout: Layout | None = None
) -> DeckContribution:
    """Record the image-path outline as the subject's replaceable contribution.

    The contribution is keyed by the manifest's deck slug. Re-running the same
    deck therefore replaces one file, while the profile is rebuilt from every
    contribution so exposure cannot accumulate twice.
    """

    layout = layout or Layout()
    run_dir = Path(run_dir)
    manifest_payload = paths.read_json(paths.manifest_file(run_dir))
    outline_payload = paths.read_json(paths.outline_file(run_dir, "image"))
    if manifest_payload is None or outline_payload is None:
        raise MemoryUnreadable(f"{run_dir} is missing its manifest or image outline")
    try:
        manifest = Manifest.model_validate(manifest_payload)
        outline = Outline.model_validate(outline_payload)
    except ValidationError as error:
        raise MemoryUnreadable(f"{run_dir} has invalid contribution artifacts: {error}") from error
    if outline.path is not PathKind.image:
        raise MemoryUnreadable("only an image-path outline can contribute to memory")
    require_subject(manifest.subject_slug, layout)
    topics = [
        TopicContribution(
            name=topic.name,
            slides=topic.slides,
            is_new=topic.is_new,
            created_reason=topic.created_reason,
        )
        for topic in outline.topics
        if topic.slides
    ]
    contribution = DeckContribution(
        subject_slug=manifest.subject_slug,
        deck_slug=manifest.deck_slug,
        deck_sha256=manifest.deck_sha256,
        run_timestamp=manifest.run_timestamp,
        contributed_at=paths.utc_iso(),
        topics=topics,
    )
    paths.write_model(
        layout.contribution_file(manifest.subject_slug, manifest.deck_slug),
        contribution,
    )
    _rebuild_profile_from_contributions(manifest.subject_slug, layout)
    return contribution


# --- Attempts, and the performance derived from them ------------------------


@dataclass(frozen=True)
class AttemptsRead:
    """What one walk of the attempts directory found, skips included.

    The skips are carried rather than swallowed because every number derived
    from attempts is a count. An empty history and a history whose files all
    failed to parse both yield zero, and only the second one means the
    reported performance is wrong.
    """

    attempts: list[Attempt] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)


def read_attempts(subject_slug: str, layout: Layout | None = None) -> AttemptsRead:
    """Every attempt on record, oldest first, plus the files that would not read.

    Attempt ids lead with a UTC timestamp, so filename order is time order. A
    file that does not parse or does not validate is skipped rather than
    failing the read: an attempt is one graded quiz, and losing the rest of a
    subject's history to one damaged file would be the worse outcome. The
    skipped filenames come back so a caller can say so out loud.
    """

    layout = layout or Layout()
    require_subject(subject_slug, layout)

    directory = layout.attempts_dir(subject_slug)
    if not directory.is_dir():
        return AttemptsRead()

    attempts: list[Attempt] = []
    unreadable: list[str] = []
    for target in sorted(directory.glob("*.json"), key=lambda p: p.name):
        attempt = _read_attempt(target)
        if attempt is None:
            unreadable.append(target.name)
        else:
            attempts.append(attempt)
    return AttemptsRead(attempts=attempts, unreadable=unreadable)


def load_attempts(subject_slug: str, layout: Layout | None = None) -> list[Attempt]:
    """The attempts alone, for a caller with nowhere to report skips."""

    return read_attempts(subject_slug, layout).attempts


def _read_attempt(target: Path) -> Attempt | None:
    payload = paths.read_json(target)
    if payload is None:
        return None
    try:
        return Attempt.model_validate(payload)
    except ValidationError:
        return None


def topic_performance(
    subject_slug: str, layout: Layout | None = None
) -> list[TopicPerformance]:
    """The (correct, seen) pair per topic, sorted by topic name.

    Below `MIN_SIGHTINGS_FOR_PERFORMANCE` sightings the pair still comes back,
    with `insufficient_evidence` set, so a caller reports "not enough evidence"
    rather than a 0/1 that reads as a score. A topic with no responses at all
    does not appear here; exposure is the profile's business.
    """

    seen: Counter[str] = Counter()
    correct: Counter[str] = Counter()
    for attempt in load_attempts(subject_slug, layout):
        for response in attempt.responses:
            if response.chosen_index < 0:
                continue
            seen[response.topic] += 1
            if response.correct:
                correct[response.topic] += 1

    return [
        TopicPerformance(
            topic=topic,
            correct=correct[topic],
            seen=seen[topic],
            insufficient_evidence=seen[topic] < config.MIN_SIGHTINGS_FOR_PERFORMANCE,
        )
        for topic in sorted(seen)
    ]


def has_attempts(subject_slug: str, layout: Layout | None = None) -> bool:
    """Whether anything has been graded. The retake refuses when this is False."""

    return bool(load_attempts(subject_slug, layout))
