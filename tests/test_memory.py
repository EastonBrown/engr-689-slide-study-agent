"""Deck contribution memory and retake generation."""

from __future__ import annotations

from study_agent import config, memory, paths, schemas
from study_agent.stages import quiz as quiz_stage


def manifest(deck_sha256: str = "a" * 64, stamp: str = "2026-08-20T12-00-00Z") -> schemas.Manifest:
    return schemas.Manifest(
        schema_version=config.SCHEMA_VERSION,
        subject_slug="engr-689",
        deck_slug="deck",
        deck_sha256=deck_sha256,
        deck_filename="Deck.pdf",
        run_timestamp=stamp,
        started_at=stamp,
        ended_at=stamp,
        model=config.MODEL_ID,
        prompt_version=config.PROMPT_VERSION,
        dpi=config.RENDER_DPI,
        preflight=schemas.Preflight(
            readable=True,
            page_count=3,
            text_native_pages=3,
            text_native_fraction=1.0,
            image_only=False,
            page_width_px=1,
            page_height_px=1,
            downscaled=False,
            buildup_detection_ran=True,
            superseded_count=0,
            superseded=[],
        ),
        paths=[schemas.PathStats(path=schemas.PathKind.image)],
        stage_usage=[],
        total_cost_usd=0,
    )


def outline(*, slides: list[int] | None = None, topic: str = "Retrieval") -> schemas.Outline:
    return schemas.Outline(
        deck_slug="deck",
        path=schemas.PathKind.image,
        topics=[
            schemas.OutlineTopic(
                name=topic,
                slides=slides or [1, 2],
                is_new=True,
                created_reason="new",
            )
        ],
        skipped=[],
        superseded=[],
        unassigned=[],
        bridged_facts=[],
        candidates_proposed=0,
        candidate_cap=30,
        topic_cap_exceeded=False,
        question_budget=[(topic, 2)],
    )


def note(slide_number: int, topic: str = "Retrieval") -> schemas.SlideNote:
    return schemas.SlideNote(
        slide_number=slide_number,
        page_role=schemas.PageRole.content,
        title=f"{topic} {slide_number}",
        reading=f"{topic} note {slide_number}.",
        visuals=[],
        concepts=[
            schemas.Concept(
                name=topic,
                status=schemas.ConceptStatus.named_only,
                why_it_matters=f"{topic} matters.",
            )
        ],
        verbatim_spans=[],
        reader_note=None,
    )


def question(topic: str, slide: int = 1) -> schemas.QuestionDraft:
    return schemas.QuestionDraft(
        stem=f"What matters for {topic}?",
        options=["correct option", "near miss", "wrong option", "also wrong"],
        correct_index=0,
        explanation="Because the note says so.",
        distractor_rationale=[None, "Near miss.", "Wrong.", "Also wrong."],
        slide_citations=[slide],
        topic=topic,
        source=schemas.Source.prose,
    )


def attempt(attempt_id: str, responses: list[schemas.Response]) -> schemas.Attempt:
    return schemas.Attempt(
        attempt_id=attempt_id,
        subject_slug="engr-689",
        deck_slug="deck",
        run_timestamp="2026-08-20T12-00-00Z",
        topics_touched=sorted({item.topic for item in responses}),
        quiz_sha256="f" * 64,
        kind=schemas.AttemptKind.first_pass,
        taken_at="2026-08-20T12:30:00Z",
        responses=responses,
    )


def response(topic: str, correct: bool) -> schemas.Response:
    return schemas.Response(question_id=f"{topic}-q", topic=topic, chosen_index=0, correct=correct)


def write_run(layout: paths.Layout, stamp: str = "2026-08-20T12-00-00Z", deck_sha256: str = "a" * 64):
    run_dir = layout.run_dir("engr-689", "deck", stamp)
    paths.write_model(paths.manifest_file(run_dir), manifest(deck_sha256, stamp))
    paths.write_model(paths.outline_file(run_dir, "image"), outline())
    paths.write_model(paths.outline_file(run_dir, "text"), outline(topic="TextOnly"))
    paths.write_model(paths.page_note(run_dir, "image", 1), note(1))
    paths.write_model(paths.page_note(run_dir, "image", 2), note(2))
    layout.write_latest("engr-689", "deck", stamp)
    return run_dir


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


class FakeRetakeGenerator:
    def __init__(self) -> None:
        self.requests: list[quiz_stage.QuizRequest] = []

    def generate(self, request: quiz_stage.QuizRequest) -> quiz_stage.QuizGenerationResult:
        self.requests.append(request)
        questions = []
        slide_by_topic = {
            concept.name: note.slide_number
            for note in request.notes
            for concept in note.concepts
        }
        for topic, count in request.outline.question_budget:
            for _ in range(count):
                questions.append(question(topic, slide=slide_by_topic[topic]))
        return quiz_stage.QuizGenerationResult(
            draft=schemas.QuizDraft(questions=questions),
            usage=schemas.StageUsage(stage="retake", calls=1),
        )


