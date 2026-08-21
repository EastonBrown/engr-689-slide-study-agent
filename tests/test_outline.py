"""Outline stage behaviour."""

from __future__ import annotations

import pytest

from study_agent import memory, paths, schemas
from study_agent.stages import outline


def note(
    slide_number: int,
    *,
    role: schemas.PageRole = schemas.PageRole.content,
    title: str | None = "Topic",
    concepts: list[str] | None = None,
    relates_to: list[int] | None = None,
    reader_note: str | None = None,
) -> schemas.SlideNote:
    return schemas.SlideNote(
        slide_number=slide_number,
        page_role=role,
        title=title,
        reading=f"slide {slide_number}",
        visuals=[
            schemas.Visual(
                kind=schemas.VisualKind.diagram,
                description="diagram",
                assertion="joined fact",
                relates_to_slides=relates_to or [],
            )
        ]
        if relates_to is not None
        else [],
        concepts=[
            schemas.Concept(
                name=name,
                status=schemas.ConceptStatus.explained_here,
                why_it_matters="matters",
            )
            for name in (concepts or [])
        ],
        verbatim_spans=[],
        reader_note=reader_note,
    )


class FakeOutliner:
    def __init__(
        self,
        grouping: schemas.GroupingDraft,
        bridges: schemas.BridgeDraft | None = None,
        repair: schemas.GroupingDraft | None = None,
    ) -> None:
        self.grouping = grouping
        self.bridges = bridges or schemas.BridgeDraft(confirmations=[])
        self.repair = repair
        self.compacted_slides: list[int] = []
        self.candidates: list[outline.BridgeCandidate] = []
        self.repair_called = False
        self.group_calls = 0
        self.confirm_calls = 0

    def group(
        self,
        notes: list[schemas.SlideNote],
        existing_topics: list[str],
    ) -> schemas.GroupingDraft:
        del existing_topics
        self.group_calls += 1
        self.compacted_slides = [item.slide_number for item in notes]
        return self.grouping

    def confirm_bridges(
        self,
        notes_by_slide: dict[int, schemas.SlideNote],
        candidates: list[outline.BridgeCandidate],
    ) -> schemas.BridgeDraft:
        del notes_by_slide
        self.confirm_calls += 1
        self.candidates = candidates
        return self.bridges

    def repair_grouping(
        self,
        notes: list[schemas.SlideNote],
        existing_topics: list[str],
        grouping: schemas.GroupingDraft,
        violations: list[str],
    ) -> schemas.GroupingDraft:
        del notes, existing_topics, grouping, violations
        self.repair_called = True
        return self.repair or self.grouping


def topic(name: str, slides: list[int], is_new: bool = True) -> schemas.TopicAssignmentDraft:
    return schemas.TopicAssignmentDraft(
        name=name,
        slides=slides,
        is_new=is_new,
        created_reason="new" if is_new else None,
    )


def test_outline_partitions_covered_slides_and_names_skipped_roles(tmp_path):
    notes = [
        note(1, role=schemas.PageRole.title),
        note(2, concepts=["A"]),
        note(3, concepts=["A"]),
    ]
    outliner = FakeOutliner(schemas.GroupingDraft(topics=[topic("A", [2, 3])]))

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=[],
        superseded=[],
        outliner=outliner,
    )

    assert result.skipped == [
        schemas.SkippedSlide(slide_number=1, page_role=schemas.PageRole.title)
    ]
    assert result.topics[0].slides == [2, 3]
    assert result.unassigned == []


def test_superseded_frames_are_omitted_from_model_input_partition_and_candidates():
    notes = [
        note(1, title="Build", concepts=["A"]),
        note(2, title="Build", concepts=["A"]),
        note(3, title="Next", concepts=["A"]),
        note(4, role=schemas.PageRole.section_break, title="Section"),
    ]
    outliner = FakeOutliner(schemas.GroupingDraft(topics=[topic("A", [2, 3])]))

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=[],
        superseded=[1],
        outliner=outliner,
    )

    assert result.superseded == [1]
    assert outliner.compacted_slides == [2, 3, 4]
    assert all(1 not in candidate.slides for candidate in outliner.candidates)


