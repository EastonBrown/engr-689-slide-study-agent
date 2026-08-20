"""Review writer stage behaviour."""

from __future__ import annotations

from study_agent import config, paths, schemas
from study_agent.stages import review


def note(
    slide_number: int,
    *,
    role: schemas.PageRole = schemas.PageRole.content,
    reader_note: str | None = None,
) -> schemas.SlideNote:
    return schemas.SlideNote(
        slide_number=slide_number,
        page_role=role,
        title=f"Slide {slide_number}",
        reading=f"Slide {slide_number} reading.",
        visuals=[],
        concepts=[],
        verbatim_spans=[],
        reader_note=reader_note,
    )


def outline(path_kind: schemas.PathKind = schemas.PathKind.image) -> schemas.Outline:
    return schemas.Outline(
        deck_slug="deck",
        path=path_kind,
        topics=[
            schemas.OutlineTopic(
                name="First",
                slides=[2],
                is_new=True,
                created_reason="new",
            ),
            schemas.OutlineTopic(
                name="Second",
                slides=[3],
                is_new=True,
                created_reason="new",
                degraded_slides=[3],
            ),
        ],
        skipped=[schemas.SkippedSlide(slide_number=1, page_role=schemas.PageRole.title)],
        superseded=[4],
        unassigned=[],
        bridged_facts=[
            schemas.BridgedFact(
                slides=[4, 5],
                statement="A bridge.",
                from_visuals=[],
                candidate_signal="adjacent_title",
            )
        ],
        candidates_proposed=1,
        candidate_cap=30,
        topic_cap_exceeded=False,
        question_budget=[("First", 5), ("Second", 5)],
    )


def cache_entry(concept: str = "RAG") -> schemas.CacheEntry:
    return schemas.CacheEntry(
        query=concept,
        normalized_query=concept.lower(),
        asked_at="2026-08-20T12:00:00Z",
        model=config.MODEL_ID,
        prompt_version=config.PROMPT_VERSION,
        concept=concept,
        answer="External explanation.",
        citations=[schemas.Citation(title="Source", url="https://example.com")],
    )


class FakeWriter:
    def __init__(self, markdown: str) -> None:
        self.markdown = markdown
        self.requests: list[review.ReviewRequest] = []

    def write(self, request: review.ReviewRequest) -> review.ReviewWriteResult:
        self.requests.append(request)
        return review.ReviewWriteResult(
            markdown=self.markdown,
            usage=schemas.StageUsage(stage="review", calls=1, input_tokens=10, cost_usd=0.2),
        )


def test_review_writes_both_paths_and_updates_manifest(tmp_path):
    run_dir = tmp_path / "run"
    paths.write_model(paths.manifest_file(run_dir), manifest())
    for path_kind in ("image", "text"):
        paths.write_model(
            paths.outline_file(run_dir, path_kind),
            outline(schemas.PathKind(path_kind)),
        )
        paths.write_model(paths.page_note(run_dir, path_kind, 2), note(2))
        paths.write_model(paths.page_note(run_dir, path_kind, 3), note(3, reader_note="blurred"))
    paths.write_model(paths.run_research_path_dir(run_dir, "image") / "rag.json", cache_entry())
    paths.write_model(paths.run_research_path_dir(run_dir, "text") / "rag.json", cache_entry("TextRAG"))

    writer = FakeWriter("# First\nClaim [slide 2]\n# Second\nClaim [slide 3] (degraded: blurred)\n# Bridged Facts\nBridge [slide 5]\n# Research\nResearch-derived: fact [Source](https://example.com)\n")

    review.review_run(run_dir, writer=writer)

    assert paths.review_file(run_dir, "image").is_file()
    assert paths.review_file(run_dir, "text").is_file()
    assert writer.requests[0].research_entries[0].concept == "RAG"
    assert writer.requests[1].research_entries[0].concept == "TextRAG"
    after = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    usage = next(item for item in after.stage_usage if item.stage == "review")
    image = next(stat for stat in after.paths if stat.path == schemas.PathKind.image)
    assert usage.calls == 2
    assert usage.cost_usd == 0.4
    assert image.review_calls == 1
    assert image.review_input_tokens == 10
    assert image.review_cost_usd == 0.2
    assert all("review" in stat.completed_stages for stat in after.paths)


