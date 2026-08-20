"""Deterministic quiz grading and attempt memory."""

from __future__ import annotations

from pathlib import Path

from study_agent import memory, paths, schemas
from study_agent.stages import grade


def question(
    question_id: str,
    topic: str,
    correct_index: int = 0,
) -> schemas.Question:
    return schemas.Question(
        question_id=question_id,
        stem=f"What is true about {topic}?",
        options=["Correct", "Near miss", "Wrong", "Also wrong"],
        correct_index=correct_index,
        explanation=f"{topic} explanation.",
        distractor_rationale=[None, f"{topic} near miss.", f"{topic} wrong.", f"{topic} also wrong."],
        slide_citations=[1],
        topic=topic,
        source=schemas.Source.prose,
    )


def quiz() -> schemas.Quiz:
    return schemas.Quiz(
        quiz_id="deck-2026-08-20T12-00-00Z",
        subject_slug="engr-689",
        deck_slug="deck",
        run_timestamp="2026-08-20T12-00-00Z",
        kind=schemas.AttemptKind.first_pass,
        generated_at="2026-08-20T12-00-00Z",
        covered_slide_count=2,
        questions=[
            question("deck-q01", "Retrieval", correct_index=0),
            question("deck-q02", "RAG", correct_index=2),
            question("deck-q03", "RAG", correct_index=1),
        ],
    )


def write_quiz(root: Path, item: schemas.Quiz | None = None) -> Path:
    target = root / "runs" / "deck" / "2026-08-20T12-00-00Z" / "quiz.json"
    paths.write_model(target, item or quiz())
    return target


def register_subject(layout: paths.Layout) -> None:
    paths.write_model(
        layout.subjects_file(),
        schemas.SubjectsRegistry(
            subjects=[
                schemas.SubjectEntry(
                    slug="engr-689",
                    display_name="ENGR 689",
                    created_at="2026-08-20T12:00:00Z",
                )
            ]
        ),
    )


def test_grade_quiz_returns_verdict_feedback_and_topic_rollup(tmp_path):
    quiz_path = write_quiz(tmp_path)

    result = grade.grade_quiz_file(
        quiz_path,
        [0, 1, 1],
        layout=paths.Layout(tmp_path),
        attempt_id="2026-08-20T12-10-00Z-aaaaaa",
        taken_at="2026-08-20T12:10:00Z",
    )

    assert [item.correct for item in result.questions] == [True, False, True]
    assert [item.explanation for item in result.questions] == [
        "Retrieval explanation.",
        "RAG explanation.",
        "RAG explanation.",
    ]
    assert result.questions[1].chosen_rationale == "RAG near miss."
    assert result.questions[0].chosen_rationale == "Selected the correct option."
    assert [(item.topic, item.correct, item.seen) for item in result.rollup] == [
        ("Retrieval", 1, 1),
        ("RAG", 1, 2),
    ]


def test_grade_quiz_appends_one_attempt_and_does_not_touch_profile(tmp_path):
    quiz_path = write_quiz(tmp_path)
    layout = paths.Layout(tmp_path)
    profile_path = layout.profile_file("engr-689")
    paths.write_json(profile_path, {"schema_version": 1, "subject_slug": "engr-689", "topics": []})
    before = profile_path.read_text(encoding="utf-8")

    grade.grade_quiz_file(
        quiz_path,
        [0, 2, 1],
        layout=layout,
        attempt_id="2026-08-20T12-10-00Z-aaaaaa",
        taken_at="2026-08-20T12:10:00Z",
    )

    attempt_files = sorted(layout.attempts_dir("engr-689").glob("*.json"))
    assert [item.name for item in attempt_files] == ["2026-08-20T12-10-00Z-aaaaaa.json"]
    attempt = schemas.Attempt.model_validate(paths.read_json(attempt_files[0]))
    assert attempt.subject_slug == "engr-689"
    assert attempt.deck_slug == "deck"
    assert attempt.run_timestamp == "2026-08-20T12-00-00Z"
    assert attempt.topics_touched == ["RAG", "Retrieval"]
    assert attempt.quiz_sha256 == paths.sha256_file(quiz_path)
    assert {item.topic for item in attempt.responses} == {"Retrieval", "RAG"}
    assert profile_path.read_text(encoding="utf-8") == before


def test_grade_quiz_handles_unanswered_explicitly(tmp_path):
    quiz_path = write_quiz(tmp_path)

    result = grade.grade_quiz_file(
        quiz_path,
        [None, 2],
        layout=paths.Layout(tmp_path),
        attempt_id="2026-08-20T12-10-00Z-aaaaaa",
        taken_at="2026-08-20T12:10:00Z",
    )

    assert result.questions[0].chosen_index is None
    assert result.questions[0].correct is False
    assert result.questions[0].chosen_rationale == "Unanswered."
    assert result.attempt.responses[0].chosen_index == -1
    assert result.attempt.responses[0].unanswered is True
    assert result.rollup[0].seen == 1


def test_performance_derivation_requires_three_sittings(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    quiz_path = write_quiz(tmp_path)
    for attempt_number, choices in enumerate(([0, 2, 1], [0, 1, 1], [1, 2, 0]), start=1):
        grade.grade_quiz_file(
            quiz_path,
            list(choices),
            layout=layout,
            attempt_id=f"2026-08-20T12-1{attempt_number}-00Z-aaaaaa",
            taken_at=f"2026-08-20T12:1{attempt_number}:00Z",
        )

    performance = memory.derive_topic_performance(layout, "engr-689")

    assert [(item.topic, item.correct, item.seen, item.insufficient_evidence) for item in performance] == [
        ("RAG", 4, 6, False),
        ("Retrieval", 2, 3, False),
    ]


def test_performance_with_fewer_than_three_sightings_reports_insufficient_evidence(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    quiz_path = write_quiz(tmp_path)
    grade.grade_quiz_file(
        quiz_path,
        [0, 2, 1],
        layout=layout,
        attempt_id="2026-08-20T12-10-00Z-aaaaaa",
        taken_at="2026-08-20T12:10:00Z",
    )

    performance = memory.derive_topic_performance(layout, "engr-689")

    assert [(item.topic, item.correct, item.seen, item.insufficient_evidence) for item in performance] == [
        ("RAG", 2, 2, True),
        ("Retrieval", 1, 1, True),
    ]