def test_candidates_come_from_the_three_code_side_signals():
    notes = [
        note(55, title="Generation", concepts=["RAG"], relates_to=[56]),
        note(56, title=None, concepts=["RAG"]),
        note(57, title="Generation", concepts=["Other"]),
    ]

    proposal = outline.propose_bridge_candidates(notes, cap=10)

    by_pair = {candidate.slides: candidate for candidate in proposal.candidates}
    assert set(by_pair[(55, 56)].signals) == {
        "relates_to_slides",
        "adjacent_title",
        "shared_concept",
    }
    assert (56, 57) not in by_pair


def test_bridge_confirmation_cannot_introduce_unproposed_candidates():
    notes = [note(1, relates_to=[2]), note(2)]
    outliner = FakeOutliner(
        schemas.GroupingDraft(topics=[topic("A", [1, 2])]),
        schemas.BridgeDraft(
            confirmations=[
                schemas.BridgeConfirmationDraft(
                    candidate_index=99,
                    confirmed=True,
                    statement="invented",
                    from_visuals=[],
                )
            ]
        ),
    )

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=[],
        superseded=[],
        outliner=outliner,
    )

    assert result.bridged_facts == []


def test_bridge_confirmation_cannot_reference_visuals_outside_candidate_slides():
    notes = [note(1, relates_to=[2]), note(2), note(3)]
    outliner = FakeOutliner(
        schemas.GroupingDraft(topics=[topic("A", [1, 2, 3])]),
        schemas.BridgeDraft(
            confirmations=[
                schemas.BridgeConfirmationDraft(
                    candidate_index=0,
                    confirmed=True,
                    statement="valid",
                    from_visuals=[(1, 0), (3, 0)],
                )
            ]
        ),
    )

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=[],
        superseded=[],
        outliner=outliner,
    )

    assert result.bridged_facts[0].slides == [1, 2]
    assert result.bridged_facts[0].from_visuals == [(1, 0)]


def test_question_budget_sums_to_ten_and_reserves_one_for_a_bridge():
    topics = [
        schemas.OutlineTopic(name="A", slides=[1, 2, 3, 4], is_new=True),
        schemas.OutlineTopic(name="B", slides=[5, 6, 7], is_new=True),
        schemas.OutlineTopic(name="C", slides=[8, 9], is_new=True),
        schemas.OutlineTopic(name="D", slides=[10], is_new=True),
    ]

    budget, untested_topics = outline.allocate_question_budget(
        topics,
        has_bridged_facts=True,
        total_questions=10,
        max_per_topic=3,
    )

    assert sum(count for _, count in budget) == 10
    assert untested_topics == []
    assert ("bridged_fact", 1) in budget
    assert ("A", 3) in budget


def test_question_budget_ships_short_when_the_hard_topic_cap_makes_ten_impossible():
    topics = [schemas.OutlineTopic(name="A", slides=[1], is_new=True)]

    budget, untested_topics = outline.allocate_question_budget(
        topics,
        has_bridged_facts=False,
        total_questions=10,
        max_per_topic=3,
    )

    assert budget == [("A", 3)]
    assert untested_topics == []


def test_question_budget_keeps_the_hard_topic_cap_alongside_a_bridge():
    topics = [schemas.OutlineTopic(name="A", slides=[1], is_new=True)]

    budget, untested_topics = outline.allocate_question_budget(
        topics,
        has_bridged_facts=True,
        total_questions=10,
        max_per_topic=3,
    )

    assert budget == [("bridged_fact", 1), ("A", 3)]
    assert untested_topics == []


def test_topic_allocated_zero_is_recorded_as_untested():
    topics = [
        schemas.OutlineTopic(name=f"T{slide}", slides=[slide], is_new=True)
        for slide in range(1, 13)
    ]

    budget, untested_topics = outline.allocate_question_budget(
        topics,
        has_bridged_facts=True,
        total_questions=10,
        max_per_topic=3,
    )

    assert sum(count for _, count in budget) == 10
    assert any(count == 0 for _, count in budget)
    assert untested_topics
    assert all(not name.startswith("untested:") for name, _ in budget)


def test_topics_are_ordered_by_first_slide_not_model_order():
    notes = [note(1), note(2), note(3)]
    outliner = FakeOutliner(
        schemas.GroupingDraft(topics=[topic("Later", [3]), topic("Earlier", [1, 2])])
    )

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=[],
        superseded=[],
        outliner=outliner,
    )

    assert [topic.name for topic in result.topics] == ["Earlier", "Later"]


