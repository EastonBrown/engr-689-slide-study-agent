"""Generate subject-level retake quizzes from stored image-path notes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

from .. import config, llm, memory, paths
from ..prompts import quiz as quiz_prompts
from ..schemas import (
    AttemptKind,
    Profile,
    Question,
    QuestionDraft,
    Quiz,
    QuizDraft,
    SlideNote,
    StageUsage,
)


class RetakeError(RuntimeError):
    """The subject does not have enough valid state to generate a retake."""


class RetakeGenerator(Protocol):
    usage: StageUsage

    def generate(self, context: str) -> QuizDraft:
        """Generate one batch of retake questions."""


class AnthropicRetakeGenerator:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or llm.create_client()
        self.usage = StageUsage(stage="retake")

    def generate(self, context: str) -> QuizDraft:
        result = llm.structured_call(
            self.client,
            response_model=QuizDraft,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": quiz_prompts.GENERATE_RETAKE},
                        {"type": "text", "text": context},
                    ],
                }
            ],
            max_tokens=config.MAX_TOKENS_QUIZ,
            effort=config.EFFORT_QUIZ,
            stage="retake",
        )
        self.usage = _add_usage(self.usage, result.usage)
        return result.output


def _add_usage(first: StageUsage, second: StageUsage) -> StageUsage:
    return StageUsage(
        stage="retake",
        calls=first.calls + second.calls,
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        cache_read_tokens=first.cache_read_tokens + second.cache_read_tokens,
        web_searches=first.web_searches + second.web_searches,
        cost_usd=first.cost_usd + second.cost_usd,
    )


def select_topics(profile: Profile, performance: list[Any]) -> list[tuple[str, int]]:
    """Return the retake's topic/question budget in deterministic order."""

    by_name = {item.topic: item for item in performance}
    weak = [
        topic
        for topic in profile.topics
        if by_name.get(topic.name) is not None
        and by_name[topic.name].seen >= config.MIN_SIGHTINGS_FOR_PERFORMANCE
    ]
    weak.sort(
        key=lambda topic: (
            by_name[topic.name].correct / by_name[topic.name].seen,
            topic.name,
        )
    )
    selected_weak = weak[: config.RETAKE_WEAK_TOPICS]
    budget: list[tuple[str, int]] = [
        (topic.name, config.RETAKE_QUESTIONS_PER_WEAK_TOPIC)
        for topic in selected_weak
    ]

    remaining = config.QUIZ_QUESTIONS - sum(count for _, count in budget)
    undertested = [
        topic
        for topic in profile.topics
        if by_name.get(topic.name) is None
        or by_name[topic.name].seen < config.MIN_SIGHTINGS_FOR_PERFORMANCE
    ]
    undertested.sort(key=lambda topic: (topic.exposure, topic.name))
    if remaining > 0 and undertested:
        # The profile is the only durable ordering available for exposure, so
        # distribute the fill pool round-robin across the oldest topics.
        for index in range(remaining):
            topic = undertested[index % len(undertested)].name
            for position, (name, count) in enumerate(budget):
                if name == topic:
                    budget[position] = (name, count + 1)
                    break
            else:
                budget.append((topic, 1))
    elif remaining > 0 and selected_weak:
        # A subject can have graded topics but no under-tested topics. Keep the
        # fixed ten-question format rather than silently emitting a short quiz.
        for index in range(remaining):
            position = index % len(budget)
            name, count = budget[position]
            budget[position] = (name, count + 1)
    return budget


def _load_notes_for_topics(
    subject_slug: str, profile: Profile, topics: set[str], layout: paths.Layout
) -> list[SlideNote]:
    wanted: dict[tuple[str, int], None] = {}
    for record in profile.topics:
        if record.name in topics:
            wanted.update({citation: None for citation in record.slide_citations})

    notes: list[SlideNote] = []
    for deck_slug, slide_number in sorted(wanted):
        run_dir = layout.latest_run_dir(subject_slug, deck_slug)
        if run_dir is None:
            raise RetakeError(
                f"no latest run is available for contributing deck {deck_slug!r}"
            )
        target = paths.page_note(run_dir, "image", slide_number)
        payload = paths.read_json(target)
        if payload is None:
            raise RetakeError(f"missing image note for {deck_slug} slide {slide_number}")
        notes.append(SlideNote.model_validate(payload))
    return notes


