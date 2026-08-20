"""Stage 1: a PDF to page images and extracted text, plus everything that can
be learned from a deck without asking a model anything.

Both outputs are produced in one pass so the image path and the text path see
the same page numbering by construction. Preflight and build-up frame detection
live here because they need the extracted text and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import config, paths
from .schemas import Preflight


class DeckUnreadable(RuntimeError):
    """The one hard stop: the PDF does not open, or it is encrypted."""


# --- Build-up frames --------------------------------------------------------


def _line_set(text: str) -> set[str]:
    """Normalized non-empty lines. Case and internal spacing are not content."""

    lines = set()
    for raw in text.splitlines():
        normalized = " ".join(raw.split()).casefold()
        if normalized:
            lines.add(normalized)
    return lines


def detect_superseded(
    page_texts: list[str], enabled: bool = config.BUILDUP_DETECTION_ENABLED
) -> list[int]:
    """Slide numbers that a later frame of the same build contains entirely.

    Page N is superseded by page N+1 when both carry at least
    `BUILDUP_MIN_CHARS` of extracted text, N's normalized non-empty lines are a
    subset of N+1's, and N+1 has strictly more of them. Chains apply across
    consecutive pages and the last frame survives.

    Deliberately conservative. A false negative leaves some exposure inflation;
    a false positive silently deletes a real slide, so subset-plus-strictly-more
    is the whole rule and a mere duplicate page is not a build-up.
    """

    if not enabled:
        return []

    superseded: list[int] = []
    for index in range(len(page_texts) - 1):
        first, second = page_texts[index], page_texts[index + 1]
        if len(first.strip()) < config.BUILDUP_MIN_CHARS:
            continue
        if len(second.strip()) < config.BUILDUP_MIN_CHARS:
            continue
        first_lines, second_lines = _line_set(first), _line_set(second)
        if not first_lines:
            continue
        if first_lines < second_lines:  # proper subset: contained and smaller
            superseded.append(index + 1)  # slide numbers are 1-based
    return superseded


def survivor_map(superseded: list[int], page_count: int) -> dict[int, int]:
    """Every slide mapped to the frame that survives for it.

    A citation resolving to a superseded frame is rewritten in code to this
    survivor. A slide that is not superseded maps to itself.
    """

    dropped = set(superseded)
    mapping: dict[int, int] = {}
    for slide in range(1, page_count + 1):
        target = slide
        while target in dropped and target < page_count:
            target += 1
        mapping[slide] = target
    return mapping


# --- Preflight --------------------------------------------------------------


def scale_for_long_edge(width_px: int, height_px: int) -> float:
    """How much to shrink a rendered page so its long edge fits the clamp.

    1.0 for anything already inside it, which is every course deck page.
    """

    long_edge = max(width_px, height_px)
    if long_edge <= config.MAX_LONG_EDGE_PX:
        return 1.0
    return config.MAX_LONG_EDGE_PX / long_edge


def build_preflight(page_texts: list[str], width_px: int, height_px: int) -> Preflight:
    """What this run is allowed to claim about this deck.

    Preflight decides what a run may report, not whether it happens. The one
    exception is readability, which is checked before this function is reached.
    """

    page_count = len(page_texts)
    text_native = sum(
        1 for text in page_texts if len(text.strip()) >= config.TEXT_NATIVE_MIN_CHARS
    )
    fraction = (text_native / page_count) if page_count else 0.0
    image_only = fraction < config.TEXT_NATIVE_MIN_FRACTION

    # Detection reads extracted text, so an image-only deck has nothing to read.
    # That it did not run is recorded rather than assumed.
    detection_ran = config.BUILDUP_DETECTION_ENABLED and not image_only
    superseded = detect_superseded(page_texts, enabled=detection_ran)

    return Preflight(
        readable=True,
        page_count=page_count,
        text_native_pages=text_native,
        text_native_fraction=fraction,
        image_only=image_only,
        page_width_px=width_px,
        page_height_px=height_px,
        downscaled=scale_for_long_edge(width_px, height_px) < 1.0,
        buildup_detection_ran=detection_ran,
        superseded_count=len(superseded),
        superseded=superseded,
        long_deck=page_count > config.LONG_DECK_SLIDES,
    )


# --- The stage itself -------------------------------------------------------


@dataclass
class RenderResult:
    preflight: Preflight
    page_texts: list[str] = field(default_factory=list)
    image_paths: list[Path] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return self.preflight.page_count

    def survivors(self) -> dict[int, int]:
        return survivor_map(self.preflight.superseded, self.page_count)


def _points_to_pixels(points: float, dpi: int) -> int:
    return int(round(points * dpi / 72.0))


def render_deck(
    pdf_path: Path,
    run_dir: Path,
    dpi: int = config.RENDER_DPI,
    log=None,
) -> RenderResult:
    """Render every page to PNG and write its extracted text beside it.

    Raises `DeckUnreadable` when the PDF will not open or is encrypted. That is
    the only refusal in the pipeline; everything else degrades.
    """

    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(str(pdf_path))
        page_count = len(document)
    except Exception as error:  # pdfium raises its own error types
        raise DeckUnreadable(f"{pdf_path.name} will not open: {error}") from error
    if page_count == 0:
        raise DeckUnreadable(f"{pdf_path.name} has no pages")

    first_width, first_height = document[0].get_size()
    width_px = _points_to_pixels(first_width, dpi)
    height_px = _points_to_pixels(first_height, dpi)
    scale = (dpi / 72.0) * scale_for_long_edge(width_px, height_px)

    page_texts: list[str] = []
    image_paths: list[Path] = []
    render_dir = run_dir / "pages-render"
    render_dir.mkdir(parents=True, exist_ok=True)

    for index in range(page_count):
        slide_number = index + 1
        page = document[index]

        textpage = page.get_textpage()
        text = textpage.get_text_range() or ""
        page_texts.append(text)
        paths.write_text(paths.page_render_txt(run_dir, slide_number), text)

        image = page.render(scale=scale).to_pil()
        target = paths.page_render_png(run_dir, slide_number)
        image.save(target)
        image_paths.append(target)

        if log and (slide_number % 10 == 0 or slide_number == page_count):
            log(f"rendered {slide_number}/{page_count} pages")

    preflight = build_preflight(page_texts, width_px=width_px, height_px=height_px)
    if log:
        if preflight.image_only:
            log("deck is image-only: the text path will run but is not comparable")
        if preflight.superseded_count:
            log(f"{preflight.superseded_count} build-up frames superseded")
    return RenderResult(preflight=preflight, page_texts=page_texts, image_paths=image_paths)


def load_page_texts(run_dir: Path, page_count: int) -> list[str]:
    """Read back what render wrote. Used by replay and by the span checker."""

    texts: list[str] = []
    for slide_number in range(1, page_count + 1):
        target = paths.page_render_txt(run_dir, slide_number)
        texts.append(target.read_text(encoding="utf-8") if target.is_file() else "")
    return texts
