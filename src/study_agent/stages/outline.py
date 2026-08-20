"""Outline stage: topic partition, bridge candidates, and question budget."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .. import config, llm, paths
from ..prompts import outline as outline_prompts
from ..schemas import (
    BridgeConfirmationDraft,
    BridgeDraft,
    BridgedFact,
    GroupingDraft,
    Manifest,
    Outline,
    OutlineTopic,
    PageRole,
    PathKind,
    SlideNote,
    SkippedSlide,
    StageUsage,
    TopicAssignmentDraft,
)


BRIDGED_FACT_BUDGET_TOPIC = "bridged_fact"


@dataclass(frozen=True)
class BridgeCandidate:
    index: int
    slides: tuple[int, int]
    signal: str


class Outliner(Protocol):
    def group(
        self, notes: list[SlideNote], existing_topics: list[str]
    ) -> GroupingDraft:
        """Group covered slide notes into topics."""

    def confirm_bridges(
        self, notes_by_slide: dict[int, SlideNote], candidates: list[BridgeCandidate]
    ) -> BridgeDraft:
        """Confirm or reject code-proposed bridge candidates."""

    def repair_grouping(
        self,
        notes: list[SlideNote],
        existing_topics: list[str],
        grouping: GroupingDraft,
        violations: list[str],
    ) -> GroupingDraft:
        """Repair a grouping contract violation once."""


class AnthropicOutliner:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or llm.create_client()
        self.usage = StageUsage(stage="outline")

    def group(
        self, notes: list[SlideNote], existing_topics: list[str]
    ) -> GroupingDraft:
        result = llm.structured_call(
            self.client,
            response_model=GroupingDraft,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": outline_prompts.GROUP_NOTES},
                        {"type": "text", "text": str(_compact_notes(notes))},
                        {"type": "text", "text": str(existing_topics)},
                    ],
                }
            ],
            max_tokens=config.MAX_TOKENS_OUTLINE,
            effort=config.EFFORT_OUTLINE,
            stage="outline",
        )
        self.usage = _add_usage(self.usage, result.usage)
        return result.output

    def confirm_bridges(
        self, notes_by_slide: dict[int, SlideNote], candidates: list[BridgeCandidate]
    ) -> BridgeDraft:
        payload = [
            {
                "index": candidate.index,
                "slides": candidate.slides,
                "signal": candidate.signal,
                "notes": [notes_by_slide[slide].model_dump() for slide in candidate.slides],
            }
            for candidate in candidates
        ]
        result = llm.structured_call(
            self.client,
            response_model=BridgeDraft,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": outline_prompts.CONFIRM_BRIDGES,
                        },
                        {"type": "text", "text": str(payload)},
                    ],
                }
            ],
            max_tokens=config.MAX_TOKENS_OUTLINE,
            effort=config.EFFORT_OUTLINE,
            stage="outline",
        )
        self.usage = _add_usage(self.usage, result.usage)
        return result.output

    def repair_grouping(
        self,
        notes: list[SlideNote],
        existing_topics: list[str],
        grouping: GroupingDraft,
        violations: list[str],
    ) -> GroupingDraft:
        result = llm.structured_call(
            self.client,
            response_model=GroupingDraft,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": outline_prompts.REPAIR_GROUPING},
                        {"type": "text", "text": str(_compact_notes(notes))},
                        {"type": "text", "text": str(existing_topics)},
                        {"type": "text", "text": grouping.model_dump_json()},
                        {"type": "text", "text": str(violations)},
                    ],
                }
            ],
            max_tokens=config.MAX_TOKENS_OUTLINE,
            effort=config.EFFORT_OUTLINE,
            stage="outline",
        )
        self.usage = _add_usage(self.usage, result.usage)
        return result.output


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


def _compact_notes(notes: list[SlideNote]) -> list[dict[str, Any]]:
    return [
        {
            "slide_number": note.slide_number,
            "page_role": note.page_role.value,
            "title": note.title,
            "concepts": [concept.model_dump() for concept in note.concepts],
            "visuals": [
                {"kind": visual.kind.value, "assertion": visual.assertion}
                for visual in note.visuals
            ],
        }
        for note in notes
    ]


def propose_bridge_candidates(
    notes: list[SlideNote], cap: int = config.CANDIDATE_CAP
) -> list[BridgeCandidate]:
    """Propose bridge candidates from ADR 0007's three code-side signals."""

    by_slide = {note.slide_number: note for note in notes}
    pairs: list[tuple[tuple[int, int], str]] = []

    for note in notes:
        for visual in note.visuals:
            for target in visual.relates_to_slides:
                first_slide, second_slide = sorted((note.slide_number, target))
                pair = (first_slide, second_slide)
                if pair[0] != pair[1] and pair[0] in by_slide and pair[1] in by_slide:
                    pairs.append((pair, "relates_to_slides"))

    ordered = sorted(notes, key=lambda note: note.slide_number)
    for first, second in zip(ordered, ordered[1:]):
        if second.slide_number != first.slide_number + 1:
            continue
        if second.title is None or second.title == first.title:
            pairs.append(((first.slide_number, second.slide_number), "adjacent_title"))
        first_concepts = {concept.name for concept in first.concepts}
        second_concepts = {concept.name for concept in second.concepts}
        if first_concepts & second_concepts:
            pairs.append(((first.slide_number, second.slide_number), "shared_concept"))

    candidates: list[BridgeCandidate] = []
    seen: set[tuple[tuple[int, int], str]] = set()
    for pair, signal in pairs:
        key = (pair, signal)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            BridgeCandidate(index=len(candidates), slides=pair, signal=signal)
        )
        if len(candidates) >= cap:
            break
    return candidates


