"""Image-path quiz generator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .. import config, llm, paths
from ..prompts import quiz as quiz_prompts
from ..schemas import (
    AttemptKind,
    Manifest,
    Outline,
    PathKind,
    Question,
    QuestionDraft,
    Quiz,
    QuizDraft,
    SlideNote,
    Source,
    StageUsage,
)


QUIZ_STAGE = "quiz"
BRIDGED_FACT_TOPIC = "bridged_fact"
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_NAMED_AUTHOR = re.compile(
    r"\b(?:according to|by|from|did)\s+[A-Z][a-z]+(?:\s+et al\.)?\b|"
    r"\b[A-Z][a-z]+(?:\s+et al\.)?\s+"
    r"(?:argues|argue|proposes|propose|says|say|shows|show|introduced|wrote)\b"
)
_TITLE = re.compile(
    r"\b[A-Z][A-Za-z]+(?:\s+(?:Is|Are|All|You|Need|of|the|and|for|in|with|[A-Z][A-Za-z]+)){2,}\b"
)
_FACT_NUMBER = re.compile(
    r"\b(?:how many|what number|which number|how much|what year|what percentage|"
    r"what percent|what is the value|what value)\b",
    re.IGNORECASE,
)
_REASONING_NUMBER = re.compile(
    r"\b(?:if|when|given|doubles|halves|scale|scales|compute|calculate|why)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QuizRequest:
    outline: Outline
    notes: list[SlideNote]
    target_count: int
    regeneration: bool = False


@dataclass(frozen=True)
class QuizGenerationResult:
    draft: QuizDraft
    usage: StageUsage


class QuizGenerator(Protocol):
    def generate(self, request: QuizRequest) -> QuizGenerationResult:
        """Generate a quiz draft."""


class AnthropicQuizGenerator:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or llm.create_client()

    def generate(self, request: QuizRequest) -> QuizGenerationResult:
        result = llm.structured_call(
            self.client,
            response_model=QuizDraft,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": quiz_prompts.WRITE},
                        {"type": "text", "text": request.outline.model_dump_json()},
                        {
                            "type": "text",
                            "text": "["
                            + ",".join(note.model_dump_json() for note in request.notes)
                            + "]",
                        },
                        {"type": "text", "text": f"target_count={request.target_count}"},
                    ],
                }
            ],
            max_tokens=config.MAX_TOKENS_QUIZ,
            effort=config.EFFORT_QUIZ,
            stage=QUIZ_STAGE,
            system=quiz_prompts.SYSTEM,
        )
        return QuizGenerationResult(draft=result.output, usage=result.usage)


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


def has_banned_content(question: QuestionDraft) -> bool:
    text = " ".join([question.stem, *question.options])
    lowered = text.lower()
    if "all of the above" in lowered or "none of the above" in lowered:
        return True
    if _YEAR.search(text) or _TITLE.search(text) or _NAMED_AUTHOR.search(text):
        return True
    return bool(_FACT_NUMBER.search(text) and not _REASONING_NUMBER.search(text))


def _load_notes(run_dir: Path) -> list[SlideNote]:
    notes: list[SlideNote] = []
    for target in sorted(paths.notes_dir(run_dir, PathKind.image.value).glob("*.json")):
        payload = paths.read_json(target)
        if payload is not None:
            notes.append(SlideNote.model_validate(payload))
    return notes


def _allowed_slides(outline: Outline, notes: list[SlideNote]) -> set[int]:
    degraded = {slide for topic in outline.topics for slide in topic.degraded_slides}
    skipped = {item.slide_number for item in outline.skipped}
    notes_by_slide = {note.slide_number: note for note in notes}
    return {
        slide
        for topic in outline.topics
        for slide in topic.slides
        if slide not in degraded
        and slide not in skipped
        and notes_by_slide.get(slide) is not None
        and notes_by_slide[slide].reader_note is None
    }


def _budget(outline: Outline) -> dict[str, int]:
    return {topic: count for topic, count in outline.question_budget if count > 0}


def _target_count(outline: Outline) -> int:
    return min(config.QUIZ_QUESTIONS, sum(_budget(outline).values()))


def _valid_question(
    question: QuestionDraft,
    *,
    outline: Outline,
    allowed_slides: set[int],
    accepted_counts: dict[str, int],
) -> bool:
    if len(question.options) != 4 or not 0 <= question.correct_index <= 3:
        return False
    if len(question.distractor_rationale) != 4:
        return False
    if question.distractor_rationale[question.correct_index] is not None:
        return False
    if not question.slide_citations:
        return False
    if any(slide not in allowed_slides for slide in question.slide_citations):
        return False
    budget = _budget(outline)
    if question.topic not in budget:
        return False
    if accepted_counts.get(question.topic, 0) >= budget[question.topic]:
        return False
    if question.topic == BRIDGED_FACT_TOPIC and question.source != Source.visual:
        return False
    if has_banned_content(question):
        return False
    return True


def _filter_questions(
    drafts: list[QuestionDraft],
    *,
    outline: Outline,
    notes: list[SlideNote],
    accepted_counts: dict[str, int] | None = None,
) -> tuple[list[QuestionDraft], int]:
    allowed = _allowed_slides(outline, notes)
    accepted: list[QuestionDraft] = []
    counts = dict(accepted_counts or {})
    dropped = 0
    for item in drafts:
        if _valid_question(
            item,
            outline=outline,
            allowed_slides=allowed,
            accepted_counts=counts,
        ):
            accepted.append(item)
            counts[item.topic] = counts.get(item.topic, 0) + 1
        else:
            dropped += 1
    return accepted, dropped


def filter_questions(
    drafts: list[QuestionDraft],
    *,
    outline: Outline,
    notes: list[SlideNote],
    accepted_counts: dict[str, int] | None = None,
) -> tuple[list[QuestionDraft], int]:
    """Public quiz contract for first-pass and retake question validation."""

    return _filter_questions(
        drafts,
        outline=outline,
        notes=notes,
        accepted_counts=accepted_counts,
    )


def _covered_slide_count(outline: Outline) -> int:
    return sum(len(topic.slides) for topic in outline.topics)


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _materialize_quiz(
    *,
    subject_slug: str,
    deck_slug: str,
    run_timestamp: str,
    outline: Outline,
    questions: list[QuestionDraft],
    dropped: int,
) -> Quiz:
    return materialize_quiz(
        quiz_id=f"{deck_slug}-{run_timestamp}",
        subject_slug=subject_slug,
        deck_slug=deck_slug,
        run_timestamp=run_timestamp,
        kind=AttemptKind.first_pass,
        generated_at=_stamp(),
        covered_slide_count=_covered_slide_count(outline),
        question_id_prefix=deck_slug,
        questions=questions,
        dropped=dropped,
    )


def materialize_quiz(
    *,
    quiz_id: str,
    subject_slug: str,
    deck_slug: str | None,
    run_timestamp: str | None,
    kind: AttemptKind,
    generated_at: str,
    covered_slide_count: int,
    question_id_prefix: str,
    questions: list[QuestionDraft],
    dropped: int,
) -> Quiz:
    """Build a quiz artifact from validated question drafts."""

    return Quiz(
        quiz_id=quiz_id,
        subject_slug=subject_slug,
        deck_slug=deck_slug,
        run_timestamp=run_timestamp,
        kind=kind,
        generated_at=generated_at,
        covered_slide_count=covered_slide_count,
        questions=[
            Question(question_id=f"{question_id_prefix}-q{index:02d}", **question.model_dump())
            for index, question in enumerate(questions, start=1)
        ],
        dropped_count=dropped,
    )


def _load_manifest(run_dir: Path) -> Manifest | None:
    payload = paths.read_json(paths.manifest_file(run_dir))
    return Manifest.model_validate(payload) if payload is not None else None


def _update_manifest(run_dir: Path, manifest: Manifest | None, quiz: Quiz, usage: StageUsage) -> None:
    if manifest is None:
        return
    stats_by_path = {stat.path: stat for stat in manifest.paths}
    image_stats = stats_by_path.get(PathKind.image)
    if image_stats is not None:
        stages = list(image_stats.completed_stages)
        if QUIZ_STAGE not in stages:
            stages.append(QUIZ_STAGE)
        stats_by_path[PathKind.image] = image_stats.model_copy(
            update={"completed_stages": stages}
        )
    stage_usage = [item for item in manifest.stage_usage if item.stage != QUIZ_STAGE]
    if usage.calls:
        stage_usage.append(usage)
    paths.write_model(
        paths.manifest_file(run_dir),
        manifest.model_copy(
            update={
                "paths": list(stats_by_path.values()),
                "stage_usage": stage_usage,
                "total_cost_usd": sum(item.cost_usd for item in stage_usage),
                "quiz_questions": len(quiz.questions),
                "quiz_dropped": quiz.dropped_count,
            }
        ),
    )


def quiz_run(run_dir: Path, *, generator: QuizGenerator | None = None) -> None:
    """Generate quiz.json from the image path only."""

    run_dir = Path(run_dir)
    generator = generator or AnthropicQuizGenerator()
    manifest = _load_manifest(run_dir)
    outline_payload = paths.read_json(paths.outline_file(run_dir, PathKind.image.value))
    if outline_payload is None:
        return
    outline = Outline.model_validate(outline_payload)
    notes = _load_notes(run_dir)
    usage = StageUsage(stage=QUIZ_STAGE)

    first = generator.generate(
        QuizRequest(
            outline=outline,
            notes=notes,
            target_count=_target_count(outline),
        )
    )
    usage = _add_usage(usage, first.usage)
    accepted, dropped = _filter_questions(first.draft.questions, outline=outline, notes=notes)

    shortfall = _target_count(outline) - len(accepted)
    if shortfall > 0:
        second = generator.generate(
            QuizRequest(
                outline=outline,
                notes=notes,
                target_count=shortfall,
                regeneration=True,
            )
        )
        usage = _add_usage(usage, second.usage)
        accepted_counts: dict[str, int] = {}
        for question in accepted:
            accepted_counts[question.topic] = accepted_counts.get(question.topic, 0) + 1
        more, more_dropped = _filter_questions(
            second.draft.questions,
            outline=outline,
            notes=notes,
            accepted_counts=accepted_counts,
        )
        accepted.extend(more[:shortfall])
        dropped += more_dropped

    subject_slug = manifest.subject_slug if manifest else ""
    deck_slug = manifest.deck_slug if manifest else outline.deck_slug
    run_timestamp = manifest.run_timestamp if manifest else ""
    quiz = _materialize_quiz(
        subject_slug=subject_slug,
        deck_slug=deck_slug,
        run_timestamp=run_timestamp,
        outline=outline,
        questions=accepted,
        dropped=dropped,
    )
    paths.write_model(paths.quiz_file(run_dir), quiz)
    _update_manifest(run_dir, manifest, quiz, usage)
