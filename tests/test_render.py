"""Preflight and build-up frame detection. Pure text comparison, no model call."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest import mock

import pytest

from study_agent import config, paths, render


class FakeImage:
    def save(self, target) -> None:
        Path(target).write_bytes(b"png")


class FakeBitmap:
    def to_pil(self) -> FakeImage:
        return FakeImage()


class FakeTextPage:
    def __init__(self, text: str) -> None:
        self.text = text

    def get_text_range(self) -> str:
        return self.text


class FakePage:
    """One pdfium page, returning CRLF text the way the real one does."""

    def __init__(self, text: str) -> None:
        self.text = text

    def get_size(self) -> tuple[float, float]:
        return 960.0, 540.0

    def get_textpage(self) -> FakeTextPage:
        return FakeTextPage(self.text)

    def render(self, scale: float) -> FakeBitmap:
        del scale
        return FakeBitmap()


class FakeDocument:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages

    def __len__(self) -> int:
        return len(self.pages)

    def __getitem__(self, index: int) -> FakePage:
        return self.pages[index]


def render_deck_with(document: FakeDocument, run_dir: Path) -> render.RenderResult:
    """Run the real render stage over a stubbed pdfium."""

    module = types.ModuleType("pypdfium2")
    module.PdfDocument = lambda _path: document  # type: ignore[attr-defined]
    with mock.patch.dict(sys.modules, {"pypdfium2": module}):
        return render.render_deck(run_dir / "deck.pdf", run_dir)


def page(*lines: str) -> str:
    return "\n".join(lines)


A = page("Retrieval augmented generation", "The retriever selects passages from a corpus")
AB = page(
    "Retrieval augmented generation",
    "The retriever selects passages from a corpus",
    "The generator conditions on those passages",
)
ABC = page(
    "Retrieval augmented generation",
    "The retriever selects passages from a corpus",
    "The generator conditions on those passages",
    "Citations trace each claim back to its passage",
)


class TestSupersededFrames:
    def test_a_page_contained_by_the_next_is_superseded(self):
        assert render.detect_superseded([A, AB]) == [1]

    def test_the_last_frame_of_a_chain_survives(self):
        assert render.detect_superseded([A, AB, ABC]) == [1, 2]

    def test_survivor_of_a_chain_is_the_final_frame(self):
        mapping = render.survivor_map(render.detect_superseded([A, AB, ABC]), page_count=3)
        assert mapping[1] == 3
        assert mapping[2] == 3
        assert mapping[3] == 3

    def test_a_slide_that_is_not_superseded_maps_to_itself(self):
        mapping = render.survivor_map([1], page_count=3)
        assert mapping[3] == 3

    def test_equal_line_sets_are_not_a_build_up(self):
        # A repeated slide is a repeat, not an animation step. Strictly more
        # lines is required, so a duplicate page keeps both.
        assert render.detect_superseded([AB, AB]) == []

    def test_a_page_that_drops_a_line_is_not_superseded(self):
        assert render.detect_superseded([AB, A]) == []

    def test_short_pages_are_never_paired(self):
        assert render.detect_superseded(["Agents", "Agents\nand tools"]) == []

    def test_whitespace_and_case_do_not_defeat_containment(self):
        first = page("  Retrieval Augmented Generation  ", "the retriever selects passages")
        second = page(
            "RETRIEVAL AUGMENTED GENERATION",
            "The   retriever selects passages",
            "The generator conditions on those passages",
        )
        assert render.detect_superseded([first, second]) == [1]

    def test_non_adjacent_containment_is_ignored(self):
        unrelated = page(
            "Vision encoders", "CLIP dominates the field of multimodal language models"
        )
        assert render.detect_superseded([A, unrelated, AB]) == []

    def test_detection_can_be_disabled(self):
        assert render.detect_superseded([A, AB], enabled=False) == []

    def test_an_empty_deck_detects_nothing(self):
        assert render.detect_superseded([]) == []


class TestPreflight:
    def test_a_text_native_deck_is_not_image_only(self):
        texts = ["x" * 100] * 10
        result = render.build_preflight(texts, width_px=2000, height_px=1125)
        assert result.image_only is False
        assert result.text_native_fraction == 1.0
        assert result.buildup_detection_ran is True

    def test_a_deck_below_the_fraction_is_image_only(self):
        texts = ["x" * 100, "", "", ""]
        result = render.build_preflight(texts, width_px=2000, height_px=1125)
        assert result.image_only is True
        assert result.text_native_fraction == pytest.approx(0.25)

    def test_detection_is_off_for_an_image_only_deck_and_says_so(self):
        result = render.build_preflight(["", "", ""], width_px=2000, height_px=1125)
        assert result.buildup_detection_ran is False
        assert result.superseded == []

    def test_a_page_of_39_characters_is_not_text_native(self):
        assert config.TEXT_NATIVE_MIN_CHARS == 40
        result = render.build_preflight(["x" * 39, "x" * 40], width_px=100, height_px=100)
        assert result.text_native_pages == 1

    def test_superseded_frames_are_counted_into_the_preflight(self):
        result = render.build_preflight([A, AB], width_px=2000, height_px=1125)
        assert result.superseded == [1]
        assert result.superseded_count == 1

    def test_course_deck_geometry_is_not_downscaled(self):
        result = render.build_preflight(["x" * 100], width_px=2000, height_px=1125)
        assert result.downscaled is False

    def test_an_oversized_page_is_flagged_for_downscaling(self):
        result = render.build_preflight(["x" * 100], width_px=4000, height_px=2250)
        assert result.downscaled is True

    def test_a_long_deck_is_flagged(self):
        result = render.build_preflight(["x" * 100] * 130, width_px=2000, height_px=1125)
        assert result.long_deck is True


class TestScaleForLongEdge:
    def test_a_page_under_the_clamp_is_untouched(self):
        assert render.scale_for_long_edge(2000, 1125) == 1.0

    def test_an_oversized_page_scales_its_long_edge_to_the_clamp(self):
        scale = render.scale_for_long_edge(4000, 2250)
        assert scale == pytest.approx(config.MAX_LONG_EDGE_PX / 4000)

    def test_a_portrait_page_scales_on_its_height(self):
        scale = render.scale_for_long_edge(1000, 5000)
        assert scale == pytest.approx(config.MAX_LONG_EDGE_PX / 5000)


class TestExtractedTextRoundTrips:
    """A span that crosses a line break has to survive the write and the read.

    pdfium hands back CRLF line endings. Written through a text handle that
    translates newlines and read back through one that does not, every CRLF
    grew a second CR, so the text on disk was not the text that was extracted
    and every multi-line verbatim span scored as a fabrication.
    """

    def test_crlf_extracted_text_reads_back_byte_identical(self, tmp_path):
        target = paths.page_render_txt(tmp_path, 1)
        text = "Self-supervised learning\n• Modern methods\no Contrastive"

        paths.write_text(target, text)

        assert paths.read_text(target) == text
        assert b"\r" not in target.read_bytes()

    def test_render_normalizes_line_endings_before_writing(self, tmp_path):
        extracted = "Self-supervised learning\r\n• Modern methods\ro Contrastive"

        document = FakeDocument([FakePage(extracted)])
        render_deck_with(document, tmp_path)

        stored = paths.read_text(paths.page_render_txt(tmp_path, 1))
        assert stored == "Self-supervised learning\n• Modern methods\no Contrastive"
        assert render.load_page_texts(tmp_path, 1) == [stored]

    def test_a_span_crossing_a_line_break_is_found_in_the_stored_text(self, tmp_path):
        document = FakeDocument([FakePage("Retrieval\r\naugmented generation")])
        render_deck_with(document, tmp_path)

        stored = paths.read_text(paths.page_render_txt(tmp_path, 1))
        assert "Retrieval\naugmented generation" in stored