def _covered_notes(notes: list[SlideNote], superseded: set[int]) -> list[SlideNote]:
    return [
        note
        for note in notes
        if note.page_role == PageRole.content and note.slide_number not in superseded
    ]


def _exposed_notes(notes: list[SlideNote], superseded: set[int]) -> list[SlideNote]:
    return [note for note in notes if note.slide_number not in superseded]


def _skipped(notes: list[SlideNote]) -> list[SkippedSlide]:
    return [
        SkippedSlide(slide_number=note.slide_number, page_role=note.page_role)
        for note in notes
        if note.page_role != PageRole.content
    ]


def _violations(
    grouping: GroupingDraft, covered_slides: set[int], existing_topics: list[str]
) -> list[str]:
    claimed: dict[int, int] = {}
    problems: list[str] = []
    existing = set(existing_topics)
    for index, topic in enumerate(grouping.topics):
        if not topic.is_new and topic.name not in existing:
            problems.append(f"reused topic is not in profile: {topic.name}")
        if topic.is_new and not topic.created_reason:
            problems.append(f"new topic lacks created_reason: {topic.name}")
        for slide in topic.slides:
            if slide not in covered_slides:
                problems.append(f"slide {slide} is not covered")
                continue
            if slide in claimed:
                problems.append(f"slide {slide} is claimed twice")
            claimed[slide] = index
    missing = sorted(covered_slides - set(claimed))
    if missing:
        problems.append(f"unassigned slides: {missing}")
    if len(grouping.topics) > config.TOPIC_CAP:
        problems.append(f"topic cap exceeded: {len(grouping.topics)}")
    return problems