def test_degraded_content_slides_are_flagged_inside_their_topic():
    notes = [note(1, reader_note="low confidence"), note(2)]
    outliner = FakeOutliner(schemas.GroupingDraft(topics=[topic("A", [1, 2])]))

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=[],
        superseded=[],
        outliner=outliner,
    )

    assert result.topics[0].degraded_slides == [1]


def test_schema_violation_gets_one_repair_then_degrades():
    notes = [note(1), note(2)]
    outliner = FakeOutliner(
        schemas.GroupingDraft(topics=[topic("A", [1, 2]), topic("B", [2])])
    )

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=[],
        superseded=[],
        outliner=outliner,
    )

    assert outliner.repair_called is True
    assert len(result.topics) == 1
    assert result.topics[0].slides == [1, 2]
    assert result.unassigned == []


def test_invalid_topic_reuse_gets_one_repair_then_degrades_to_unassigned():
    notes = [note(1)]
    outliner = FakeOutliner(
        schemas.GroupingDraft(
            topics=[
                schemas.TopicAssignmentDraft(
                    name="Almost Existing",
                    slides=[1],
                    is_new=False,
                    created_reason=None,
                )
            ]
        )
    )

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=["Existing"],
        superseded=[],
        outliner=outliner,
    )

    assert outliner.repair_called is True
    assert result.unassigned == [1]
    assert result.topics == []


def test_deck_over_twelve_topics_keeps_them_and_sets_flag():
    notes = [note(slide) for slide in range(1, 14)]
    outliner = FakeOutliner(
        schemas.GroupingDraft(
            topics=[topic(f"T{slide}", [slide]) for slide in range(1, 14)]
        )
    )

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=[],
        superseded=[],
        outliner=outliner,
    )

    assert len(result.topics) == 13
    assert result.topic_cap_exceeded is True


def test_run_writes_outlines_for_both_paths(tmp_path):
    run_dir = tmp_path / "run"
    for path_kind in ("image", "text"):
        paths.write_model(paths.page_note(run_dir, path_kind, 1), note(1))
    outliner = FakeOutliner(schemas.GroupingDraft(topics=[topic("A", [1])]))

    outline.outline_run(run_dir, deck_slug="deck", superseded=[], outliner=outliner)

    image = schemas.Outline.model_validate(paths.read_json(paths.outline_file(run_dir, "image")))
    text = schemas.Outline.model_validate(paths.read_json(paths.outline_file(run_dir, "text")))
    assert image.path == schemas.PathKind.image
    assert text.path == schemas.PathKind.text


class TestRerunningOutlineReplacesItsUsageRowRatherThanAppending:
    """Issue #31, the defect moved in from #32: a second `outline_run` call
    used to append a second `stage_usage` row for "outline" and add its cost
    on top of the first, roughly doubling the reported cost of a stage that
    just reprocesses the same notes.
    """

    def a_manifest(self) -> schemas.Manifest:
        return schemas.Manifest(
            schema_version=1,
            subject_slug="engr-689",
            deck_slug="deck",
            deck_sha256="a" * 64,
            deck_filename="deck.pdf",
            run_timestamp="2026-08-20T12-00-00Z",
            started_at="2026-08-20T12-00-00Z",
            ended_at="2026-08-20T12-00-00Z",
            model="model",
            prompt_version="p",
            dpi=150,
            preflight=schemas.Preflight(
                readable=True,
                page_count=1,
                text_native_pages=1,
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
                schemas.PathStats(path=schemas.PathKind.image, completed_stages=["render"]),
                schemas.PathStats(path=schemas.PathKind.text, completed_stages=["render"]),
            ],
            stage_usage=[schemas.StageUsage(stage="render")],
            total_cost_usd=0.0,
        )

    def test_a_second_run_replaces_the_first_runs_outline_usage_row(self, tmp_path):
        run_dir = tmp_path / "run"
        paths.write_model(paths.manifest_file(run_dir), self.a_manifest())
        for path_kind in ("image", "text"):
            paths.write_model(paths.page_note(run_dir, path_kind, 1), note(1))

        first_outliner = FakeOutliner(schemas.GroupingDraft(topics=[topic("A", [1])]))
        first_outliner.usage = schemas.StageUsage(
            stage="outline", calls=2, cost_usd=0.50
        )
        outline.outline_run(run_dir, deck_slug="deck", superseded=[], outliner=first_outliner)

        second_outliner = FakeOutliner(schemas.GroupingDraft(topics=[topic("A", [1])]))
        second_outliner.usage = schemas.StageUsage(
            stage="outline", calls=2, cost_usd=0.60
        )
        outline.outline_run(run_dir, deck_slug="deck", superseded=[], outliner=second_outliner)

        manifest = schemas.Manifest.model_validate(
            paths.read_json(paths.manifest_file(run_dir))
        )
        outline_rows = [item for item in manifest.stage_usage if item.stage == "outline"]
        assert len(outline_rows) == 1
        assert outline_rows[0].cost_usd == 0.60
        assert manifest.total_cost_usd == 0.60


