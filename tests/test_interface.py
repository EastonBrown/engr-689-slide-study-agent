"""Interface shell reads all state from disk."""

from __future__ import annotations

from pathlib import Path

from study_agent import config, interface, paths, schemas


def preflight() -> schemas.Preflight:
    return schemas.Preflight(
        readable=True,
        page_count=4,
        text_native_pages=2,
        text_native_fraction=0.5,
        image_only=False,
        page_width_px=2000,
        page_height_px=1125,
        downscaled=False,
        buildup_detection_ran=True,
        superseded_count=1,
        superseded=[3],
    )


def manifest() -> schemas.Manifest:
    return schemas.Manifest(
        schema_version=config.SCHEMA_VERSION,
        subject_slug="engr-689",
        deck_slug="deck",
        deck_sha256="a" * 64,
        deck_filename="Deck.pdf",
        run_timestamp="2026-08-20T12-00-00Z",
        started_at="2026-08-20T12-00-00Z",
        ended_at="2026-08-20T12-30-00Z",
        model=config.MODEL_ID,
        prompt_version=config.PROMPT_VERSION,
        dpi=config.RENDER_DPI,
        preflight=preflight(),
        paths=[
            schemas.PathStats(
                path=schemas.PathKind.image,
                slides_attempted=4,
                slides_succeeded=3,
                reader_notes=1,
                research_lookups=6,
                research_cache_hits=2,
                completed_stages=["render", "page_reader", "outline"],
            ),
            schemas.PathStats(
                path=schemas.PathKind.text,
                slides_attempted=4,
                slides_succeeded=4,
                completed_stages=["render", "page_reader"],
            ),
        ],
        stage_usage=[schemas.StageUsage(stage="page_reader", calls=8, cost_usd=0.12)],
        total_cost_usd=0.12,
    )


def note(slide_number: int, reader_note: str | None = None) -> schemas.SlideNote:
    return schemas.SlideNote(
        slide_number=slide_number,
        page_role=schemas.PageRole.content,
        title=f"Slide {slide_number}",
        reading=f"Reading {slide_number}.",
        visuals=[],
        concepts=[],
        verbatim_spans=[],
        reader_note=reader_note,
    )


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


def write_run(layout: paths.Layout) -> Path:
    run_dir = layout.run_dir("engr-689", "deck", "2026-08-20T12-00-00Z")
    paths.write_model(paths.manifest_file(run_dir), manifest())
    layout.write_latest("engr-689", "deck", "2026-08-20T12-00-00Z")
    for slide in (1, 2):
        target = paths.page_render_png(run_dir, slide)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"png")
    paths.write_model(paths.page_note(run_dir, "image", 1), note(1, reader_note="blurred"))
    paths.write_model(paths.page_note(run_dir, "text", 1), note(1))
    paths.write_model(paths.page_note(run_dir, "text", 2), note(2, reader_note="missing text"))
    return run_dir


def write_review_and_quiz(run_dir: Path) -> None:
    paths.write_text(paths.review_file(run_dir, "image"), "# Retrieval\nClaim [slide 1]\n")
    paths.write_text(paths.review_file(run_dir, "text"), "# Retrieval\nText claim [slide 2]\n")
    paths.write_model(
        paths.quiz_file(run_dir),
        schemas.Quiz(
            quiz_id="deck-2026-08-20T12-00-00Z",
            subject_slug="engr-689",
            deck_slug="deck",
            run_timestamp="2026-08-20T12-00-00Z",
            kind=schemas.AttemptKind.first_pass,
            generated_at="2026-08-20T12:10:00Z",
            covered_slide_count=4,
            questions=[
                schemas.Question(
                    question_id="deck-q01",
                    stem="What follows from retrieval?",
                    options=["correct option", "near miss", "wrong option", "also wrong"],
                    correct_index=0,
                    explanation="The slide says so.",
                    distractor_rationale=[None, "Near miss.", "Wrong.", "Also wrong."],
                    slide_citations=[1],
                    topic="Retrieval",
                    source=schemas.Source.prose,
                )
            ],
        ),
    )


def test_subject_options_come_from_registry(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)

    assert interface.subject_options(layout) == [interface.SubjectOption("engr-689", "ENGR 689")]


def test_create_subject_appends_registry_and_profile(tmp_path):
    layout = paths.Layout(tmp_path)

    option = interface.create_subject(layout, "ENGR 689")

    assert option == interface.SubjectOption("engr-689", "ENGR 689")
    assert interface.subject_options(layout) == [option]
    profile = schemas.Profile.model_validate(paths.read_json(layout.profile_file("engr-689")))
    assert profile.subject_slug == "engr-689"


def test_create_subject_preserves_existing_registry_metadata(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)

    interface.create_subject(layout, "Computer Vision")

    registry = schemas.SubjectsRegistry.model_validate(paths.read_json(layout.subjects_file()))
    assert registry.subjects[0].created_at == "2026-08-20T12:00:00Z"


def test_latest_run_summary_reads_manifest_numbers(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)

    summary = interface.latest_run_summary(layout, "engr-689")

    assert summary is not None
    assert summary.run_dir == run_dir
    assert summary.slides_read == 4
    assert summary.topics_matched == 0
    assert summary.topics_new == 0
    assert summary.research_lookups == 6
    assert summary.research_cache_hits == 2
    assert summary.total_cost_usd == 0.12
    assert summary.image_only is False
    assert summary.superseded_count == 1