def _topics_from_grouping(
    grouping: GroupingDraft, covered_notes: list[SlideNote], existing_topics: list[str]
) -> tuple[list[OutlineTopic], list[int], bool]:
    covered_slides = {note.slide_number for note in covered_notes}
    degraded_slides = {
        note.slide_number for note in covered_notes if note.reader_note is not None
    }
    existing = set(existing_topics)
    assigned: set[int] = set()
    topics: list[OutlineTopic] = []
    ordered_drafts = sorted(
        grouping.topics,
        key=lambda topic: min(
            (slide for slide in topic.slides if slide in covered_slides),
            default=10**9,
        ),
    )
    for draft in ordered_drafts:
        slides: list[int] = []
        valid_topic = (draft.is_new and bool(draft.created_reason)) or (
            not draft.is_new and draft.name in existing
        )
        if valid_topic:
            for slide in draft.slides:
                if slide in covered_slides and slide not in assigned:
                    slides.append(slide)
                    assigned.add(slide)
        topics.append(
            OutlineTopic(
                name=draft.name,
                slides=slides,
                is_new=draft.is_new,
                created_reason=draft.created_reason,
                degraded_slides=[
                    slide for slide in slides if slide in degraded_slides
                ],
            )
        )
    unassigned = sorted(covered_slides - assigned)
    return topics, unassigned, len(grouping.topics) > config.TOPIC_CAP


def _bridged_facts_from(
    draft: BridgeDraft, candidates: list[BridgeCandidate]
) -> list[BridgedFact]:
    by_index = {candidate.index: candidate for candidate in candidates}
    facts: list[BridgedFact] = []
    for confirmation in draft.confirmations:
        candidate = by_index.get(confirmation.candidate_index)
        if (
            candidate is None
            or not confirmation.confirmed
            or confirmation.statement is None
        ):
            continue
        candidate_slides = set(candidate.slides)
        facts.append(
            BridgedFact(
                slides=list(candidate.slides),
                statement=confirmation.statement,
                from_visuals=[
                    item
                    for item in confirmation.from_visuals
                    if item[0] in candidate_slides
                ],
                candidate_signal=candidate.signal,
            )
        )
    return facts


def allocate_question_budget(
    topics: list[OutlineTopic],
    *,
    has_bridged_facts: bool,
    total_questions: int = config.QUIZ_QUESTIONS,
    max_per_topic: int = config.MAX_QUESTIONS_PER_TOPIC,
) -> tuple[list[tuple[str, int]], list[str]]:
    """Allocate ADR 0005's fixed quiz budget without a model call."""

    remaining = total_questions - (1 if has_bridged_facts else 0)
    budget: list[tuple[str, int]] = []
    if has_bridged_facts:
        budget.append((BRIDGED_FACT_BUDGET_TOPIC, 1))
    if not topics:
        return budget, []

    total_slides = sum(len(topic.slides) for topic in topics)
    effective_max = max_per_topic
    if len(topics) * effective_max < remaining:
        effective_max = remaining
    raw: list[tuple[OutlineTopic, int, float]] = []
    allocated = 0
    for topic in topics:
        share = (len(topic.slides) / total_slides * remaining) if total_slides else 0
        base = min(int(share), effective_max)
        raw.append((topic, base, share - int(share)))
        allocated += base

    while allocated < remaining:
        changed = False
        for index, (topic, count, remainder) in sorted(
            enumerate(raw), key=lambda item: item[1][2], reverse=True
        ):
            if count >= effective_max:
                continue
            raw[index] = (topic, count + 1, remainder)
            allocated += 1
            changed = True
            if allocated == remaining:
                break
        if not changed:
            break

    untested: list[str] = []
    for topic, count, _ in raw:
        budget.append((topic.name, count))
        if count == 0:
            untested.append(topic.name)
    return budget, untested


