"""Quiz generator behaviour."""

from __future__ import annotations

from study_agent import config, paths, schemas
from study_agent.stages import quiz


def note(slide_number: int, *, reader_note: str | None = None) -> schemas.SlideNote:
    return schemas.SlideNote(
        slide_number=slide_number,
        page_role=schemas.PageRole.content,
        title=f"Slide {slide_number}",
        reading=f"Slide {slide_number} reading.",
        visuals=[],
        concepts=[],
        verbatim_spans=[],
        reader_note=reader_note,
    )


def outline() -> schemas.Outline:
    return schemas.Outline(
        deck_slug="deck",
        path=schemas.PathKind.image,
        topics=[
            schemas.OutlineTopic(name="A", slides=[1, 2], is_new=True, created_reason="new"),
            schemas.OutlineTopic(name="B", slides=[3], is_new=True, created_reason="new"),
        ],
        skipped=[schemas.SkippedSlide(slide_number=4, page_role=schemas.PageRole.title)],
        superseded=[],
        unassigned=[],
        bridged_facts=[
            schemas.BridgedFact(
                slides=[1, 2],
                statement="A bridge.",
                from_visuals=[],
                candidate_signal="shared_concept",
            )
        ],
        candidates_proposed=1,
        candidate_cap=30,
        topic_cap_exceeded=False,
        question_budget=[("bridged_fact", 1), ("A", 2), ("B", 1)],
    )


def question(topic: str, slide: int, *, source: schemas.Source = schemas.Source.prose) -> schemas.QuestionDraft:
    return schemas.QuestionDraft(
        stem=f"What follows for {topic}?",
        options=["Correct", "Distractor 1", "Distractor 2", "Distractor 3"],
        correct_index=0,
        explanation="Because the cited slide says so.",
        distractor_rationale=[None, "Wrong.", "Wrong.", "Wrong."],
        slide_citations=[slide],
        topic=topic,
        source=source,
    )


class FakeGenerator:
    def __init__(self, drafts: list[schemas.QuizDraft]) -> None:
        self.drafts = drafts
        self.requests: list[quiz.QuizRequest] = []

    def generate(self, request: quiz.QuizRequest) -> quiz.QuizGenerationResult:
        self.requests.append(request)
        return quiz.QuizGenerationResult(
            draft=self.drafts.pop(0),
            usage=schemas.StageUsage(stage="quiz", calls=1, input_tokens=10, cost_usd=0.3),
        )


def manifest() -> schemas.Manifest:
    return schemas.Manifest(
        schema_version=config.SCHEMA_VERSION,
        subject_slug="engr-689",
        deck_slug="deck",
        deck_sha256="a" * 64,
        deck_filename="deck.pdf",
        run_timestamp="2026-08-20T12-00-00Z",
        started_at="2026-08-20T12-00-00Z",
        ended_at="2026-08-20T12-00-00Z",
        model=config.MODEL_ID,
        prompt_version=config.PROMPT_VERSION,
        dpi=config.RENDER_DPI,
        preflight=schemas.Preflight(
            readable=True,
            page_count=4,
            text_native_pages=4,
            text_native_fraction=1.0,
            image_only=False,
            page_width_px=1,
            page_height_px=1,
            downscaled=False,
            buildup_detection_ran=True,
            superseded_count=0,
            superseded=[],
        ),
        paths=[
            schemas.PathStats(path=schemas.PathKind.image, completed_stages=["review"]),
            schemas.PathStats(path=schemas.PathKind.text, completed_stages=["review"]),
        ],
        stage_usage=[schemas.StageUsage(stage="render")],
        total_cost_usd=0,
    )


def write_inputs(run_dir):
    paths.write_model(paths.manifest_file(run_dir), manifest())
    paths.write_model(paths.outline_file(run_dir, "image"), outline())
    paths.write_model(paths.outline_file(run_dir, "text"), outline().model_copy(update={"path": schemas.PathKind.text}))
    for slide in (1, 2, 3):
        paths.write_model(paths.page_note(run_dir, "image", slide), note(slide))
    paths.write_model(paths.page_note(run_dir, "image", 4), note(4))


def test_quiz_run_writes_image_path_quiz_only_and_updates_manifest(tmp_path):
    run_dir = tmp_path / "run"
    write_inputs(run_dir)
    generator = FakeGenerator(
        [
            schemas.QuizDraft(
                questions=[
                    question("bridged_fact", 1, source=schemas.Source.visual),
                    question("A", 1),
                    question("A", 2),
                    question("B", 3),
                ]
            )
        ]
    )

    quiz.quiz_run(run_dir, generator=generator)

    result = schemas.Quiz.model_validate(paths.read_json(paths.quiz_file(run_dir)))
    assert result.subject_slug == "engr-689"
    assert result.deck_slug == "deck"
    assert result.covered_slide_count == 3
    assert [item.question_id for item in result.questions] == [
        "deck-q01",
        "deck-q02",
        "deck-q03",
        "deck-q04",
    ]
    assert not (run_dir / "quiz-text.json").exists()
    after = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    assert after.quiz_questions == 4
    assert after.quiz_dropped == 0
    assert any(item.stage == "quiz" and item.calls == 1 for item in after.stage_usage)