def _stored_question_stems(layout: paths.Layout, subject_slug: str) -> set[str]:
    stems: set[str] = set()
    subject_runs = layout.runs_dir() / subject_slug
    if subject_runs.is_dir():
        quiz_files = subject_runs.glob("*/**/quiz.json")
    else:
        quiz_files = iter(())
    for target in quiz_files:
        payload = paths.read_json(target)
        if isinstance(payload, dict):
            try:
                stems.update(question.stem for question in Quiz.model_validate(payload).questions)
            except Exception:
                continue
    retakes = layout.retakes_dir(subject_slug)
    if retakes.is_dir():
        for target in retakes.glob("*.json"):
            payload = paths.read_json(target)
            if isinstance(payload, dict):
                try:
                    stems.update(question.stem for question in Quiz.model_validate(payload).questions)
                except Exception:
                    continue
    return stems


def _context(
    budget: list[tuple[str, int]], notes: list[SlideNote], prior_stems: set[str]
) -> str:
    return (
        "RETAKE QUESTION BUDGET:\n"
        + repr(budget)
        + "\nSTORED IMAGE SLIDE NOTES:\n"
        + "\n".join(note.model_dump_json() for note in notes)
        + "\nQUESTIONS TO AVOID VERBATIM:\n"
        + "\n".join(sorted(prior_stems))
    )


_BANNED = ("all of the above", "none of the above")
_DATE = re.compile(r"\b(?:19|20)\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")


def _valid(draft: QuestionDraft, budget: dict[str, int], notes: dict[int, SlideNote], stems: set[str]) -> bool:
    if budget.get(draft.topic, 0) <= 0:
        return False
    if len(draft.options) != 4 or len(draft.distractor_rationale) != 4:
        return False
    if not 0 <= draft.correct_index < 4:
        return False
    if draft.distractor_rationale[draft.correct_index] is not None:
        return False
    if not draft.slide_citations or any(slide not in notes for slide in draft.slide_citations):
        return False
    text = " ".join([draft.stem, *draft.options]).lower()
    if any(phrase in text for phrase in _BANNED) or _DATE.search(text):
        return False
    if draft.stem in stems:
        return False
    if any(note.reader_note is not None for slide, note in notes.items() if slide in draft.slide_citations):
        return False
    return True


def _assemble(
    drafts: list[QuestionDraft], budget: list[tuple[str, int]], notes: list[SlideNote],
    stems: set[str], retake_id: str,
) -> tuple[list[Question], list[tuple[str, int]]]:
    remaining = dict(budget)
    note_map = {note.slide_number: note for note in notes}
    questions: list[Question] = []
    seen = set(stems)
    for draft in drafts:
        if not _valid(draft, remaining, note_map, seen):
            continue
        seen.add(draft.stem)
        questions.append(
            Question(
                question_id=f"{retake_id}-q{len(questions) + 1:02d}",
                **draft.model_dump(),
            )
        )
        remaining[draft.topic] -= 1
    return questions, [(name, count) for name, count in budget if remaining[name] > 0]


def retake_run(
    subject_slug: str,
    *,
    layout: paths.Layout | None = None,
    generator: RetakeGenerator | None = None,
) -> Quiz:
    """Generate and persist a fresh retake quiz for a registered subject."""

    layout = layout or paths.Layout()
    memory.require_subject(subject_slug, layout)
    if not memory.has_attempts(subject_slug, layout):
        raise RetakeError("cannot generate a retake before the subject has a graded attempt")
    profile = memory.load_profile(subject_slug, layout)
    performance = memory.topic_performance(subject_slug, layout)
    budget = select_topics(profile, performance)
    if not budget:
        raise RetakeError("cannot generate a retake because the subject has no topics")
    topics = {name for name, _ in budget}
    notes = _load_notes_for_topics(subject_slug, profile, topics, layout)
    prior_stems = _stored_question_stems(layout, subject_slug)
    retake_id = paths.new_attempt_id()
    generator = generator or AnthropicRetakeGenerator()
    drafts: list[QuestionDraft] = []
    question_prefix = f"retake-{retake_id}"
    questions, missing = _assemble(drafts, budget, notes, prior_stems, question_prefix)
    for attempt in range(config.QUIZ_REGENERATION_ATTEMPTS + 1):
        if not missing:
            break
        drafts.extend(
            generator.generate(_context(budget, notes, prior_stems)).questions
        )
        questions, missing = _assemble(drafts, budget, notes, prior_stems, question_prefix)
        if attempt >= config.QUIZ_REGENERATION_ATTEMPTS:
            break
    target = sum(count for _, count in budget)
    quiz = Quiz(
        quiz_id=f"retake-{retake_id}",
        subject_slug=subject_slug,
        kind=AttemptKind.retake,
        generated_at=paths.utc_iso(),
        covered_slide_count=len({note.slide_number for note in notes}),
        questions=questions,
        dropped_count=max(0, target - len(questions)),
    )
    paths.write_model(layout.retake_file(subject_slug, retake_id), quiz)
    return quiz
