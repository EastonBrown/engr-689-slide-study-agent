"""Deterministically grade a quiz and append the sitting to subject memory."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Sequence

from .. import memory, paths
from ..paths import Layout
from ..schemas import (
    Attempt,
    AttemptKind,
    GradeResult,
    GradedQuestion,
    Quiz,
    Response,
    TopicRollup,
)


class GradeError(ValueError):
    """The submitted answers cannot be matched to the quiz."""


def grade_quiz(
    quiz: Quiz,
    chosen_indices: Sequence[int | None],
    *,
    quiz_sha256: str = "",
    attempt_id: str | None = None,
    taken_at: str | None = None,
    kind: AttemptKind | None = None,
) -> GradeResult:
    """Grade answers in quiz order and return feedback plus topic rollups.

    ``None`` is an explicit unanswered response. It is stored as ``-1`` in the
    attempt record, receives no distractor rationale, and is excluded from the
    performance denominator because the student did not attempt it.
    """

    if len(chosen_indices) != len(quiz.questions):
        raise GradeError(
            f"expected {len(quiz.questions)} answers, got {len(chosen_indices)}"
        )

    correct_by_topic: Counter[str] = Counter()
    seen_by_topic: Counter[str] = Counter()
    graded: list[GradedQuestion] = []
    responses: list[Response] = []
    for question, chosen in zip(quiz.questions, chosen_indices):
        if chosen is None:
            chosen_index = -1
            is_correct = False
            rationale = None
        else:
            if not 0 <= chosen < len(question.options):
                raise GradeError(
                    f"answer for {question.question_id} must be between 0 and "
                    f"{len(question.options) - 1}, got {chosen}"
                )
            chosen_index = chosen
            is_correct = chosen == question.correct_index
            rationale = question.distractor_rationale[chosen]
            seen_by_topic[question.topic] += 1
            if is_correct:
                correct_by_topic[question.topic] += 1

        graded.append(
            GradedQuestion(
                question_id=question.question_id,
                topic=question.topic,
                stem=question.stem,
                chosen_index=chosen_index,
                correct_index=question.correct_index,
                correct=is_correct,
                explanation=question.explanation,
                chosen_rationale=rationale,
                slide_citations=question.slide_citations,
                source=question.source,
            )
        )
        responses.append(
            Response(
                question_id=question.question_id,
                topic=question.topic,
                chosen_index=chosen_index,
                correct=is_correct,
            )
        )

    attempt = Attempt(
        attempt_id=attempt_id or paths.new_attempt_id(),
        subject_slug=quiz.subject_slug,
        deck_slug=quiz.deck_slug,
        run_timestamp=quiz.run_timestamp,
        quiz_sha256=quiz_sha256,
        kind=kind or quiz.kind,
        taken_at=taken_at or paths.utc_iso(),
        responses=responses,
    )
    rollup = [
        TopicRollup(topic=topic, correct=correct_by_topic[topic], seen=seen_by_topic[topic])
        for topic in sorted(seen_by_topic)
    ]
    return GradeResult(
        attempt=attempt,
        questions=graded,
        rollup=rollup,
        correct=sum(item.correct for item in graded),
        total=len(graded),
    )


def grade_run(
    run_dir: Path,
    chosen_indices: Sequence[int | None],
    *,
    layout: Layout | None = None,
    kind: AttemptKind | None = None,
) -> GradeResult:
    """Grade ``quiz.json`` from a run and append exactly one attempt record."""

    layout = layout or Layout()
    quiz_path = paths.quiz_file(Path(run_dir))
    payload = paths.read_json(quiz_path)
    if payload is None:
        raise GradeError(f"missing or unreadable quiz: {quiz_path}")
    quiz = Quiz.model_validate(payload)
    memory.require_subject(quiz.subject_slug, layout)
    result = grade_quiz(
        quiz,
        chosen_indices,
        quiz_sha256=paths.sha256_file(quiz_path),
        kind=kind,
    )
    paths.write_model(layout.attempt_file(quiz.subject_slug, result.attempt.attempt_id), result.attempt)
    return result