def test_sections_must_match_outline_order():
    markdown = "# Second\nClaim [slide 3]\n# First\nClaim [slide 2]\n"
    errors = review.validate_review_markdown(
        markdown,
        outline=outline(),
        notes_by_slide={2: note(2), 3: note(3)},
        superseded_survivors={},
        research_entries=[],
    )

    assert any("section order" in error for error in errors)


def test_rewrite_citations_replaces_superseded_and_rejects_skipped():
    markdown = "# First\nClaim [slide 4]\nBad [slide 1]\n"

    rewritten = review.rewrite_superseded_citations(markdown, {4: 5})
    errors = review.validate_review_markdown(
        rewritten,
        outline=outline(),
        notes_by_slide={1: note(1, role=schemas.PageRole.title), 2: note(2), 5: note(5)},
        superseded_survivors={4: 5},
        research_entries=[],
    )

    assert "[slide 5]" in rewritten
    assert any("skipped slide 1" in error for error in errors)


def test_degraded_cited_slide_requires_inline_note():
    markdown = "# First\nGood [slide 2]\n# Second\nMissing note [slide 3]\n"
    errors = review.validate_review_markdown(
        markdown,
        outline=outline(),
        notes_by_slide={2: note(2), 3: note(3, reader_note="blurred")},
        superseded_survivors={},
        research_entries=[],
    )

    assert any("degraded slide 3" in error for error in errors)


def test_front_matter_is_rejected_and_research_must_be_marked_with_citation():
    markdown = "---\ntitle: bad\n---\n# First\nClaim [slide 2]\n# Research\nExternal explanation.\n"
    errors = review.validate_review_markdown(
        markdown,
        outline=outline(),
        notes_by_slide={2: note(2), 3: note(3)},
        superseded_survivors={},
        research_entries=[cache_entry()],
    )

    assert "front matter" in errors
    assert any("Research-derived" in error for error in errors)


def test_uncited_claim_is_rejected():
    markdown = "# First\nThis sentence has no citation.\n# Second\nClaim [slide 3]\n"
    errors = review.validate_review_markdown(
        markdown,
        outline=outline(),
        notes_by_slide={2: note(2), 3: note(3)},
        superseded_survivors={},
        research_entries=[],
    )

    assert any("uncited claim" in error for error in errors)


def test_invalid_review_fails_without_writing_or_marking_complete(tmp_path):
    run_dir = tmp_path / "run"
    paths.write_model(paths.manifest_file(run_dir), manifest())
    paths.write_model(paths.outline_file(run_dir, "image"), outline())
    paths.write_model(paths.page_note(run_dir, "image", 2), note(2))
    writer = FakeWriter("# Wrong\nNo citation\n")

    try:
        review.review_run(run_dir, writer=writer)
    except review.ReviewContractError:
        pass
    else:
        raise AssertionError("invalid review did not fail")

    assert not paths.review_file(run_dir, "image").exists()
    after = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    assert all("review" not in stat.completed_stages for stat in after.paths)


def test_superseded_survivor_skips_intermediate_superseded_frames():
    notes = [note(4), note(5), note(6)]

    assert review._survivors_from_notes(notes, [4, 5]) == {4: 6, 5: 6}


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
            page_count=5,
            text_native_pages=5,
            text_native_fraction=1.0,
            image_only=False,
            page_width_px=1,
            page_height_px=1,
            downscaled=False,
            buildup_detection_ran=True,
            superseded_count=1,
            superseded=[4],
        ),
        paths=[
            schemas.PathStats(path=schemas.PathKind.image, completed_stages=["research"]),
            schemas.PathStats(path=schemas.PathKind.text, completed_stages=["research"]),
        ],
        stage_usage=[schemas.StageUsage(stage="render")],
        total_cost_usd=0,
    )
