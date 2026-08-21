"""Page reader stage behaviour."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from time import sleep

import pytest

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


def a_manifest(page_count: int) -> schemas.Manifest:
    """A post-render manifest, the state the page reader always starts from."""

    return schemas.Manifest(
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
        ),
        paths=[
            schemas.PathStats(path=schemas.PathKind.image, completed_stages=["render"]),
            schemas.PathStats(path=schemas.PathKind.text, completed_stages=["render"]),
        ],
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
            page_count=7,
            text_native_pages=7,
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


class TestASliceOrResumeMergesIntoTheManifestRatherThanOverwriting:
    """Issue #31: a second invocation's counts add to the first's, on disk.

    `_update_manifest` used to record only what the current invocation read,
    so a slice or a resume overwrote the earlier invocation's counts instead
    of merging into them, and a path could be marked complete on a slice that
    covered only part of the deck.
    """

    def test_a_second_slice_adds_to_the_first_slices_counts(self, tmp_path):
        run_dir = tmp_path / "run"
        for slide in (1, 2, 3):
            write_rendered_page(run_dir, slide)
        paths.write_model(paths.manifest_file(run_dir), a_manifest(page_count=3))

        page_reader.read_run_pages(
            run_dir,
            reader=FakeReader({("image", 1): draft("one")}),
            paths_to_read=[schemas.PathKind.image],
            slide_numbers=[1],
        )
        page_reader.read_run_pages(
            run_dir,
            reader=FakeReader({("image", 2): draft("two")}),
            paths_to_read=[schemas.PathKind.image],
            slide_numbers=[2],
        )

        manifest = schemas.Manifest.model_validate(
            paths.read_json(paths.manifest_file(run_dir))
        )
        image = next(
            stat for stat in manifest.paths if stat.path == schemas.PathKind.image
        )
        assert image.slides_attempted == 2
        assert image.slides_succeeded == 2

    def test_a_path_is_complete_only_once_every_slide_of_the_deck_is_attempted(
        self, tmp_path
    ):
        run_dir = tmp_path / "run"
        for slide in (1, 2, 3):
            write_rendered_page(run_dir, slide)
        paths.write_model(paths.manifest_file(run_dir), a_manifest(page_count=3))

        page_reader.read_run_pages(
            run_dir,
            reader=FakeReader({("image", 1): draft("one"), ("image", 2): draft("two")}),
            paths_to_read=[schemas.PathKind.image],
            slide_numbers=[1, 2],
        )
        first = schemas.Manifest.model_validate(
            paths.read_json(paths.manifest_file(run_dir))
        )
        first_image = next(
            stat for stat in first.paths if stat.path == schemas.PathKind.image
        )
        assert "page_reader" not in first_image.completed_stages

        page_reader.read_run_pages(
            run_dir,
            reader=FakeReader({("image", 3): draft("three")}),
            paths_to_read=[schemas.PathKind.image],
            slide_numbers=[3],
        )
        second = schemas.Manifest.model_validate(
            paths.read_json(paths.manifest_file(run_dir))
        )
        second_image = next(
            stat for stat in second.paths if stat.path == schemas.PathKind.image
        )
        assert second_image.slides_attempted == 3
        assert "page_reader" in second_image.completed_stages

    def test_resuming_a_run_with_no_failed_slides_makes_no_model_call(self, tmp_path):
        run_dir = tmp_path / "run"
        for slide in (1, 2):
            write_rendered_page(run_dir, slide)
        clean = schemas.SlideNote(slide_number=1, **draft("one").model_dump())
        also_clean = schemas.SlideNote(slide_number=2, **draft("two").model_dump())
        paths.write_model(paths.page_note(run_dir, "image", 1), clean)
        paths.write_model(paths.page_note(run_dir, "image", 2), also_clean)
        paths.write_model(paths.manifest_file(run_dir), a_manifest(page_count=2))
        reader = FakeReader({})

        page_reader.read_run_pages(
            run_dir,
            reader=reader,
            paths_to_read=[schemas.PathKind.image],
            slide_numbers=[1, 2],
            resume=True,
        )

        assert reader.calls == []
        manifest = schemas.Manifest.model_validate(
            paths.read_json(paths.manifest_file(run_dir))
        )
        image = next(
            stat for stat in manifest.paths if stat.path == schemas.PathKind.image
        )
        assert image.slides_attempted == 2
        assert "page_reader" in image.completed_stages

    def test_a_zero_call_resume_does_not_erase_the_earlier_invocations_cost(
        self, tmp_path
    ):
        """A resume that reads nothing must not look like a free run.

        `_update_manifest` used to replace the `page_reader` stage_usage row
        every call, so a resume that made zero model calls overwrote a real,
        already-paid-for row with a zero-cost one and silently erased it from
        `total_cost_usd`.
        """

        run_dir = tmp_path / "run"
        for slide in (1, 2):
            write_rendered_page(run_dir, slide)
        clean = schemas.SlideNote(slide_number=1, **draft("one").model_dump())
        also_clean = schemas.SlideNote(slide_number=2, **draft("two").model_dump())
        paths.write_model(paths.page_note(run_dir, "image", 1), clean)
        paths.write_model(paths.page_note(run_dir, "image", 2), also_clean)
        manifest = a_manifest(page_count=2).model_copy(
            update={
                "stage_usage": [
                    schemas.StageUsage(
                        stage="page_reader", calls=4, cost_usd=0.70
                    )
                ],
                "total_cost_usd": 0.70,
            }
        )
        paths.write_model(paths.manifest_file(run_dir), manifest)

        page_reader.read_run_pages(
            run_dir,
            reader=FakeReader({}),
            paths_to_read=[schemas.PathKind.image],
            slide_numbers=[1, 2],
            resume=True,
        )

        updated = schemas.Manifest.model_validate(
            paths.read_json(paths.manifest_file(run_dir))
        )
        page_reader_rows = [
            item for item in updated.stage_usage if item.stage == "page_reader"
        ]
        assert len(page_reader_rows) == 1
        assert page_reader_rows[0].cost_usd == 0.70
        assert updated.total_cost_usd == 0.70


class TestAMissingRenderArtifactDegradesRatherThanAborting:
    """Ticket 17's invariant: a missing file never means anything.

    A failed or degraded read still writes its note with `reader_note` set, so
    that the absence of a note file is unambiguous. A read that died on a
    missing PNG used to write nothing and take the whole stage down with it,
    losing every note the other workers had already finished.
    """

    def test_a_slide_with_no_png_writes_a_note_and_the_run_continues(self, tmp_path):
        run_dir = tmp_path / "run"
        for slide in (1, 2):
            write_rendered_page(run_dir, slide)
        paths.page_render_png(run_dir, 2).unlink()

        page_reader.read_run_pages(
            run_dir,
            reader=FakeReader({("image", slide): draft() for slide in (1, 2)}),
            paths_to_read=[schemas.PathKind.image],
        )

        first = schemas.SlideNote.model_validate(
            paths.read_json(paths.page_note(run_dir, "image", 1))
        )
        second = schemas.SlideNote.model_validate(
            paths.read_json(paths.page_note(run_dir, "image", 2))
        )
        assert first.reader_note is None
        assert second.reader_note is not None
        assert "0002.png" in second.reader_note

    def test_the_manifest_is_written_even_though_a_slide_failed(self, tmp_path):
        run_dir = tmp_path / "run"
        for slide in (1, 2):
            write_rendered_page(run_dir, slide)
        paths.page_render_png(run_dir, 2).unlink()
        paths.write_model(paths.manifest_file(run_dir), a_manifest(page_count=2))

        page_reader.read_run_pages(
            run_dir,
            reader=FakeReader({("image", slide): draft() for slide in (1, 2)}),
            paths_to_read=[schemas.PathKind.image],
        )

        manifest = schemas.Manifest.model_validate(
            paths.read_json(paths.manifest_file(run_dir))
        )
        image = next(
            stat for stat in manifest.paths if stat.path == schemas.PathKind.image
        )
        assert image.slides_attempted == 2
        assert image.slides_succeeded == 1
        assert image.reader_notes == 1

    def test_an_unexpected_error_still_leaves_a_manifest_behind(self, tmp_path):
        run_dir = tmp_path / "run"
        for slide in (1, 2):
            write_rendered_page(run_dir, slide)
        paths.write_model(paths.manifest_file(run_dir), a_manifest(page_count=2))

        class Exploding:
            def read(self, request):
                if request.slide_number == 2:
                    raise TypeError("a programming error, not a model failure")
                return page_reader.PageReadResult(
                    note=draft(),
                    usage=schemas.StageUsage(stage="page_reader", calls=1),
                )

        with pytest.raises(TypeError):
            page_reader.read_run_pages(
                run_dir,
                reader=Exploding(),
                paths_to_read=[schemas.PathKind.image],
                max_concurrency=1,
            )

        assert paths.manifest_file(run_dir).is_file()
        manifest = schemas.Manifest.model_validate(
            paths.read_json(paths.manifest_file(run_dir))
        )
        image = next(
            stat for stat in manifest.paths if stat.path == schemas.PathKind.image
        )
        assert image.slides_attempted == 1
        assert image.slides_succeeded == 1

    def test_a_crashed_stage_does_not_mark_itself_complete(self, tmp_path):
        """Partial counts are worth keeping. A completion claim is not."""

        run_dir = tmp_path / "run"
        for slide in (1, 2):
            write_rendered_page(run_dir, slide)
        paths.write_model(paths.manifest_file(run_dir), a_manifest(page_count=2))

        class Exploding:
            def read(self, request):
                if request.slide_number == 2:
                    raise TypeError("a programming error, not a model failure")
                return page_reader.PageReadResult(
                    note=draft(),
                    usage=schemas.StageUsage(stage="page_reader", calls=1),
                )

        with pytest.raises(TypeError):
            page_reader.read_run_pages(
                run_dir,
                reader=Exploding(),
                paths_to_read=[schemas.PathKind.image],
                max_concurrency=1,
            )

        manifest = schemas.Manifest.model_validate(
            paths.read_json(paths.manifest_file(run_dir))
        )
        image = next(
            stat for stat in manifest.paths if stat.path == schemas.PathKind.image
        )
        assert "page_reader" not in image.completed_stages
        assert image.completed_stages == ["render"]


def test_the_log_callback_reports_each_slide_with_the_path_it_belongs_to(tmp_path):
    """The interface routes a live line into the right stage box by its path.

    Issue #25 has one box per path, so a log line carrying only text would have
    to be parsed to be placed. The callback is handed the `PathKind` instead.
    """

    run_dir = tmp_path / "run"
    for slide in (1, 2):
        write_rendered_page(run_dir, slide)
    paths.write_model(paths.manifest_file(run_dir), a_manifest(2))
    degraded = draft("Slide 2").model_copy(update={"reader_note": "unreadable"})
    reader = FakeReader(
        {
            ("image", 1): draft("Slide 1"),
            ("image", 2): degraded,
            ("text", 1): draft("Slide 1"),
            ("text", 2): draft("Slide 2"),
        }
    )
    lines: list[tuple[str, str]] = []

    page_reader.read_run_pages(
        run_dir,
        reader=reader,
        log=lambda path_kind, message: lines.append((path_kind.value, message)),
        max_concurrency=1,
    )

    image_lines = [message for kind, message in lines if kind == "image"]
    text_lines = [message for kind, message in lines if kind == "text"]
    assert len(image_lines) == 2
    assert len(text_lines) == 2
    assert any("slide 1" in message for message in image_lines)
    assert any("DEGRADED" in message and "slide 2" in message for message in image_lines)