def test_invalid_questions_are_dropped_and_regenerated_once(tmp_path):
    run_dir = tmp_path / "run"
    write_inputs(run_dir)
    bad = question("A", 4)
    banned = question("B", 3)
    banned.options[1] = "All of the above"
    uncited = question("A", 1).model_copy(update={"slide_citations": []})
    generator = FakeGenerator(
        [
            schemas.QuizDraft(questions=[question("bridged_fact", 1, source=schemas.Source.visual), bad, banned, uncited]),
            schemas.QuizDraft(questions=[question("A", 1)]),
        ]
    )

    quiz.quiz_run(run_dir, generator=generator)

    result = schemas.Quiz.model_validate(paths.read_json(paths.quiz_file(run_dir)))
    after = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    assert len(generator.requests) == 2
    assert [item.topic for item in result.questions] == ["bridged_fact", "A"]
    assert after.quiz_questions == 2
    assert after.quiz_dropped == 3


def test_degraded_slide_citations_are_dropped(tmp_path):
    run_dir = tmp_path / "run"
    write_inputs(run_dir)
    paths.write_model(paths.page_note(run_dir, "image", 2), note(2, reader_note="blurred"))
    generator = FakeGenerator(
        [schemas.QuizDraft(questions=[question("A", 2)]), schemas.QuizDraft(questions=[])]
    )

    quiz.quiz_run(run_dir, generator=generator)

    result = schemas.Quiz.model_validate(paths.read_json(paths.quiz_file(run_dir)))
    assert len(generator.requests) == 2
    assert result.questions == []
    assert result.dropped_count == 1


def test_budget_validation_keeps_only_budgeted_counts_and_one_bridge_question(tmp_path):
    run_dir = tmp_path / "run"
    write_inputs(run_dir)
    generator = FakeGenerator(
        [
            schemas.QuizDraft(
                questions=[
                    question("bridged_fact", 1, source=schemas.Source.visual),
                    question("bridged_fact", 2, source=schemas.Source.visual),
                    question("A", 1),
                    question("A", 2),
                    question("A", 1),
                    question("B", 3),
                ]
            )
        ]
    )

    quiz.quiz_run(run_dir, generator=generator)

    result = schemas.Quiz.model_validate(paths.read_json(paths.quiz_file(run_dir)))
    counts = {topic: 0 for topic, _ in outline().question_budget}
    for item in result.questions:
        counts[item.topic] += 1
    assert counts == {"bridged_fact": 1, "A": 2, "B": 1}


def test_regeneration_cannot_exceed_already_filled_topic_budget(tmp_path):
    run_dir = tmp_path / "run"
    write_inputs(run_dir)
    generator = FakeGenerator(
        [
            schemas.QuizDraft(questions=[question("A", 1), question("A", 2)]),
            schemas.QuizDraft(questions=[question("A", 1), question("B", 3)]),
        ]
    )

    quiz.quiz_run(run_dir, generator=generator)

    result = schemas.Quiz.model_validate(paths.read_json(paths.quiz_file(run_dir)))
    assert [item.topic for item in result.questions] == ["A", "A", "B"]


def test_correct_option_rationale_must_be_null(tmp_path):
    run_dir = tmp_path / "run"
    write_inputs(run_dir)
    invalid = question("A", 1)
    invalid.distractor_rationale[0] = "Should be null."
    generator = FakeGenerator([schemas.QuizDraft(questions=[invalid]), schemas.QuizDraft(questions=[])])

    quiz.quiz_run(run_dir, generator=generator)

    result = schemas.Quiz.model_validate(paths.read_json(paths.quiz_file(run_dir)))
    assert result.questions == []


def test_manifest_marks_image_path_quiz_complete_but_not_text_path(tmp_path):
    run_dir = tmp_path / "run"
    write_inputs(run_dir)
    generator = FakeGenerator([schemas.QuizDraft(questions=[question("A", 1)]), schemas.QuizDraft(questions=[])])

    quiz.quiz_run(run_dir, generator=generator)

    after = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    image = next(stat for stat in after.paths if stat.path == schemas.PathKind.image)
    text = next(stat for stat in after.paths if stat.path == schemas.PathKind.text)
    assert "quiz" in image.completed_stages
    assert "quiz" not in text.completed_stages


def test_banned_dates_authors_titles_and_fact_numbers_are_detected():
    assert quiz.has_banned_content(question("A", 1).model_copy(update={"stem": "What happened in 2024?"}))
    assert quiz.has_banned_content(question("A", 1).model_copy(update={"stem": "What did Smith propose?"}))
    assert quiz.has_banned_content(question("A", 1).model_copy(update={"stem": "What does Attention Is All You Need say?"}))
    assert quiz.has_banned_content(question("A", 1).model_copy(update={"stem": "What does Deep Learning for Vision say?"}))
    assert quiz.has_banned_content(question("A", 1).model_copy(update={"stem": "How many layers are in the model?"}))
    assert not quiz.has_banned_content(question("A", 1).model_copy(update={"stem": "If resolution doubles, why does attention cost scale by 4?"}))