def build_outline(
    *,
    deck_slug: str,
    path_kind: PathKind,
    notes: list[SlideNote],
    existing_topics: list[str],
    superseded: list[int],
    outliner: Outliner,
) -> Outline:
    superseded_set = set(superseded)
    covered = _covered_notes(notes, superseded_set)
    exposed = _exposed_notes(notes, superseded_set)
    covered_slides = {note.slide_number for note in covered}

    grouping = outliner.group(exposed, existing_topics)
    violations = _violations(grouping, covered_slides, existing_topics)
    repair_attempted = False
    if violations:
        repair_attempted = True
        repaired = outliner.repair_grouping(
            exposed, existing_topics, grouping, violations
        )
        if not _violations(repaired, covered_slides, existing_topics):
            grouping = repaired

    topics, unassigned, topic_cap_exceeded = _topics_from_grouping(
        grouping, covered, existing_topics
    )
    candidates = propose_bridge_candidates(covered, cap=config.CANDIDATE_CAP)
    notes_by_slide = {note.slide_number: note for note in covered}
    bridge_draft = outliner.confirm_bridges(notes_by_slide, candidates)
    bridged_facts = _bridged_facts_from(bridge_draft, candidates)
    question_budget, untested_topics = allocate_question_budget(
        topics, has_bridged_facts=bool(bridged_facts)
    )

    return Outline(
        deck_slug=deck_slug,
        path=path_kind,
        topics=topics,
        skipped=_skipped(notes),
        superseded=superseded,
        unassigned=unassigned,
        bridged_facts=bridged_facts,
        candidates_proposed=len(candidates),
        candidate_cap=config.CANDIDATE_CAP,
        topic_cap_exceeded=topic_cap_exceeded,
        question_budget=question_budget,
        untested_topics=untested_topics,
        repair_attempted=repair_attempted,
    )


def _load_notes(run_dir: Path, path_kind: PathKind) -> list[SlideNote]:
    notes: list[SlideNote] = []
    for target in sorted(paths.notes_dir(run_dir, path_kind.value).glob("*.json")):
        payload = paths.read_json(target)
        if payload is not None:
            notes.append(SlideNote.model_validate(payload))
    return notes


def _load_existing_topic_names(layout: paths.Layout, subject_slug: str) -> list[str]:
    payload = paths.read_json(layout.profile_file(subject_slug))
    if payload is None:
        return []
    from ..schemas import Profile

    profile = Profile.model_validate(payload)
    return [topic.name for topic in profile.topics]


def _mark_outline_complete(run_dir: Path, usage: StageUsage) -> None:
    manifest_payload = paths.read_json(paths.manifest_file(run_dir))
    if manifest_payload is None:
        return
    manifest = Manifest.model_validate(manifest_payload)
    updated_paths = []
    for stat in manifest.paths:
        stages = list(stat.completed_stages)
        if "outline" not in stages:
            stages.append("outline")
        updated_paths.append(stat.model_copy(update={"completed_stages": stages}))
    stage_usage = list(manifest.stage_usage)
    if usage.calls:
        stage_usage.append(usage)
    paths.write_model(
        paths.manifest_file(run_dir),
        manifest.model_copy(
            update={
                "paths": updated_paths,
                "stage_usage": stage_usage,
                "total_cost_usd": manifest.total_cost_usd + usage.cost_usd,
                "topic_cap_exceeded": manifest.topic_cap_exceeded
                or any(
                    Outline.model_validate(
                        paths.read_json(paths.outline_file(run_dir, path_kind.value))
                    ).topic_cap_exceeded
                    for path_kind in (PathKind.image, PathKind.text)
                    if paths.read_json(paths.outline_file(run_dir, path_kind.value))
                    is not None
                ),
            }
        ),
    )


def outline_run(
    run_dir: Path,
    *,
    deck_slug: str,
    superseded: list[int],
    subject_slug: str | None = None,
    layout: paths.Layout | None = None,
    existing_topics: list[str] | None = None,
    outliner: Outliner | None = None,
) -> None:
    outliner = outliner or AnthropicOutliner()
    if existing_topics is not None:
        topics = existing_topics
    elif subject_slug is not None:
        topics = _load_existing_topic_names(layout or paths.Layout(), subject_slug)
    else:
        topics = []
    for path_kind in (PathKind.image, PathKind.text):
        result = build_outline(
            deck_slug=deck_slug,
            path_kind=path_kind,
            notes=_load_notes(Path(run_dir), path_kind),
            existing_topics=topics,
            superseded=superseded,
            outliner=outliner,
        )
        paths.write_model(paths.outline_file(Path(run_dir), path_kind.value), result)
    usage = getattr(outliner, "usage", StageUsage(stage="outline"))
    _mark_outline_complete(Path(run_dir), usage)
