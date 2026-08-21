from pathlib import Path

import pytest

from study_agent import memory, paths
from study_agent.schemas import (
    AttemptKind,
    Question,
    Quiz,
    Source,
)
from study_agent.stages import grade


def question(number: int, topic: str, correct: int, rationale: str | None) -> Question:
    rationales = ["wrong", "wrong", "wrong", "wrong"]
    rationales[0] = rationale or "wrong"
    rationales[correct] = None
    return Question(
        question_id=f"deck-q{number:02d}",
        stem=f"Question {number}",
        options=["A", "B", "C", "D"],
        correct_index=correct,
        explanation=f"Explanation {number}",
        distractor_rationale=rationales,
        slide_citations=[number],
        topic=topic,
        source=Source.prose,
    )


def quiz() -> Quiz:
    first = question(1, "Encoders", 1, None)
    second = question(2, "Attention", 2, "Option B confuses the two mechanisms.")
    return Quiz(
        quiz_id="deck-quiz",
        subject_slug="engr-689",
        deck_slug="deck",
        run_timestamp="2026-08-20T09-00-00Z",
        generated_at="2026-08-20T09:00:00Z",
        covered_slide_count=2,
        questions=[first, second],
    )


def test_grading_returns_feedback_and_topic_rollup():
    result = grade.grade_quiz(quiz(), [1, 0], quiz_sha256="f" * 64)

    assert result.correct == 1
    assert result.total == 2
    assert [(item.question_id, item.correct) for item in result.questions] == [
        ("deck-q01", True),
        ("deck-q02", False),
    ]
    assert result.questions[0].explanation == "Explanation 1"
    assert result.questions[1].chosen_rationale == "Option B confuses the two mechanisms."
    assert [(item.topic, item.correct, item.seen) for item in result.rollup] == [
        ("Attention", 0, 1),
        ("Encoders", 1, 1),
    ]


def test_unanswered_question_is_explicit_and_not_counted_as_seen():
    result = grade.grade_quiz(quiz(), [None, 2], quiz_sha256="f" * 64)

    unanswered = result.questions[0]
    assert unanswered.chosen_index == -1
    assert unanswered.correct is False
    assert unanswered.chosen_rationale is None
    assert [(item.topic, item.correct, item.seen) for item in result.rollup] == [
        ("Attention", 1, 1),
    ]


def test_unanswered_response_does_not_enter_derived_performance(tmp_path: Path):
    layout = paths.Layout(root=tmp_path)
    memory.create_subject("ENGR 689", layout)
    run_dir = tmp_path / "runs" / "run-1"
    paths.write_model(paths.quiz_file(run_dir), quiz())

    grade.grade_run(run_dir, [None, 2], layout=layout)

    performance = memory.topic_performance("engr-689", layout)
    assert [(item.topic, item.correct, item.seen) for item in performance] == [
        ("Attention", 1, 1),
    ]


def test_grade_run_appends_attempt_without_changing_profile(tmp_path: Path):
    layout = paths.Layout(root=tmp_path)
    memory.create_subject("ENGR 689", layout)
    run_dir = tmp_path / "runs" / "run-1"
    quiz_path = paths.quiz_file(run_dir)
    paths.write_model(quiz_path, quiz())

    before = layout.profile_file("engr-689").read_text(encoding="utf-8")
    result = grade.grade_run(run_dir, [1, 2], layout=layout)

    attempts = memory.load_attempts("engr-689", layout)
    assert len(attempts) == 1
    assert attempts[0].quiz_sha256 == paths.sha256_file(quiz_path)
    assert attempts[0].kind is AttemptKind.first_pass
    assert [response.correct for response in attempts[0].responses] == [True, True]
    assert result.attempt.attempt_id == attempts[0].attempt_id
    assert layout.profile_file("engr-689").read_text(encoding="utf-8") == before


def test_grade_run_refuses_an_unregistered_subject(tmp_path: Path):
    layout = paths.Layout(root=tmp_path)
    run_dir = tmp_path / "runs" / "run-1"
    paths.write_model(paths.quiz_file(run_dir), quiz())

    with pytest.raises(memory.UnknownSubject):
        grade.grade_run(run_dir, [1, 2], layout=layout)
