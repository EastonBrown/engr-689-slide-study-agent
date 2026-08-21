"""Review-stage behavior at the review writer seam."""

from __future__ import annotations

import pytest

from study_agent import paths, schemas
from study_agent.stages import review


class Reviewer:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.usage = schemas.StageUsage(
            stage="review", calls=len(outputs), input_tokens=10, cost_usd=0.25
        )

    def write(self, context: str) -> str:
        assert "OUTLINE:" in context
        return self.outputs.pop(0)


def outline(path: schemas.PathKind) -> schemas.Outline:
    return schemas.Outline(
        deck_slug="deck",
        path=path,
        topics=[schemas.OutlineTopic(name="Retrieval", slides=[2, 4], is_new=True, created_reason="Test", degraded_slides=[2])],
        skipped=[schemas.SkippedSlide(slide_number=1, page_role=schemas.PageRole.title)],
        superseded=[3],
        bridged_facts=[schemas.BridgedFact(slides=[2, 4], statement="Joined fact", candidate_signals=["adjacent_title"])],
    )


def note(slide: int) -> schemas.SlideNote:
    return schemas.SlideNote(
        slide_number=slide,
        page_role=schemas.PageRole.content,
        title="Topic",
        reading="Reading",
        visuals=[],
        concepts=[],
        verbatim_spans=[],
        reader_note="degraded" if slide == 2 else None,
    )


def write_inputs(run_dir) -> None:
    for kind in schemas.PathKind:
        paths.write_model(paths.outline_file(run_dir, kind.value), outline(kind))
        paths.write_model(paths.page_note(run_dir, kind.value, 2), note(2))
        paths.write_model(paths.page_note(run_dir, kind.value, 3), note(3))
        paths.write_model(paths.page_note(run_dir, kind.value, 4), note(4))
    paths.write_model(
        paths.manifest_file(run_dir),
        schemas.Manifest(
            schema_version=1,
            subject_slug="subject",
            deck_slug="deck",
            deck_sha256="a" * 64,
            deck_filename="deck.pdf",
            run_timestamp="2026-08-20T12:00:00Z",
            started_at="2026-08-20T12:00:00Z",
            model="claude-opus-5",
            prompt_version="test",
            dpi=150,
            preflight=schemas.Preflight(
                readable=True, page_count=4, text_native_pages=4, text_native_fraction=1,
                image_only=False, page_width_px=1, page_height_px=1, downscaled=False,
                buildup_detection_ran=True, superseded_count=1, superseded=[3],
            ),
            paths=[schemas.PathStats(path=kind, completed_stages=["outline"]) for kind in schemas.PathKind],
        ),
    )


def test_review_run_writes_both_reviews_rewrites_superseded_citations_and_accounts(tmp_path):
    run_dir = tmp_path / "run"
    write_inputs(run_dir)
    writer = Reviewer([
        "## Retrieval\nClaim [slide 2].\n\n## Bridged facts\nJoined [slides 3, 4].",
        "## Retrieval\nClaim [slide 2].",
    ])

    review.review_run(run_dir, reviewer=writer)

    assert "[slides 4, 4]" in paths.review_file(run_dir, "image").read_text()
    assert "degraded read" in paths.review_file(run_dir, "image").read_text()
    assert paths.review_file(run_dir, "text").is_file()
    manifest = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    assert all("review" in stat.completed_stages for stat in manifest.paths)
    assert manifest.stage_usage[0].stage == "review"
    assert manifest.total_cost_usd == pytest.approx(0.25)


def test_review_rejects_citation_to_skipped_slide(tmp_path):
    run_dir = tmp_path / "run"
    write_inputs(run_dir)
    writer = Reviewer(["## Retrieval\nClaim [slide 1].", "## Retrieval\nClaim [slide 2]."])

    with pytest.raises(review.ReviewError, match="uncovered"):
        review.review_run(run_dir, reviewer=writer)