def test_stage_states_pending_until_artifacts_exist(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)

    states = interface.stage_states(run_dir)

    assert [item.name for item in states] == [
        "Render",
        "Page reader",
        "Outline",
        "Research",
        "Review",
        "Quiz",
        "Grade",
    ]
    assert states[0].state == "complete"
    assert states[1].summary == "4 slides read."
    assert states[2].state == "partial"
    assert states[3].state == "pending"
    assert "waiting for artifacts" in states[3].summary


def test_empty_artifact_directory_does_not_mark_stage_complete(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)
    paths.run_research_dir(run_dir).mkdir(parents=True)

    states = interface.stage_states(run_dir)

    research = next(item for item in states if item.key == "research")
    assert research.state == "pending"


def test_active_run_marker_round_trips_from_disk(tmp_path):
    layout = paths.Layout(tmp_path)
    run_dir = layout.run_dir("engr-689", "deck", "2026-08-20T12-00-00Z")
    run_dir.mkdir(parents=True)

    interface.write_active_run(layout, run_dir)

    assert interface.read_active_run(layout) == run_dir


def test_degraded_reads_include_page_images(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)

    degraded = interface.degraded_reads(run_dir)

    assert [(item.path_kind, item.slide_number, item.reader_note, item.image_path) for item in degraded] == [
        ("image", 1, "blurred", paths.page_render_png(run_dir, 1)),
        ("text", 2, "missing text", paths.page_render_png(run_dir, 2)),
    ]


def test_review_provenance_resolves_citations_to_image_and_note(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)
    write_review_and_quiz(run_dir)

    review_doc = interface.review_document(run_dir, "image")

    assert review_doc is not None
    assert review_doc.markdown.startswith("# Retrieval")
    assert [(item.slide_number, item.image_path, item.note.title) for item in review_doc.citations] == [
        (1, paths.page_render_png(run_dir, 1), "Slide 1")
    ]


def test_comparison_metrics_are_computed_from_run_and_eval_labels(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)
    eval_file = tmp_path / "eval" / "figure-only-facts.json"
    paths.write_json(
        eval_file,
        {
            "schema_version": 1,
            "decks": {
                "deck": {
                    "facts": [
                        {"id": "headline", "slides": [1], "in_headline": True, "fact": "Reading 1."},
                        {"id": "weak", "slides": [10], "in_headline": False, "fact": "Reading 10."},
                    ]
                }
            },
        },
    )

    comparison = interface.comparison_scoreboard(run_dir, eval_file=eval_file)

    assert comparison.image.slides_read == 3
    assert comparison.text.slides_read == 4
    assert comparison.image.visuals_found == 0
    assert comparison.figure_only_label == "1/1 vs 1/1"
    assert comparison.slide_10_label == "partial on both sides"


def test_unlabeled_deck_and_image_only_text_baseline_are_explicit(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)
    updated = manifest().model_copy(update={"preflight": preflight().model_copy(update={"image_only": True})})
    paths.write_model(paths.manifest_file(run_dir), updated)

    comparison = interface.comparison_scoreboard(run_dir, eval_file=tmp_path / "missing.json")

    assert comparison.figure_only_label == "not labeled for this deck"
    assert comparison.text.not_applicable is True
    assert comparison.text.note == "text path not applicable, this deck is image-only"


def test_quiz_submission_grades_and_appends_attempt(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)
    write_review_and_quiz(run_dir)

    result = interface.submit_quiz_answers(
        layout,
        run_dir,
        {"deck-q01": 1},
        attempt_id="2026-08-20T12-20-00Z-aaaaaa",
        taken_at="2026-08-20T12:20:00Z",
    )

    assert result.questions[0].correct is False
    assert result.questions[0].chosen_rationale == "Near miss."
    assert [(item.topic, item.correct, item.seen) for item in result.rollup] == [("Retrieval", 0, 1)]


def test_latest_grade_result_rehydrates_from_attempt_file(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    run_dir = write_run(layout)
    write_review_and_quiz(run_dir)
    interface.submit_quiz_answers(
        layout,
        run_dir,
        {"deck-q01": 1},
        attempt_id="2026-08-20T12-20-00Z-aaaaaa",
        taken_at="2026-08-20T12:20:00Z",
    )

    result = interface.latest_grade_result(layout, run_dir)

    assert result is not None
    assert result.questions[0].chosen_rationale == "Near miss."
    assert result.rollup[0].seen == 1


def test_latest_retake_reads_newest_retake_from_disk(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)
    paths.write_model(
        layout.retake_file("engr-689", "2026-08-20T12-30-00Z-aaaaaa"),
        schemas.Quiz(
            quiz_id="2026-08-20T12-30-00Z-aaaaaa",
            subject_slug="engr-689",
            deck_slug=None,
            run_timestamp=None,
            kind=schemas.AttemptKind.retake,
            generated_at="2026-08-20T12:30:00Z",
            covered_slide_count=1,
            questions=[],
        ),
    )

    retake = interface.latest_retake(layout, "engr-689")

    assert retake is not None
    assert retake.quiz_id == "2026-08-20T12-30-00Z-aaaaaa"


def test_retake_refusal_is_returned_for_empty_attempt_history(tmp_path):
    layout = paths.Layout(tmp_path)
    register_subject(layout)

    message = interface.generate_retake_for_subject(layout, "engr-689")

    assert isinstance(message, str)
    assert "no attempts" in message.lower()
