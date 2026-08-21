"""The headless render pipeline from issue #16."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from study_agent import paths, pipeline, render, schemas
from study_agent.stages import outline, page_reader


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


class Outliner:
    def group(
        self,
        notes: list[schemas.SlideNote],
        existing_topics: list[str],
    ) -> schemas.GroupingDraft:
        del existing_topics
        return schemas.GroupingDraft(
            topics=[
                schemas.TopicAssignmentDraft(
                    name="Topic",
                    slides=[note.slide_number for note in notes],
                    is_new=True,
                    created_reason="new",
                )
            ]
        )

    def confirm_bridges(
        self,
        notes_by_slide: dict[int, schemas.SlideNote],
        candidates: list[outline.BridgeCandidate],
    ) -> schemas.BridgeDraft:
        del notes_by_slide, candidates
        return schemas.BridgeDraft(confirmations=[])

    def repair_grouping(
        self,
        notes: list[schemas.SlideNote],
        existing_topics: list[str],
        grouping: schemas.GroupingDraft,
        violations: list[str],
    ) -> schemas.GroupingDraft:
        del notes, existing_topics, violations
        return grouping


def test_pipeline_can_continue_into_page_reader_for_a_slide_slice(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "render_deck", fake_render)
    monkeypatch.setattr(render, "page_count", lambda _deck: 2)
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


def test_pipeline_can_continue_into_outline_after_page_reader(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "render_deck", fake_render)
    deck = tmp_path / "Day3 Principle.pdf"
    deck.write_bytes(b"pdf bytes")

    result = pipeline.run_render_pipeline(
        deck,
        "engr-689",
        layout=paths.Layout(tmp_path),
        started_at=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
        read_pages=True,
        outline_pages=True,
        reader=Reader(),
        outliner=Outliner(),
    )

    assert paths.outline_file(result.run_dir, "image").is_file()
    assert paths.outline_file(result.run_dir, "text").is_file()
    assert all("outline" in stat.completed_stages for stat in result.manifest.paths)


def test_research_requires_its_page_reader_and_outline_prerequisites(tmp_path):
    deck = tmp_path / "Day3 Principle.pdf"
    deck.write_bytes(b"pdf bytes")

    with pytest.raises(pipeline.PipelineError, match="--research requires"):
        pipeline.run_render_pipeline(deck, "engr-689", research_concepts=True)


class TestASlideSelectionIsCheckedAgainstTheDeck:
    """A slice naming a page the deck does not have is a typo, not a read.

    Left unchecked it reached the reader as a request for a PNG that was never
    rendered, which is the one input the stage cannot do anything useful with.
    Refusing costs nothing and names the mistake.
    """

    def test_a_slide_number_below_one_is_rejected_at_parse_time(self):
        with pytest.raises(pipeline.PipelineError, match="slide numbers start at 1"):
            pipeline.parse_slide_numbers("0,3")

    def test_a_negative_slide_number_is_rejected(self):
        with pytest.raises(pipeline.PipelineError, match="slide numbers start at 1"):
            pipeline.parse_slide_numbers("-4")

    def test_a_range_past_the_end_of_the_deck_is_refused_before_any_work(
        self, tmp_path, monkeypatch
    ):
        def should_not_render(*_args, **_kwargs):
            raise AssertionError("an invalid range must be refused before render")

        monkeypatch.setattr(render, "render_deck", should_not_render)
        monkeypatch.setattr(render, "page_count", lambda _deck: 2)
        deck = tmp_path / "Day3 Principle.pdf"
        deck.write_bytes(b"pdf bytes")
        reader = Reader()

        with pytest.raises(pipeline.PipelineError, match="deck has 2 slides"):
            pipeline.run_render_pipeline(
                deck,
                "engr-689",
                layout=paths.Layout(tmp_path),
                started_at=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
                read_pages=True,
                slide_numbers=[1, 70],
                reader=reader,
            )

        assert not (tmp_path / "runs").exists()

    def test_a_refused_range_creates_no_run_or_latest_pointer(self, tmp_path, monkeypatch):
        monkeypatch.setattr(render, "page_count", lambda _deck: 2)
        deck = tmp_path / "Day3 Principle.pdf"
        deck.write_bytes(b"pdf bytes")
        layout = paths.Layout(tmp_path)

        with pytest.raises(pipeline.PipelineError):
            pipeline.run_render_pipeline(
                deck,
                "engr-689",
                layout=layout,
                started_at=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
                read_pages=True,
                slide_numbers=[70],
                reader=Reader(),
            )

        assert not (tmp_path / "runs").exists()
        assert layout.read_latest("engr-689", "day3-principle") is None

    def test_the_cli_reports_the_refusal_rather_than_a_traceback(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(render, "render_deck", fake_render)
        deck = tmp_path / "Day3 Principle.pdf"
        deck.write_bytes(b"pdf bytes")

        code = pipeline.main(
            [
                str(deck),
                "--subject",
                "engr-689",
                "--root",
                str(tmp_path),
                "--slides",
                "0-3",
            ]
        )

        assert code == 1
        assert "slide numbers start at 1" in capsys.readouterr().err


class TestTheManifestClockCoversTheWholeRun:
    """`ended_at` is the run's duration in the results table.

    Stamped when render finished, it excluded every model stage, which is
    almost all of a run's wall time. A duration that reads as six seconds for a
    run that took ten minutes is worse than no duration at all.
    """

    def test_ended_at_is_stamped_after_the_last_stage_not_after_render(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(render, "render_deck", fake_render)
        deck = tmp_path / "Day3 Principle.pdf"
        deck.write_bytes(b"pdf bytes")

        stamps = iter(["2026-08-20T12-00-01Z", "2026-08-20T12-09-30Z"])
        real = paths.utc_timestamp
        monkeypatch.setattr(
            paths,
            "utc_timestamp",
            lambda moment=None: real(moment) if moment is not None else next(stamps),
        )

        result = pipeline.run_render_pipeline(
            deck,
            "engr-689",
            layout=paths.Layout(tmp_path),
            started_at=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
            read_pages=True,
            outline_pages=True,
            reader=Reader(),
            outliner=Outliner(),
        )

        assert result.manifest.ended_at == "2026-08-20T12-09-30Z"
        on_disk = schemas.Manifest.model_validate(
            paths.read_json(paths.manifest_file(result.run_dir))
        )
        assert on_disk.ended_at == "2026-08-20T12-09-30Z"

    def test_a_render_only_run_still_records_an_end(self, tmp_path, monkeypatch):
        monkeypatch.setattr(render, "render_deck", fake_render)
        deck = tmp_path / "Day3 Principle.pdf"
        deck.write_bytes(b"pdf bytes")

        result = pipeline.run_render_pipeline(
            deck,
            "engr-689",
            layout=paths.Layout(tmp_path),
            started_at=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
        )

        assert result.manifest.ended_at is not None


def test_the_documented_headless_command_runs_from_the_repo_root(tmp_path):
    """The command in the README and docs/spec.md, run the way a person runs it.

    No `PYTHONPATH`, no `cwd` trick: the package is installed by
    `requirements.txt`, and this fails if that install is ever dropped. Every
    other test in this file imports `study_agent` through `pytest.ini`'s
    `pythonpath = src`, which is exactly why none of them caught this.
    """

    import os
    import subprocess
    import sys

    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "-m", "study_agent.pipeline", "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=paths.repo_root(),
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert "--subject" in result.stdout
