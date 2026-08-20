"""The headless render pipeline from issue #16."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from study_agent import paths, pipeline, render, schemas
from study_agent.stages import page_reader


def preflight(page_count: int = 2) -> schemas.Preflight:
    return schemas.Preflight(
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


def fake_render(deck_path: Path, run_dir: Path, dpi: int = 150, log=None):
    del deck_path, dpi
    for slide in range(1, 3):
        paths.write_text(paths.page_render_txt(run_dir, slide), f"slide {slide}")
        paths.page_render_png(run_dir, slide).write_bytes(b"not a real png")
    if log:
        log("rendered 2/2 pages")
    return render.RenderResult(
        preflight=preflight(),
        page_texts=["slide 1", "slide 2"],
        image_paths=[paths.page_render_png(run_dir, 1), paths.page_render_png(run_dir, 2)],
    )


def test_pipeline_writes_a_run_directory_manifest_and_latest(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "render_deck", fake_render)
    deck = tmp_path / "Day3 Principle.pdf"
    deck.write_bytes(b"pdf bytes")
    layout = paths.Layout(tmp_path)

    result = pipeline.run_render_pipeline(
        deck,
        "engr-689",
        layout=layout,
        started_at=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert result.run_dir == (
        tmp_path
        / "runs"
        / "engr-689"
        / "day3-principle"
        / "2026-08-20T12-00-00Z"
    )
    assert paths.page_render_png(result.run_dir, 1).is_file()
    assert (
        paths.page_render_txt(result.run_dir, 2).read_text(encoding="utf-8")
        == "slide 2"
    )
    assert layout.read_latest("engr-689", "day3-principle") == "2026-08-20T12-00-00Z"

    manifest = schemas.Manifest.model_validate(
        paths.read_json(paths.manifest_file(result.run_dir))
    )
    assert manifest.subject_slug == "engr-689"
    assert manifest.deck_slug == "day3-principle"
    assert manifest.deck_filename == "Day3 Principle.pdf"
    assert manifest.preflight.page_count == 2
    assert manifest.stage_usage[0].stage == "render"
    assert manifest.stage_usage[0].cost_usd == 0.0
    assert {stat.path for stat in manifest.paths} == {
        schemas.PathKind.image,
        schemas.PathKind.text,
    }
    assert all(stat.completed_stages == ["render"] for stat in manifest.paths)


def test_a_rerun_writes_a_new_directory_and_updates_latest(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "render_deck", fake_render)
    deck = tmp_path / "Day3 Principle.pdf"
    deck.write_bytes(b"pdf bytes")
    layout = paths.Layout(tmp_path)

    first = pipeline.run_render_pipeline(
        deck,
        "engr-689",
        layout=layout,
        started_at=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
    )
    second = pipeline.run_render_pipeline(
        deck,
        "engr-689",
        layout=layout,
        started_at=datetime(2026, 8, 20, 12, 0, 1, tzinfo=timezone.utc),
    )

    assert second.run_dir != first.run_dir
    assert first.run_dir.is_dir()
    assert second.run_dir.is_dir()
    assert layout.read_latest("engr-689", "day3-principle") == "2026-08-20T12-00-01Z"


def test_unreadable_deck_refuses_and_does_not_update_latest(tmp_path, monkeypatch):
    def unreadable(deck_path: Path, run_dir: Path, dpi: int = 150, log=None):
        del deck_path, run_dir, dpi, log
        raise render.DeckUnreadable("encrypted.pdf will not open")

    monkeypatch.setattr(render, "render_deck", unreadable)
    deck = tmp_path / "encrypted.pdf"
    deck.write_bytes(b"not really a pdf")
    layout = paths.Layout(tmp_path)

    with pytest.raises(pipeline.PipelineError, match="will not open"):
        pipeline.run_render_pipeline(
            deck,
            "engr-689",
            layout=layout,
            started_at=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
        )

    assert layout.read_latest("engr-689", "encrypted") is None


def test_cli_returns_success_and_prints_the_run_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(render, "render_deck", fake_render)
    deck = tmp_path / "Day1 Tool.pdf"
    deck.write_bytes(b"pdf bytes")

    code = pipeline.main([str(deck), "--subject", "engr-689", "--root", str(tmp_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert "runs" in captured.out
    assert "rendered 2/2 pages" in captured.err


def test_cli_returns_failure_for_a_missing_deck(tmp_path, capsys):
    code = pipeline.main(
        [str(tmp_path / "missing.pdf"), "--subject", "engr-689", "--root", str(tmp_path)]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "deck not found" in captured.err


def test_slide_number_parser_accepts_ranges_and_singletons():
    assert pipeline.parse_slide_numbers("55-57,61") == [55, 56, 57, 61]


class Reader:
    def read(self, request: page_reader.PageReadRequest) -> page_reader.PageReadResult:
        return page_reader.PageReadResult(
            note=schemas.SlideNoteDraft(
                page_role=schemas.PageRole.content,
                title=f"{request.path_kind.value}-{request.slide_number}",
                reading="ok",
                visuals=[],
                concepts=[],
                verbatim_spans=[],
                reader_note=None,
            ),
            usage=schemas.StageUsage(stage="page_reader", calls=1),
        )


def test_pipeline_can_continue_into_page_reader_for_a_slide_slice(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "render_deck", fake_render)
    deck = tmp_path / "Day3 Principle.pdf"
    deck.write_bytes(b"pdf bytes")

    result = pipeline.run_render_pipeline(
        deck,
        "engr-689",
        layout=paths.Layout(tmp_path),
        started_at=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
        read_pages=True,
        slide_numbers=[1, 2],
        reader=Reader(),
    )

    assert paths.page_note(result.run_dir, "image", 1).is_file()
    assert paths.page_note(result.run_dir, "text", 2).is_file()
    image = next(stat for stat in result.manifest.paths if stat.path == schemas.PathKind.image)
    assert "page_reader" in image.completed_stages
