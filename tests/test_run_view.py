"""The disk-to-screen model behind the interface shell, issue #25.

Every number the interface shows comes from here, and every function here
reads a run directory rather than being handed run state. Streamlit reruns the
whole script on every interaction, so a view that remembered anything would
lose it on the next click.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from study_agent import paths, run_view, schemas


def preflight(page_count: int = 7, **overrides: Any) -> schemas.Preflight:
    fields: dict[str, Any] = dict(
        readable=True,
        page_count=page_count,
        text_native_pages=page_count,
        text_native_fraction=1.0,
        image_only=False,
        page_width_px=2000,
        page_height_px=1125,
        downscaled=False,
        buildup_detection_ran=True,
        superseded_count=0,
        superseded=[],
        long_deck=False,
    )
    fields.update(overrides)
    return schemas.Preflight(**fields)


def write_manifest(run_dir: Path, **overrides: Any) -> schemas.Manifest:
    fields: dict[str, Any] = dict(
        schema_version=1,
        subject_slug="engr-689",
        deck_slug="day3-principle",
        deck_sha256="a" * 64,
        deck_filename="Day3 Principle.pdf",
        run_timestamp="2026-08-20T12-00-00Z",
        started_at="2026-08-20T12-00-00Z",
        ended_at="2026-08-20T12-05-00Z",
        model="claude-opus-5",
        prompt_version="v1",
        dpi=150,
        preflight=preflight(),
        paths=[
            schemas.PathStats(path=schemas.PathKind.image, completed_stages=["render"]),
            schemas.PathStats(path=schemas.PathKind.text, completed_stages=["render"]),
        ],
        stage_usage=[schemas.StageUsage(stage="render")],
        total_cost_usd=0.0,
    )
    fields.update(overrides)
    manifest = schemas.Manifest(**fields)
    paths.write_model(paths.manifest_file(run_dir), manifest)
    return manifest


def write_render_pages(run_dir: Path, count: int = 7) -> None:
    for slide in range(1, count + 1):
        target = paths.page_render_png(run_dir, slide)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"png")
        paths.write_text(paths.page_render_txt(run_dir, slide), f"slide {slide}")


def note(slide: int, reader_note: str | None = None) -> schemas.SlideNote:
    return schemas.SlideNote(
        slide_number=slide,
        page_role=schemas.PageRole.content,
        title=f"Slide {slide}",
        reading="what the slide says",
        visuals=[
            schemas.Visual(
                kind=schemas.VisualKind.diagram,
                description="a block diagram",
                assertion="the encoder feeds the decoder",
                relates_to_slides=[],
            )
        ],
        concepts=[
            schemas.Concept(
                name="attention",
                status=schemas.ConceptStatus.explained_here,
                why_it_matters="it is the mechanism",
            )
        ],
        verbatim_spans=["attention is all you need"],
        reader_note=reader_note,
    )


def write_notes(
    run_dir: Path,
    path_kind: str,
    slides: list[int],
    degraded: list[int] | None = None,
) -> None:
    degraded = degraded or []
    for slide in slides:
        paths.write_model(
            paths.page_note(run_dir, path_kind, slide),
            note(slide, "page image missing" if slide in degraded else None),
        )


def write_outline(run_dir: Path, path_kind: str) -> None:
    outline = schemas.Outline(
        deck_slug="day3-principle",
        path=schemas.PathKind(path_kind),
        topics=[
            schemas.OutlineTopic(
                name="Encoders", slides=[1, 2], is_new=True, created_reason="not seen before"
            ),
            schemas.OutlineTopic(name="Attention", slides=[3, 4], is_new=False),
        ],
        skipped=[schemas.SkippedSlide(slide_number=5, page_role=schemas.PageRole.title)],
        question_budget=[("Encoders", 6), ("Attention", 4)],
    )
    paths.write_model(paths.outline_file(run_dir, path_kind), outline)


# --- The seven stage boxes --------------------------------------------------


def test_seven_stages_in_screen_order(tmp_path):
    views = run_view.stage_views(tmp_path)

    assert [view.key for view in views] == list(run_view.STAGE_KEYS)
    assert len(views) == 7


def test_a_stage_with_no_artifacts_is_pending_not_a_failure(tmp_path):
    write_render_pages(tmp_path)
    write_manifest(tmp_path)

    views = run_view.stage_views(tmp_path)
    by_key = {view.key: view for view in views}

    assert by_key[run_view.STAGE_RENDER].state is run_view.StageState.complete
    for key in (
        run_view.STAGE_PAGE_READER_IMAGE,
        run_view.STAGE_PAGE_READER_TEXT,
        run_view.STAGE_OUTLINE,
        run_view.STAGE_RESEARCH,
        run_view.STAGE_REVIEW,
        run_view.STAGE_QUIZ,
    ):
        assert by_key[key].state is run_view.StageState.pending
    assert all(view.state is not run_view.StageState.failed for view in views)


def test_a_run_directory_that_does_not_exist_renders_seven_pending_boxes(tmp_path):
    views = run_view.stage_views(tmp_path / "no-such-run")

    assert all(view.state is run_view.StageState.pending for view in views)


def test_notes_on_disk_without_the_completion_mark_read_as_running(tmp_path):
    write_render_pages(tmp_path)
    write_manifest(tmp_path)
    write_notes(tmp_path, "image", [1, 2, 3])

    by_key = {view.key: view for view in run_view.stage_views(tmp_path)}

    assert by_key[run_view.STAGE_PAGE_READER_IMAGE].state is run_view.StageState.running
    assert by_key[run_view.STAGE_PAGE_READER_TEXT].state is run_view.StageState.pending


def test_a_completed_page_read_summarises_from_the_manifest(tmp_path):
    write_render_pages(tmp_path)
    write_manifest(
        tmp_path,
        paths=[
            schemas.PathStats(
                path=schemas.PathKind.image,
                slides_attempted=7,
                slides_succeeded=6,
                reader_notes=1,
                completed_stages=["render", "page_reader"],
            ),
            schemas.PathStats(path=schemas.PathKind.text, completed_stages=["render"]),
        ],
    )
    write_notes(tmp_path, "image", [1, 2, 3, 4, 5, 6, 7], degraded=[3])

    by_key = {view.key: view for view in run_view.stage_views(tmp_path)}
    image = by_key[run_view.STAGE_PAGE_READER_IMAGE]

    assert image.state is run_view.StageState.complete
    assert "6 of 7" in image.summary
    assert "1 degraded" in image.summary
    assert any("slide 3" in line for line in image.detail)


def test_the_outline_box_replays_its_topics_from_disk(tmp_path):
    write_render_pages(tmp_path)
    write_manifest(
        tmp_path,
        paths=[
            schemas.PathStats(
                path=schemas.PathKind.image,
                completed_stages=["render", "page_reader", "outline"],
            ),
            schemas.PathStats(path=schemas.PathKind.text, completed_stages=["render"]),
        ],
    )
    write_outline(tmp_path, "image")

    by_key = {view.key: view for view in run_view.stage_views(tmp_path)}
    outline = by_key[run_view.STAGE_OUTLINE]

    assert outline.state is run_view.StageState.complete
    assert "2 topics" in outline.summary
    assert "1 matched" in outline.summary
    assert "1 new" in outline.summary
    assert any("Encoders" in line for line in outline.detail)


def test_the_render_box_names_the_preflight_findings(tmp_path):
    write_render_pages(tmp_path)
    write_manifest(tmp_path, preflight=preflight(superseded_count=1, superseded=[4]))

    by_key = {view.key: view for view in run_view.stage_views(tmp_path)}
    render_box = by_key[run_view.STAGE_RENDER]

    assert "7 pages" in render_box.summary
    assert "150" in render_box.summary
    assert any("4" in line and "superseded" in line for line in render_box.detail)


# --- The run summary --------------------------------------------------------


def test_run_summary_reads_every_number_from_the_manifest(tmp_path):
    write_render_pages(tmp_path)
    write_manifest(
        tmp_path,
        preflight=preflight(superseded_count=2, superseded=[4, 5], image_only=True),
        paths=[
            schemas.PathStats(
                path=schemas.PathKind.image,
                slides_attempted=7,
                slides_succeeded=6,
                reader_notes=1,
                research_lookups=4,
                research_cache_hits=2,
                completed_stages=["render", "page_reader"],
            ),
            schemas.PathStats(
                path=schemas.PathKind.text,
                slides_attempted=7,
                slides_succeeded=7,
                completed_stages=["render", "page_reader"],
            ),
        ],
        stage_usage=[
            schemas.StageUsage(stage="render"),
            schemas.StageUsage(stage="page_reader", calls=14, cost_usd=0.42),
        ],
        total_cost_usd=0.42,
    )
    write_outline(tmp_path, "image")

    summary = run_view.run_summary(tmp_path)

    assert summary is not None
    assert summary.slides_read == 6
    assert summary.slides_total == 7
    assert summary.degraded == 1
    assert summary.text_slides_read == 7
    assert summary.topics_matched == 1
    assert summary.topics_new == 1
    assert summary.research_lookups == 4
    assert summary.research_cache_hits == 2
    assert summary.cost_usd == pytest.approx(0.42)
    assert summary.superseded_count == 2
    assert summary.image_only is True
    assert summary.deck_filename == "Day3 Principle.pdf"


def test_run_summary_is_none_without_a_manifest(tmp_path):
    assert run_view.run_summary(tmp_path) is None


def test_run_summary_reports_no_topics_before_the_outline_runs(tmp_path):
    write_render_pages(tmp_path)
    write_manifest(tmp_path)

    summary = run_view.run_summary(tmp_path)

    assert summary is not None
    assert summary.topics_matched == 0
    assert summary.topics_new == 0
    assert summary.outline_ran is False


# --- Failures and degraded reads --------------------------------------------


def test_failures_carry_the_page_image_beside_the_reader_note(tmp_path):
    write_render_pages(tmp_path)
    write_manifest(tmp_path)
    write_notes(tmp_path, "image", [1, 2, 3], degraded=[2])
    write_notes(tmp_path, "text", [1, 2, 3])

    found = run_view.failures(tmp_path)

    assert [(item.path, item.slide_number) for item in found] == [("image", 2)]
    assert found[0].reader_note == "page image missing"
    assert found[0].image_path == paths.page_render_png(tmp_path, 2)


def test_a_failure_whose_page_image_is_missing_reports_no_image(tmp_path):
    write_manifest(tmp_path)
    write_notes(tmp_path, "image", [9], degraded=[9])

    found = run_view.failures(tmp_path)

    assert found[0].image_path is None


def test_failures_are_ordered_by_slide_then_path(tmp_path):
    write_render_pages(tmp_path)
    write_manifest(tmp_path)
    write_notes(tmp_path, "image", [1, 3], degraded=[1, 3])
    write_notes(tmp_path, "text", [1], degraded=[1])

    found = run_view.failures(tmp_path)

    assert [(item.path, item.slide_number) for item in found] == [
        ("image", 1),
        ("text", 1),
        ("image", 3),
    ]


def test_an_unparseable_note_is_reported_as_a_failure_not_skipped(tmp_path):
    write_manifest(tmp_path)
    target = paths.page_note(tmp_path, "image", 4)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{ truncated", encoding="utf-8")

    found = run_view.failures(tmp_path)

    assert [(item.path, item.slide_number) for item in found] == [("image", 4)]
    assert "would not parse" in (found[0].reader_note or "")


# --- Finding the run to show ------------------------------------------------


def test_latest_run_is_the_newest_run_across_every_deck_in_the_subject(tmp_path):
    layout = paths.Layout(tmp_path)
    older = layout.run_dir("engr-689", "day1-tool", "2026-08-20T10-00-00Z")
    newer = layout.run_dir("engr-689", "day3-principle", "2026-08-20T12-00-00Z")
    other = layout.run_dir("cs-101", "other-deck", "2026-08-20T23-00-00Z")
    for run_dir in (older, newer, other):
        run_dir.mkdir(parents=True)
        write_manifest(run_dir)

    assert run_view.latest_run(layout, "engr-689") == newer
    assert run_view.latest_run(layout, "cs-101") == other
    assert run_view.latest_run(layout, "no-such-subject") is None


def test_a_directory_without_a_manifest_is_not_offered_as_a_run(tmp_path):
    layout = paths.Layout(tmp_path)
    empty = layout.run_dir("engr-689", "day3-principle", "2026-08-20T12-00-00Z")
    empty.mkdir(parents=True)

    assert run_view.latest_run(layout, "engr-689") is None
