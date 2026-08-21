from study_agent import paths, schemas
from study_agent.stages import quiz


def test_quiz_filters_invalid_questions_and_regenerates_once(tmp_path):
    run = tmp_path / "run"
    outline = schemas.Outline(
        deck_slug="deck", path=schemas.PathKind.image,
        topics=[schemas.OutlineTopic(name="A", slides=[1, 2], is_new=True, created_reason="x")],
        skipped=[], question_budget=[("A", 2)],
    )
    paths.write_model(paths.outline_file(run, "image"), outline)
    paths.write_model(paths.page_note(run, "image", 1), schemas.SlideNote(
        slide_number=1, page_role=schemas.PageRole.content, title="A", reading="x",
        visuals=[], concepts=[], verbatim_spans=[], reader_note=None,
    ))
    paths.write_model(paths.page_note(run, "image", 2), schemas.SlideNote(
        slide_number=2, page_role=schemas.PageRole.content, title="A", reading="x",
        visuals=[], concepts=[], verbatim_spans=[], reader_note="bad",
    ))
    paths.write_model(paths.manifest_file(run), schemas.Manifest(
        schema_version=1, subject_slug="subject", deck_slug="deck", deck_sha256="a" * 64,
        deck_filename="deck.pdf", run_timestamp="2026-08-20T12:00:00Z", started_at="2026-08-20T12:00:00Z",
        model="model", prompt_version="test", dpi=150,
        preflight=schemas.Preflight(readable=True, page_count=2, text_native_pages=2, text_native_fraction=1, image_only=False, page_width_px=1, page_height_px=1, downscaled=False, buildup_detection_ran=True, superseded_count=0),
        paths=[schemas.PathStats(path=kind, completed_stages=["outline"]) for kind in schemas.PathKind],
    ))

    def question(stem, slide):
        return schemas.QuestionDraft(stem=stem, options=["a", "b", "c", "d"], correct_index=0, explanation="why", distractor_rationale=[None, "b", "c", "d"], slide_citations=[slide], topic="A", source=schemas.Source.prose)

    class Generator:
        usage = schemas.StageUsage(stage="quiz", calls=2)
        def __init__(self): self.calls = 0
        def generate(self, context):
            self.calls += 1
            return schemas.QuizDraft(questions=[question("bad all of the above", 1)] if self.calls == 1 else [question("good", 1), question("degraded", 2)])

    generator = Generator()
    quiz.quiz_run(run, generator=generator)
    output = schemas.Quiz.model_validate(paths.read_json(paths.quiz_file(run)))
    assert generator.calls == 2
    assert len(output.questions) == 1
    assert output.questions[0].question_id == "deck-q01"
    manifest = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run)))
    assert manifest.quiz_questions == 1
    assert manifest.quiz_dropped == 1
