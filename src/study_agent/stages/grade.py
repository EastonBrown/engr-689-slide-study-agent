"""Deterministic grading and attempt-derived performance."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from study_agent import memory, paths, schemas

UNANSWERED_RATIONALE = "Unanswered."
INVALID_CHOICE_RATIONALE = "Invalid option."
CORRECT_CHOICE_RATIONALE = "Selected the correct option."
UNANSWERED_CHOICE_INDEX = -1


def grade_quiz_file(
    quiz_path: Path,
    chosen_indices: Sequence[int | None],
    *,
    layout: paths.Layout | None = None,
    attempt_id: str | None = None,
    taken_at: str | None = None,
) -> schemas.GradeResult:
    """Grade one quiz sitting and append its attempt record."""

    quiz_payload = paths.read_json(quiz_path)
    if quiz_payload is None:
        raise ValueError(f"Quiz file is missing or invalid JSON: {quiz_path}")
    quiz = schemas.Quiz.model_validate(quiz_payload)
    root_layout = layout or paths.Layout(paths.repo_root())
    attempt_id = attempt_id or paths.new_attempt_id()
    taken_at = taken_at or _taken_at()

    result = grade_quiz(
        quiz,
        chosen_indices,
        quiz_sha256=paths.sha256_file(quiz_path),
        attempt_id=attempt_id,
        taken_at=taken_at,
    )
    memory.append_attempt(root_layout, result.attempt)
    return result


def grade_quiz(
    quiz: schemas.Quiz,
    chosen_indices: Sequence[int | None],
    *,
    quiz_sha256: str,
    attempt_id: str,
    taken_at: str,
) -> schemas.GradeResult:
    """Return feedback and rollup for a quiz without making model calls."""

    graded_questions: list[schemas.GradedQuestion] = []
    responses: list[schemas.Response] = []
    rollup: dict[str, dict[str, int]] = {}

    for position, question in enumerate(quiz.questions):
        chosen_index = chosen_indices[position] if position < len(chosen_indices) else None
        correct = chosen_index == question.correct_index if _is_valid_choice(question, chosen_index) else False
        chosen_rationale = _chosen_rationale(question, chosen_index, correct)

        graded_questions.append(
            schemas.GradedQuestion(
                question_id=question.question_id,
                topic=question.topic,
                stem=question.stem,
                chosen_index=chosen_index,
                correct_index=question.correct_index,
                correct=correct,
                explanation=question.explanation,
                chosen_rationale=chosen_rationale,
                slide_citations=question.slide_citations,
                source=question.source,
            )
        )
        responses.append(
            schemas.Response(
                question_id=question.question_id,
                topic=question.topic,
                chosen_index=_stored_choice(chosen_index),
                correct=correct,
                unanswered=chosen_index is None,
            )
        )
        counts = rollup.setdefault(question.topic, {"correct": 0, "seen": 0})
        counts["seen"] += 1
        if correct:
            counts["correct"] += 1

    attempt = schemas.Attempt(
        attempt_id=attempt_id,
        subject_slug=quiz.subject_slug,
        deck_slug=quiz.deck_slug,
        run_timestamp=quiz.run_timestamp,
        topics_touched=sorted(rollup),
        quiz_sha256=quiz_sha256,
        kind=quiz.kind,
        taken_at=taken_at,
        responses=responses,
    )
    rollup_rows = [
        schemas.TopicRollup(topic=topic, correct=counts["correct"], seen=counts["seen"])
        for topic, counts in rollup.items()
    ]
    correct_total = sum(1 for item in graded_questions if item.correct)
    return schemas.GradeResult(
        attempt=attempt,
        questions=graded_questions,
        rollup=rollup_rows,
        correct=correct_total,
        total=len(graded_questions),
    )


def _taken_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_valid_choice(question: schemas.Question, chosen_index: int | None) -> bool:
    return chosen_index is not None and 0 <= chosen_index < len(question.options)


def _chosen_rationale(question: schemas.Question, chosen_index: int | None, correct: bool) -> str | None:
    if chosen_index is None:
        return UNANSWERED_RATIONALE
    if not _is_valid_choice(question, chosen_index):
        return INVALID_CHOICE_RATIONALE
    if correct:
        return CORRECT_CHOICE_RATIONALE
    return question.distractor_rationale[chosen_index]


def _stored_choice(chosen_index: int | None) -> int:
    return UNANSWERED_CHOICE_INDEX if chosen_index is None else chosen_index
