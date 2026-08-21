"""Generate and validate the image-path quiz."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

from .. import config, llm, paths
from ..prompts import quiz as quiz_prompts
from ..schemas import Manifest, Outline, PathKind, Question, Quiz, QuizDraft, SlideNote, StageUsage


QUIZ_STAGE = "quiz"
_BANNED_PHRASES = ("all of the above", "none of the above", "named author", "paper title")
_DATE = re.compile(r"\b(?:19|20)\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
_REASONING_WORDS = ("calculate", "compute", "reason", "scale", "squared", "ratio", "proportion", "derive", "increase", "decrease")


class QuizError(RuntimeError):
    """The quiz stage could not produce a usable artifact."""


class QuizGenerator(Protocol):
    usage: StageUsage

    def generate(self, context: str) -> QuizDraft:
        """Generate one batch of draft questions."""


class AnthropicQuizGenerator:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or llm.create_client()
        self.usage = StageUsage(stage=QUIZ_STAGE)

    def generate(self, context: str) -> QuizDraft:
        result = llm.structured_call(
            self.client,
            response_model=QuizDraft,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": quiz_prompts.GENERATE_QUIZ},
                {"type": "text", "text": context},
            ]}],
            max_tokens=config.MAX_TOKENS_QUIZ,
            effort=config.EFFORT_QUIZ,
            stage=QUIZ_STAGE,
        )
        self.usage = _add_usage(self.usage, result.usage)
        return result.output


def _add_usage(first: StageUsage, second: StageUsage) -> StageUsage:
    return StageUsage(
        stage=QUIZ_STAGE,
        calls=first.calls + second.calls,
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        cache_read_tokens=first.cache_read_tokens + second.cache_read_tokens,
        web_searches=first.web_searches + second.web_searches,
        cost_usd=first.cost_usd + second.cost_usd,
    )


def _load_notes(run_dir: Path) -> list[SlideNote]:
    notes: list[SlideNote] = []
    for source in sorted(paths.notes_dir(run_dir, PathKind.image.value).glob("*.json")):
        payload = paths.read_json(source)
        if payload is not None:
            notes.append(SlideNote.model_validate(payload))
    return notes


def _context(
    outline: Outline,
    notes: list[SlideNote],
    missing: list[tuple[str, int]] | None = None,
) -> str:
    return (
        "QUESTION BUDGET:\n" + outline.model_dump_json() +
        "\nIMAGE SLIDE NOTES:\n" + "\n".join(note.model_dump_json() for note in notes) +
        ("\nMISSING BUDGET SLOTS:\n" + repr(missing) if missing else "")
    )


def _is_banned(question: Any) -> bool:
    text = " ".join([question.stem, *question.options]).lower()
    if any(phrase in text for phrase in _BANNED_PHRASES) or _DATE.search(text):
        return True
    if re.search(r"\b\d+(?:\.\d+)?\b", text) and not any(word in text for word in _REASONING_WORDS):
        return True
    return False


def _valid(
    draft: Any,
    *,
    outline: Outline,
    notes: dict[int, SlideNote],
    covered: set[int],
    degraded: set[int],
    forbidden: set[int],
) -> bool:
    if len(draft.options) != 4 or len(draft.distractor_rationale) != 4:
        return False
    if not 0 <= draft.correct_index < 4 or draft.distractor_rationale[draft.correct_index] is not None:
        return False
    if not draft.slide_citations or any(slide not in covered or slide in degraded or slide in forbidden for slide in draft.slide_citations):
        return False
    topic_slides = (
        {slide for topic in outline.topics for slide in topic.slides}
        if draft.topic == "bridged_fact"
        else next((set(topic.slides) for topic in outline.topics if topic.name == draft.topic), set())
    )
    if any(slide not in topic_slides for slide in draft.slide_citations):
        return False
    if draft.source.value == "visual" and not any(
        any(visual.assertion for visual in notes[slide].visuals)
        for slide in draft.slide_citations
        if slide in notes
    ):
        return False
    return not _is_banned(draft)


def _assemble(
    drafts: list[Any], outline: Outline, notes: list[SlideNote], deck_slug: str,
) -> tuple[list[Question], list[tuple[str, int]]]:
    covered = {slide for topic in outline.topics for slide in topic.slides}
    degraded = {
        slide
        for topic in outline.topics
        for slide in topic.degraded_slides
    } | {note.slide_number for note in notes if note.reader_note is not None}
    forbidden = set(outline.superseded) | set(outline.unassigned) | {item.slide_number for item in outline.skipped}
    remaining = dict(outline.question_budget)
    note_map = {note.slide_number: note for note in notes}
    questions: list[Question] = []
    seen: set[tuple[str, tuple[int, ...]]] = set()
    for draft in drafts:
        if draft.topic not in remaining or remaining[draft.topic] <= 0 or not _valid(
            draft,
            outline=outline,
            notes=note_map,
            covered=covered,
            degraded=degraded,
            forbidden=forbidden,
        ):
            continue
        key = (draft.stem, tuple(draft.slide_citations))
        if key in seen:
            continue
        seen.add(key)
        number = len(questions) + 1
        questions.append(Question(question_id=f"{deck_slug}-q{number:02d}", **draft.model_dump()))
        remaining[draft.topic] -= 1
    return questions, [(topic, count) for topic, count in outline.question_budget if remaining[topic] > 0]


def _mark_complete(run_dir: Path, quiz: Quiz, usage: StageUsage, dropped: int) -> None:
    payload = paths.read_json(paths.manifest_file(run_dir))
    if payload is None:
        return
    manifest = Manifest.model_validate(payload)
    paths.write_model(paths.quiz_file(run_dir), quiz)
    stages = [
        stat.model_copy(
            update={
                "completed_stages": list(dict.fromkeys([*stat.completed_stages, QUIZ_STAGE]))
            }
        )
        if stat.path == PathKind.image
        else stat
        for stat in manifest.paths
    ]
    usage_list = [item for item in manifest.stage_usage if item.stage != QUIZ_STAGE] + [usage]
    paths.write_model(paths.manifest_file(run_dir), manifest.model_copy(update={
        "paths": stages, "stage_usage": usage_list,
        "total_cost_usd": sum(item.cost_usd for item in usage_list),
        "quiz_questions": len(quiz.questions), "quiz_dropped": dropped,
    }))


def quiz_run(run_dir: Path, *, generator: QuizGenerator | None = None) -> None:
    run_dir = Path(run_dir)
    outline_payload = paths.read_json(paths.outline_file(run_dir, PathKind.image.value))
    if outline_payload is None:
        raise QuizError("missing image outline")
    outline = Outline.model_validate(outline_payload)
    notes = _load_notes(run_dir)
    generator = generator or AnthropicQuizGenerator()
    drafts: list[Any] = []
    questions, missing = _assemble(drafts, outline, notes, outline.deck_slug)
    if missing:
        drafts.extend(generator.generate(_context(outline, notes)).questions)
    questions, missing = _assemble(drafts, outline, notes, outline.deck_slug)
    if missing:
        drafts.extend(generator.generate(_context(outline, notes, missing)).questions)
        questions, missing = _assemble(drafts, outline, notes, outline.deck_slug)
    covered_count = len({slide for topic in outline.topics for slide in topic.slides})
    manifest = Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    target = sum(count for _, count in outline.question_budget)
    dropped = max(0, target - len(questions))
    quiz = Quiz(
        quiz_id=f"{outline.deck_slug}-{paths.utc_timestamp()}",
        subject_slug=manifest.subject_slug,
        deck_slug=outline.deck_slug,
        run_timestamp=manifest.run_timestamp,
        generated_at=paths.utc_timestamp(),
        covered_slide_count=covered_count,
        questions=questions,
        dropped_count=dropped,
    )
    _mark_complete(
        run_dir,
        quiz,
        getattr(generator, "usage", StageUsage(stage=QUIZ_STAGE)),
        dropped,
    )