def test_run_loads_existing_topics_from_subject_profile_and_updates_manifest(tmp_path):
    layout = paths.Layout(tmp_path)
    memory.create_subject("ENGR 689", layout)
    run_dir = layout.run_dir("engr-689", "deck", "2026-08-20T12-00-00Z")
    manifest = schemas.Manifest(
        schema_version=1,
        subject_slug="engr-689",
        deck_slug="deck",
        deck_sha256="a" * 64,
        deck_filename="deck.pdf",
        run_timestamp="2026-08-20T12-00-00Z",
        started_at="2026-08-20T12-00-00Z",
        ended_at="2026-08-20T12-00-00Z",
        model="model",
        prompt_version="p",
        dpi=150,
        preflight=schemas.Preflight(
            readable=True,
            page_count=1,
            text_native_pages=1,
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
            schemas.PathStats(path=schemas.PathKind.image, completed_stages=["render", "page_reader"]),
            schemas.PathStats(path=schemas.PathKind.text, completed_stages=["render", "page_reader"]),
        ],
        stage_usage=[schemas.StageUsage(stage="render")],
        total_cost_usd=0,
    )
    paths.write_model(paths.manifest_file(run_dir), manifest)
    paths.write_model(paths.page_note(run_dir, "image", 1), note(1))
    paths.write_model(paths.page_note(run_dir, "text", 1), note(1))
    paths.write_model(
        layout.profile_file("engr-689"),
        schemas.Profile(
            schema_version=1,
            subject_slug="engr-689",
            topics=[
                schemas.TopicRecord(
                    name="Existing",
                    first_seen_deck="old",
                    decks=["old"],
                )
            ],
        ),
    )

    class ExistingTopicOutliner(FakeOutliner):
        def __init__(self) -> None:
            super().__init__(
                schemas.GroupingDraft(topics=[topic("Existing", [1], is_new=False)])
            )
            self.seen_existing_topics: list[list[str]] = []

        def group(
            self,
            notes: list[schemas.SlideNote],
            existing_topics: list[str],
        ) -> schemas.GroupingDraft:
            self.seen_existing_topics.append(existing_topics)
            return super().group(notes, existing_topics)

    outliner = ExistingTopicOutliner()

    outline.outline_run(
        run_dir,
        deck_slug="deck",
        superseded=[],
        subject_slug="engr-689",
        layout=layout,
        outliner=outliner,
    )

    manifest_after = schemas.Manifest.model_validate(
        paths.read_json(paths.manifest_file(run_dir))
    )
    assert outliner.seen_existing_topics == [["Existing"], ["Existing"]]
    assert all("outline" in stat.completed_stages for stat in manifest_after.paths)


def test_run_refuses_an_unregistered_subject_before_grouping(tmp_path):
    layout = paths.Layout(tmp_path)
    run_dir = layout.run_dir("engr-689", "deck", "2026-08-20T12-00-00Z")
    for path_kind in ("image", "text"):
        paths.write_model(paths.page_note(run_dir, path_kind, 1), note(1))

    with pytest.raises(memory.UnknownSubject):
        outline.outline_run(
            run_dir,
            deck_slug="deck",
            superseded=[],
            subject_slug="engr-689",
            layout=layout,
            outliner=FakeOutliner(
                schemas.GroupingDraft(topics=[topic("A", [1])])
            ),
        )


def test_one_slide_pair_consumes_one_candidate_slot_whatever_proposed_it():
    notes = [
        note(slide, title="Same", concepts=["A"])
        for slide in range(1, 5)
    ]

    proposal = outline.propose_bridge_candidates(notes, cap=30)

    pairs = [candidate.slides for candidate in proposal.candidates]
    assert len(pairs) == len(set(pairs))
    assert proposal.proposed == len(set(pairs))
    assert [candidate.index for candidate in proposal.candidates] == list(
        range(len(proposal.candidates))
    )


