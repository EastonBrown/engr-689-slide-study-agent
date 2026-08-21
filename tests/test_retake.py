from study_agent import config, memory, paths, schemas
from study_agent.stages import retake


def _attempt(layout, topic, attempt_id, correct=True):
    attempt = schemas.Attempt(
        attempt_id=attempt_id,
        subject_slug="engr-689",
        deck_slug="deck",
        run_timestamp="2026-08-20T12-00-00Z",
        quiz_sha256="b" * 64,
        kind=schemas.AttemptKind.first_pass,
        taken_at=attempt_id,
        responses=[schemas.Response(
            question_id=f"{topic}-{attempt_id}", topic=topic,
            chosen_index=0, correct=correct,
        )],
    )
    paths.write_model(layout.attempt_file("engr-689", attempt_id), attempt)


def _draft(topic, stem, slide):
    return schemas.QuestionDraft(
        stem=stem, options=["a", "b", "c", "d"], correct_index=0,
        explanation="because", distractor_rationale=[None, "b", "c", "d"],
        slide_citations=[slide], topic=topic, source=schemas.Source.prose,
    )


def test_select_topics_prioritizes_weak_then_oldest_undertested():
    profile = schemas.Profile(
        schema_version=config.SCHEMA_VERSION, subject_slug="engr-689",
        topics=[
            schemas.TopicRecord(name="Weak", first_seen_deck="d", exposure=9),
            schemas.TopicRecord(name="New", first_seen_deck="d", exposure=1),
            schemas.TopicRecord(name="Unseen", first_seen_deck="d", exposure=0),
        ],
    )
    performance = [schemas.TopicPerformance(topic="Weak", correct=1, seen=3, insufficient_evidence=False)]
    assert retake.select_topics(profile, performance) == [
        ("Weak", 2), ("Unseen", 4), ("New", 4)
    ]


def test_retake_reads_latest_image_notes_writes_fresh_quiz(tmp_path):
    layout = paths.Layout(tmp_path)
    memory.create_subject("ENGR 689", layout)
    profile = memory.load_profile("engr-689", layout)
    profile.topics = [schemas.TopicRecord(
        name="Agents", first_seen_deck="deck", decks=["deck"],
        slide_citations=[("deck", 1)], exposure=1,
    )]
    memory.save_profile(profile, layout)
    for index in range(3):
        _attempt(layout, "Agents", f"2026-08-20T12-0{index}-00Z")
    latest = layout.run_dir("engr-689", "deck", "2026-08-20T12-00-00Z")
    layout.write_latest("engr-689", "deck", "2026-08-20T12-00-00Z")
    paths.write_model(paths.page_note(latest, "image", 1), schemas.SlideNote(
        slide_number=1, page_role=schemas.PageRole.content, title="Agents",
        reading="An agent acts", visuals=[], concepts=[], verbatim_spans=[], reader_note=None,
    ))

    class Generator:
        usage = schemas.StageUsage(stage="retake")
        def generate(self, context):
            assert "Agents" in context
            return schemas.QuizDraft(questions=[_draft("Agents", "A fresh agent question", 1)])

    output = retake.retake_run("engr-689", layout=layout, generator=Generator())
    assert output.kind is schemas.AttemptKind.retake
    assert output.questions[0].question_id.startswith("retake-")
    stored = list(layout.retakes_dir("engr-689").glob("*.json"))
    assert len(stored) == 1
