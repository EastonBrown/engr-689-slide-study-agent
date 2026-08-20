"""Page reader stage behaviour."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from time import sleep

from study_agent import paths, schemas
from study_agent.stages import page_reader


def draft(title: str = "Slide") -> schemas.SlideNoteDraft:
    return schemas.SlideNoteDraft(
        page_role=schemas.PageRole.content,
        title=title,
        reading=f"{title} reading",
        visuals=[],
        concepts=[],
        verbatim_spans=[title],
        reader_note=None,
    )


class FakeReader:
    def __init__(self, outputs: dict[tuple[str, int], schemas.SlideNoteDraft]) -> None:
        self.outputs = outputs
        self.calls: list[page_reader.PageReadRequest] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.lock = Lock()

    def read(self, request: page_reader.PageReadRequest) -> page_reader.PageReadResult:
        with self.lock:
            self.calls.append(request)
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        sleep(0.01)
        with self.lock:
            self.in_flight -= 1
        note = self.outputs[(request.path_kind.value, request.slide_number)]
        return page_reader.PageReadResult(
            note=note,
            usage=schemas.StageUsage(
                stage="page_reader",
                calls=1,
                input_tokens=10,
                output_tokens=5,
                cost_usd=0.000175,
            ),
        )


def write_rendered_page(run_dir: Path, slide_number: int) -> None:
    png = paths.page_render_png(run_dir, slide_number)
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(b"png")
    paths.write_text(paths.page_render_txt(run_dir, slide_number), f"text {slide_number}")


def test_page_reader_writes_notes_for_both_paths_and_updates_manifest(tmp_path):
    run_dir = tmp_path / "run"
    for slide in range(55, 62):
        write_rendered_page(run_dir, slide)
    manifest = schemas.Manifest(
        schema_version=1,
        subject_slug="engr-689",
        deck_slug="day3-principle",
        deck_sha256="a" * 64,
        deck_filename="Day3 Principle.pdf",
        run_timestamp="2026-08-20T12-00-00Z",
        started_at="2026-08-20T12-00-00Z",
        ended_at="2026-08-20T12-01-00Z",
        model="claude-opus-5",
        prompt_version="2026-08-20.1",
        dpi=150,
        preflight=schemas.Preflight(
            readable=True,
            page_count=61,
            text_native_pages=61,
            text_native_fraction=1.0,
            image_only=False,
            page_width_px=2000,
            page_height_px=1125,
            downscaled=False,
            buildup_detection_ran=True,
            superseded_count=0,
            superseded=[],
            long_deck=False,
        ),
        paths=[
            schemas.PathStats(path=schemas.PathKind.image, completed_stages=["render"]),
            schemas.PathStats(path=schemas.PathKind.text, completed_stages=["render"]),
        ],
    )
    paths.write_model(paths.manifest_file(run_dir), manifest)
    outputs = {
        (kind, slide): draft(f"{kind}-{slide}")
        for kind in ("image", "text")
        for slide in range(55, 62)
    }
    reader = FakeReader(outputs)

    page_reader.read_run_pages(
        run_dir,
        reader=reader,
        slide_numbers=range(55, 62),
        max_concurrency=3,
    )

    assert len(list((run_dir / "pages-image").glob("*.json"))) == 7
    assert len(list((run_dir / "pages-text").glob("*.json"))) == 7
    assert schemas.SlideNote.model_validate(
        paths.read_json(paths.page_note(run_dir, "image", 55))
    ).title == "image-55"
    assert reader.max_in_flight <= 3

    updated = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    image_stats = next(stat for stat in updated.paths if stat.path == schemas.PathKind.image)
    text_stats = next(stat for stat in updated.paths if stat.path == schemas.PathKind.text)
    assert image_stats.slides_attempted == 7
    assert image_stats.slides_succeeded == 7
    assert image_stats.reader_notes == 0
    assert "page_reader" in image_stats.completed_stages
    assert text_stats.slides_attempted == 7
    assert updated.stage_usage[0].stage == "page_reader"
    assert updated.stage_usage[0].calls == 14


def test_image_requests_contain_one_image_and_no_extracted_text(tmp_path):
    run_dir = tmp_path / "run"
    write_rendered_page(run_dir, 1)
    reader = FakeReader({("image", 1): draft("image")})

    page_reader.read_run_pages(
        run_dir,
        reader=reader,
        paths_to_read=[schemas.PathKind.image],
        slide_numbers=[1],
    )

    request = reader.calls[0]
    assert request.path_kind == schemas.PathKind.image
    assert request.image_path == paths.page_render_png(run_dir, 1)
    assert request.extracted_text is None


def test_text_requests_contain_text_and_no_image_payload(tmp_path):
    run_dir = tmp_path / "run"
    write_rendered_page(run_dir, 1)
    reader = FakeReader({("text", 1): draft("text")})

    page_reader.read_run_pages(
        run_dir,
        reader=reader,
        paths_to_read=[schemas.PathKind.text],
        slide_numbers=[1],
    )

    request = reader.calls[0]
    assert request.path_kind == schemas.PathKind.text
    assert request.image_path is None
    assert request.extracted_text == "text 1"


class AlwaysFailReader:
    def read(self, request: page_reader.PageReadRequest) -> page_reader.PageReadResult:
        raise page_reader.PageReadFailed("schema validation failed twice")


class AlwaysCrashReader:
    def read(self, request: page_reader.PageReadRequest) -> page_reader.PageReadResult:
        raise RuntimeError("programmer bug")


def test_failed_read_still_writes_a_note_with_reader_note(tmp_path):
    run_dir = tmp_path / "run"
    write_rendered_page(run_dir, 4)

    page_reader.read_run_pages(
        run_dir,
        reader=AlwaysFailReader(),
        paths_to_read=[schemas.PathKind.text],
        slide_numbers=[4],
    )

    note = schemas.SlideNote.model_validate(paths.read_json(paths.page_note(run_dir, "text", 4)))
    assert note.slide_number == 4
    assert note.reader_note == "schema validation failed twice"
    assert note.concepts == []


class FailedWithUsageReader:
    def read(self, request: page_reader.PageReadRequest) -> page_reader.PageReadResult:
        raise page_reader.PageReadFailed(
            "schema validation failed twice",
            schemas.StageUsage(stage="page_reader", calls=3, input_tokens=30),
        )


def test_failed_read_keeps_usage_from_failed_attempts(tmp_path):
    run_dir = tmp_path / "run"
    write_rendered_page(run_dir, 4)
    manifest = schemas.Manifest(
        schema_version=1,
        subject_slug="engr-689",
        deck_slug="day3-principle",
        deck_sha256="a" * 64,
        deck_filename="Day3 Principle.pdf",
        run_timestamp="2026-08-20T12-00-00Z",
        started_at="2026-08-20T12-00-00Z",
        model="claude-opus-5",
        prompt_version="2026-08-20.1",
        dpi=150,
        preflight=schemas.Preflight(
            readable=True,
            page_count=4,
            text_native_pages=4,
            text_native_fraction=1.0,
            image_only=False,
            page_width_px=2000,
            page_height_px=1125,
            downscaled=False,
            buildup_detection_ran=True,
            superseded_count=0,
        ),
    )
    paths.write_model(paths.manifest_file(run_dir), manifest)

    page_reader.read_run_pages(
        run_dir,
        reader=FailedWithUsageReader(),
        paths_to_read=[schemas.PathKind.text],
        slide_numbers=[4],
    )

    updated = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    assert updated.stage_usage[0].calls == 3
    assert updated.stage_usage[0].input_tokens == 30


def test_unexpected_reader_errors_are_not_swallowed(tmp_path):
    run_dir = tmp_path / "run"
    write_rendered_page(run_dir, 4)

    import pytest

    with pytest.raises(RuntimeError, match="programmer bug"):
        page_reader.read_run_pages(
            run_dir,
            reader=AlwaysCrashReader(),
            paths_to_read=[schemas.PathKind.text],
            slide_numbers=[4],
        )


def test_resume_retries_only_existing_reader_notes(tmp_path):
    run_dir = tmp_path / "run"
    for slide in (1, 2):
        write_rendered_page(run_dir, slide)
    clean = schemas.SlideNote(slide_number=1, **draft("clean").model_dump())
    degraded = schemas.SlideNote(
        slide_number=2,
        **draft("degraded").model_copy(update={"reader_note": "bad"}).model_dump(),
    )
    paths.write_model(paths.page_note(run_dir, "image", 1), clean)
    paths.write_model(paths.page_note(run_dir, "image", 2), degraded)
    reader = FakeReader({("image", 2): draft("fixed")})

    page_reader.read_run_pages(
        run_dir,
        reader=reader,
        paths_to_read=[schemas.PathKind.image],
        slide_numbers=[1, 2],
        resume=True,
    )

    assert [call.slide_number for call in reader.calls] == [2]
    assert schemas.SlideNote.model_validate(
        paths.read_json(paths.page_note(run_dir, "image", 2))
    ).reader_note is None


def test_resume_also_reads_missing_notes_because_missing_means_nothing(tmp_path):
    run_dir = tmp_path / "run"
    for slide in (1, 2):
        write_rendered_page(run_dir, slide)
    degraded = schemas.SlideNote(
        slide_number=2,
        **draft("degraded").model_copy(update={"reader_note": "bad"}).model_dump(),
    )
    paths.write_model(paths.page_note(run_dir, "image", 2), degraded)
    reader = FakeReader({("image", 1): draft("new"), ("image", 2): draft("fixed")})

    page_reader.read_run_pages(
        run_dir,
        reader=reader,
        paths_to_read=[schemas.PathKind.image],
        slide_numbers=[1, 2],
        resume=True,
    )

    assert [call.slide_number for call in reader.calls] == [1, 2]