def test_candidates_are_proposed_from_the_back_of_a_full_length_deck():
    notes = [
        note(slide, title="Same", concepts=["A"])
        for slide in range(1, 67)
    ]

    proposal = outline.propose_bridge_candidates(notes, cap=30)

    assert len(proposal.candidates) == 30
    assert proposal.proposed == 65
    last_third = [
        candidate for candidate in proposal.candidates if candidate.slides[0] > 44
    ]
    assert last_third, "the cap truncated the back two thirds of the deck away"


def test_candidates_proposed_records_the_pre_cap_total():
    notes = [
        note(slide, title="Same", concepts=["A"])
        for slide in range(1, 20)
    ]

    proposal = outline.propose_bridge_candidates(notes, cap=5)

    assert len(proposal.candidates) == 5
    assert proposal.proposed == 18


def test_outline_records_the_pre_cap_candidate_total(monkeypatch):
    monkeypatch.setattr(outline.config, "CANDIDATE_CAP", 3)
    notes = [note(slide, title="Same", concepts=["A"]) for slide in range(1, 12)]
    outliner = FakeOutliner(
        schemas.GroupingDraft(topics=[topic("A", list(range(1, 12)))])
    )

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=[],
        superseded=[],
        outliner=outliner,
    )

    assert result.candidate_cap == 3
    assert result.candidates_proposed == 10


def test_topic_slides_and_degraded_slides_are_sorted_ascending():
    notes = [
        note(1, reader_note="low confidence"),
        note(3),
        note(5, reader_note="low confidence"),
    ]
    outliner = FakeOutliner(schemas.GroupingDraft(topics=[topic("A", [5, 1, 3])]))

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=[],
        superseded=[],
        outliner=outliner,
    )

    assert result.topics[0].slides == [1, 3, 5]
    assert result.topics[0].degraded_slides == [1, 5]


def test_invalid_topics_are_degraded_to_unassigned_instead_of_emitted():
    notes = [note(1), note(2)]
    outliner = FakeOutliner(
        schemas.GroupingDraft(
            topics=[
                schemas.TopicAssignmentDraft(
                    name="Invented", slides=[1], is_new=False, created_reason=None
                ),
                topic("Real", [2]),
            ]
        )
    )

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=["Real"],
        superseded=[],
        outliner=outliner,
    )

    assert [(item.name, item.slides) for item in result.topics] == [("Real", [2])]
    assert result.unassigned == [1]


def test_topics_that_lose_all_slides_are_not_emitted():
    notes = [note(1), note(2)]
    outliner = FakeOutliner(
        schemas.GroupingDraft(
            topics=[topic("First", [1]), topic("Second", [1, 2])]
        )
    )

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=[],
        superseded=[],
        outliner=outliner,
    )

    assert [(item.name, item.slides) for item in result.topics] == [
        ("First", [1]),
        ("Second", [2]),
    ]


def test_question_budget_never_allocates_to_an_empty_topic():
    topics = [
        schemas.OutlineTopic(
            name="Empty", slides=[], is_new=True, created_reason="new"
        ),
        schemas.OutlineTopic(
            name="Real", slides=[1], is_new=True, created_reason="new"
        ),
    ]

    budget, untested = outline.allocate_question_budget(
        topics, has_bridged_facts=False, total_questions=3, max_per_topic=3
    )

    assert budget == [("Real", 3)]
    assert untested == []


def test_topics_are_ordered_by_first_assigned_slide_not_first_drafted_slide():
    notes = [note(1), note(2), note(3), note(20)]
    outliner = FakeOutliner(
        schemas.GroupingDraft(
            topics=[
                topic("Opening", [1]),
                topic("Late", [1, 20]),
                topic("Middle", [2, 3]),
            ]
        )
    )

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=[],
        superseded=[],
        outliner=outliner,
    )

    assert outliner.repair_called is True
    assert [item.name for item in result.topics] == ["Opening", "Middle", "Late"]
    assert [item.slides for item in result.topics] == [[1], [2, 3], [20]]