def test_image_path_run_writes_contribution_and_text_path_does_not(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)

    contribution = memory.write_deck_contribution(run_dir, layout=layout)

    assert contribution.deck_slug == "deck"
    saved = schemas.DeckContribution.model_validate(
        paths.read_json(layout.contribution_file("engr-689", "deck"))
    )
    assert [(item.name, item.slides) for item in saved.topics] == [("Retrieval", [1, 2])]
    assert {item.name for item in saved.topics} != {"TextOnly"}
    profile = schemas.Profile.model_validate(paths.read_json(layout.profile_file("engr-689")))
    assert [(item.name, item.exposure) for item in profile.topics] == [("Retrieval", 2)]


def test_rerun_replaces_contribution_and_distinct_slug_gets_own_file(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    first = write_run(layout, stamp="2026-08-20T12-00-00Z", deck_sha256="a" * 64)
    memory.write_deck_contribution(first, layout=layout)
    second = write_run(layout, stamp="2026-08-20T12-01-00Z", deck_sha256="a" * 64)
    paths.write_model(paths.outline_file(second, "image"), outline(slides=[3]))
    paths.write_model(paths.page_note(second, "image", 3), note(3))
    memory.write_deck_contribution(second, layout=layout)

    saved = schemas.DeckContribution.model_validate(
        paths.read_json(layout.contribution_file("engr-689", "deck"))
    )
    assert saved.run_timestamp == "2026-08-20T12-01-00Z"
    assert saved.topics[0].slides == [3]
    other_run = layout.run_dir("engr-689", "deck-bbbbbbbb", "2026-08-20T12-02-00Z")
    paths.write_model(
        paths.manifest_file(other_run),
        manifest(deck_sha256="b" * 64, stamp="2026-08-20T12-02-00Z").model_copy(update={"deck_slug": "deck-bbbbbbbb"}),
    )
    paths.write_model(paths.outline_file(other_run, "image"), outline())
    memory.write_deck_contribution(other_run, layout=layout)

    assert layout.contribution_file("engr-689", "deck").is_file()
    assert layout.contribution_file("engr-689", "deck-bbbbbbbb").is_file()


def test_same_pdf_hash_with_new_slug_replaces_old_contribution_file(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    first = write_run(layout, stamp="2026-08-20T12-00-00Z", deck_sha256="a" * 64)
    memory.write_deck_contribution(first, layout=layout)
    renamed = layout.run_dir("engr-689", "renamed-deck", "2026-08-20T12-01-00Z")
    paths.write_model(
        paths.manifest_file(renamed),
        manifest(deck_sha256="a" * 64, stamp="2026-08-20T12-01-00Z").model_copy(update={"deck_slug": "renamed-deck"}),
    )
    paths.write_model(paths.outline_file(renamed, "image"), outline(slides=[3]))

    memory.write_deck_contribution(renamed, layout=layout)

    assert not layout.contribution_file("engr-689", "deck").exists()
    assert layout.contribution_file("engr-689", "renamed-deck").is_file()
    profile = schemas.Profile.model_validate(paths.read_json(layout.profile_file("engr-689")))
    assert profile.topics[0].decks == ["renamed-deck"]


def test_profile_exposure_is_derived_from_contributions(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)
    memory.write_deck_contribution(run_dir, layout=layout)

    profile = memory.derive_profile(layout, "engr-689")

    assert [(item.name, item.exposure, item.slide_citations) for item in profile.topics] == [
        ("Retrieval", 2, [("deck", 1), ("deck", 2)])
    ]


def test_retake_refuses_with_no_attempts(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)

    result = memory.generate_retake(layout, "engr-689", generator=FakeRetakeGenerator())

    assert isinstance(result, memory.RetakeRefusal)
    assert "no attempts" in result.message.lower()
    assert not layout.retakes_dir("engr-689").exists()


def test_retake_selects_weak_and_undertested_topics_and_writes_quiz(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)
    topic_names = ["WeakA", "WeakB", "WeakC", "Strong", "Older", "Newer"]
    paths.write_model(
        paths.outline_file(run_dir, "image"),
        schemas.Outline(
            deck_slug="deck",
            path=schemas.PathKind.image,
            topics=[
                schemas.OutlineTopic(name=name, slides=[index], is_new=True, created_reason="new")
                for index, name in enumerate(topic_names, start=1)
            ],
            skipped=[],
            superseded=[],
            unassigned=[],
            bridged_facts=[],
            candidates_proposed=0,
            candidate_cap=30,
            topic_cap_exceeded=False,
            question_budget=[(name, 1) for name in topic_names],
        ),
    )
    for index, name in enumerate(topic_names, start=1):
        paths.write_model(paths.page_note(run_dir, "image", index), note(index, name))
    memory.write_deck_contribution(run_dir, layout=layout)
    memory.append_attempt(
        layout,
        attempt(
            "2026-08-20T12-01-00Z-aaaaaa",
            [response("WeakA", False), response("WeakB", False), response("WeakC", True), response("Strong", True)],
        ),
    )
    memory.append_attempt(
        layout,
        attempt(
            "2026-08-20T12-02-00Z-aaaaaa",
            [response("WeakA", False), response("WeakB", True), response("WeakC", True), response("Strong", True)],
        ),
    )
    memory.append_attempt(
        layout,
        attempt(
            "2026-08-20T12-03-00Z-aaaaaa",
            [response("WeakA", True), response("WeakB", False), response("WeakC", False), response("Strong", True)],
        ),
    )
    generator = FakeRetakeGenerator()

    retake = memory.generate_retake(
        layout,
        "engr-689",
        generator=generator,
        retake_id="2026-08-20T12-40-00Z-aaaaaa",
        generated_at="2026-08-20T12:40:00Z",
    )

    assert isinstance(retake, schemas.Quiz)
    assert retake.kind == schemas.AttemptKind.retake
    assert retake.deck_slug is None
    assert retake.run_timestamp is None
    assert generator.requests[0].outline.question_budget == [
        ("WeakA", 2),
        ("WeakB", 2),
        ("WeakC", 2),
        ("Older", 2),
        ("Newer", 2),
    ]
    assert [item.slide_number for item in generator.requests[0].notes] == [1, 2, 3, 5, 6]
    saved = schemas.Quiz.model_validate(
        paths.read_json(layout.retake_file("engr-689", "2026-08-20T12-40-00Z-aaaaaa"))
    )
    assert len(saved.questions) == 10
    assert saved.quiz_id == "2026-08-20T12-40-00Z-aaaaaa"


def test_unregistered_subject_is_an_error_for_memory_reads(tmp_path):
    layout = paths.Layout(tmp_path)

    try:
        memory.derive_profile(layout, "engr-689")
    except memory.SubjectRegistryError as error:
        assert "subjects.json" in str(error)
    else:
        raise AssertionError("expected unregistered subject to refuse")


def test_single_undertested_topic_absorbs_remaining_retake_questions(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)
    paths.write_model(
        paths.outline_file(run_dir, "image"),
        schemas.Outline(
            deck_slug="deck",
            path=schemas.PathKind.image,
            topics=[
                schemas.OutlineTopic(name=name, slides=[index], is_new=True, created_reason="new")
                for index, name in enumerate(["WeakA", "WeakB", "WeakC", "OnlyNew"], start=1)
            ],
            skipped=[],
            superseded=[],
            unassigned=[],
            bridged_facts=[],
            candidates_proposed=0,
            candidate_cap=30,
            topic_cap_exceeded=False,
            question_budget=[],
        ),
    )
    for index, name in enumerate(["WeakA", "WeakB", "WeakC", "OnlyNew"], start=1):
        paths.write_model(paths.page_note(run_dir, "image", index), note(index, name))
    memory.write_deck_contribution(run_dir, layout=layout)
    for attempt_number in range(3):
        memory.append_attempt(
            layout,
            attempt(
                f"2026-08-20T12-0{attempt_number}-00Z-aaaaaa",
                [
                    response("WeakA", attempt_number == 2),
                    response("WeakB", attempt_number == 1),
                    response("WeakC", attempt_number != 2),
                ],
            ),
        )
    generator = FakeRetakeGenerator()

    result = memory.generate_retake(layout, "engr-689", generator=generator)

    assert isinstance(result, schemas.Quiz)
    assert generator.requests[0].outline.question_budget == [
        ("WeakA", 2),
        ("WeakB", 2),
        ("WeakC", 2),
        ("OnlyNew", 4),
    ]


def test_retake_refuses_when_latest_image_notes_are_missing(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)
    memory.write_deck_contribution(run_dir, layout=layout)
    memory.append_attempt(
        layout,
        attempt("2026-08-20T12-01-00Z-aaaaaa", [response("Retrieval", False)]),
    )
    paths.page_note(run_dir, "image", 1).unlink()

    result = memory.generate_retake(layout, "engr-689", generator=FakeRetakeGenerator())

    assert isinstance(result, memory.RetakeRefusal)
    assert "missing" in result.message.lower()
