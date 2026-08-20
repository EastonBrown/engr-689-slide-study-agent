"""Scripted verbatim span scoring."""

from __future__ import annotations

import subprocess
import sys

from study_agent import paths, schemas

from eval import score_spans


def write_note(run_dir, slide_number: int, spans: list[str]) -> None:
    note = schemas.SlideNote(
        slide_number=slide_number,
        page_role=schemas.PageRole.content,
        title="Slide",
        reading="A slide.",
        visuals=[],
        concepts=[],
        verbatim_spans=spans,
        reader_note=None,
    )
    paths.write_model(paths.page_note(run_dir, "image", slide_number), note)


def test_score_spans_reports_passes_failures_and_checked_slides(tmp_path):
    run_dir = tmp_path / "run"
    paths.write_text(paths.page_render_txt(run_dir, 1), "alpha beta gamma")
    paths.write_text(paths.page_render_txt(run_dir, 2), "delta")
    paths.write_text(paths.page_render_txt(run_dir, 3), "empty")
    write_note(run_dir, 1, ["alpha", "missing"])
    write_note(run_dir, 2, ["delta"])
    write_note(run_dir, 3, [])

    result = score_spans.score_run(run_dir)

    assert result.slides_checked == 3
    assert result.spans_checked == 3
    assert result.passed == 2
    assert result.failed == 1
    assert result.failures == [score_spans.SpanFailure(slide_number=1, span="missing")]


def test_score_spans_reads_image_path_only(tmp_path):
    run_dir = tmp_path / "run"
    paths.write_text(paths.page_render_txt(run_dir, 1), "alpha")
    write_note(run_dir, 1, ["alpha"])
    text_note = schemas.SlideNote(
        slide_number=1,
        page_role=schemas.PageRole.content,
        title="Text",
        reading="A slide.",
        visuals=[],
        concepts=[],
        verbatim_spans=["not in alpha"],
        reader_note=None,
    )
    paths.write_model(paths.page_note(run_dir, "text", 1), text_note)

    result = score_spans.score_run(run_dir)

    assert result.failed == 0
    assert result.spans_checked == 1


def test_cli_names_failing_spans_by_slide(tmp_path, capsys):
    run_dir = tmp_path / "run"
    paths.write_text(paths.page_render_txt(run_dir, 7), "visible")
    write_note(run_dir, 7, ["not visible"])

    code = score_spans.main([str(run_dir)])

    captured = capsys.readouterr()
    assert code == 1
    assert "passes: 0" in captured.out
    assert "failures: 1" in captured.out
    assert "slide 7: not visible" in captured.out


def test_documented_script_entrypoint_works_from_repo_root(tmp_path):
    run_dir = tmp_path / "run"
    paths.write_text(paths.page_render_txt(run_dir, 1), "visible")
    write_note(run_dir, 1, ["visible"])

    result = subprocess.run(
        [sys.executable, "eval/score_spans.py", str(run_dir)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "passes: 1" in result.stdout