def test_a_note_that_will_not_parse_is_recorded_rather_than_shrinking_the_deck(tmp_path):
    run_dir = tmp_path / "run"
    for path_kind in ("image", "text"):
        paths.write_model(paths.page_note(run_dir, path_kind, 1), note(1))
        paths.write_model(paths.page_note(run_dir, path_kind, 2), note(2))
        paths.page_note(run_dir, path_kind, 3).write_text(
            '{"slide_number": 3, "page_ro', encoding="utf-8"
        )
    outliner = FakeOutliner(schemas.GroupingDraft(topics=[topic("A", [1, 2])]))

    outline.outline_run(run_dir, deck_slug="deck", superseded=[], outliner=outliner)

    result = schemas.Outline.model_validate(
        paths.read_json(paths.outline_file(run_dir, "image"))
    )
    assert result.unreadable_notes == [3]


def test_a_note_that_violates_the_schema_is_recorded_as_unreadable(tmp_path):
    run_dir = tmp_path / "run"
    for path_kind in ("image", "text"):
        paths.write_model(paths.page_note(run_dir, path_kind, 1), note(1))
        paths.page_note(run_dir, path_kind, 4).write_text(
            '{"slide_number": 4}', encoding="utf-8"
        )
    outliner = FakeOutliner(schemas.GroupingDraft(topics=[topic("A", [1])]))

    outline.outline_run(run_dir, deck_slug="deck", superseded=[], outliner=outliner)

    result = schemas.Outline.model_validate(
        paths.read_json(paths.outline_file(run_dir, "image"))
    )
    assert result.unreadable_notes == [4]


def test_an_outline_over_zero_notes_makes_no_model_call():
    outliner = FakeOutliner(schemas.GroupingDraft(topics=[]))

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=[],
        existing_topics=[],
        superseded=[],
        outliner=outliner,
    )

    assert outliner.group_calls == 0
    assert outliner.confirm_calls == 0
    assert result.topics == []
    assert result.question_budget == []


def test_bridge_confirmation_is_skipped_when_no_candidate_was_proposed():
    notes = [note(1, title="One"), note(3, title="Three")]
    outliner = FakeOutliner(schemas.GroupingDraft(topics=[topic("A", [1, 3])]))

    result = outline.build_outline(
        deck_slug="deck",
        path_kind=schemas.PathKind.image,
        notes=notes,
        existing_topics=[],
        superseded=[],
        outliner=outliner,
    )

    assert outliner.group_calls == 1
    assert outliner.confirm_calls == 0
    assert result.candidates_proposed == 0
    assert result.bridged_facts == []


def test_even_sampling_reaches_the_back_of_the_list():
    """A prefix bias reintroduced inside the sampler is the same defect again."""

    assert outline._even_sample(list(range(60)), 2) == [15, 45]
    assert outline._even_sample(list(range(65)), 30)[-1] > 60
    assert outline._even_sample(list(range(4)), 4) == [0, 1, 2, 3]
    assert outline._even_sample(list(range(4)), 0) == []


def test_a_deck_whose_visual_edges_nearly_fill_the_cap_still_reaches_its_back():
    notes = [note(slide, title="Same", concepts=["A"]) for slide in range(1, 61)]
    for index in range(0, 28):
        notes[index] = note(
            index + 1, title="Same", concepts=["A"], relates_to=[index + 31]
        )

    proposal = outline.propose_bridge_candidates(notes, cap=30)

    assert len(proposal.candidates) == 30
    adjacency_only = [
        candidate
        for candidate in proposal.candidates
        if outline.SIGNAL_VISUAL not in candidate.signals
    ]
    assert adjacency_only
    assert max(candidate.slides[0] for candidate in adjacency_only) > 30


def test_a_note_file_that_is_not_a_slide_note_does_not_abort_the_stage(tmp_path):
    run_dir = tmp_path / "run"
    for path_kind in ("image", "text"):
        paths.write_model(paths.page_note(run_dir, path_kind, 1), note(1))
        (paths.notes_dir(run_dir, path_kind) / "notes.backup.json").write_text(
            "{}", encoding="utf-8"
        )
    outliner = FakeOutliner(schemas.GroupingDraft(topics=[topic("A", [1])]))

    outline.outline_run(run_dir, deck_slug="deck", superseded=[], outliner=outliner)

    result = schemas.Outline.model_validate(
        paths.read_json(paths.outline_file(run_dir, "image"))
    )
    assert result.topics[0].slides == [1]
    assert result.unreadable_notes == []
