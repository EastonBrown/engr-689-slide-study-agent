"""Score image-path verbatim spans against extracted page text."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from study_agent import paths, schemas


@dataclass(frozen=True)
class SpanFailure:
    slide_number: int
    span: str


@dataclass(frozen=True)
class SpanScore:
    slides_checked: int
    spans_checked: int
    passed: int
    failed: int
    failures: list[SpanFailure]
    # Spans on a page whose extracted text is missing, and the slides they came
    # from. Held apart from `failed` on purpose: this check can only ever say
    # that a span is absent from the text, and a page with no text at all is a
    # gap in the evidence rather than a fabrication by the reader.
    unscoreable: int = 0
    unscoreable_slides: list[int] = field(default_factory=list)


def _image_note_files(run_dir: Path) -> list[Path]:
    return sorted(paths.notes_dir(run_dir, "image").glob("*.json"))


def score_run(run_dir: Path | str) -> SpanScore:
    """Check every image-path `verbatim_spans` entry in a run.

    `run_dir` is coerced rather than required as a `Path`, because the run
    directory usually arrives as a string from the command line or a notebook.
    """

    run_dir = Path(run_dir)
    failures: list[SpanFailure] = []
    passed = 0
    spans_checked = 0
    slides_checked = 0
    unscoreable = 0
    unscoreable_slides: list[int] = []

    for note_file in _image_note_files(run_dir):
        note = schemas.SlideNote.model_validate(paths.read_json(note_file))
        slides_checked += 1
        extracted_file = paths.page_render_txt(run_dir, note.slide_number)
        extracted = paths.read_text(extracted_file) if extracted_file.is_file() else ""
        # Empty, not absent, is the case that actually occurs. Render writes a
        # .txt for every page including the ones pdfium extracts nothing from,
        # so the usual no-evidence page is an image-only slide with a
        # whitespace-only file. Slide 56 of the Day 3 deck is exactly this.
        if not extracted.strip():
            if note.verbatim_spans:
                unscoreable += len(note.verbatim_spans)
                unscoreable_slides.append(note.slide_number)
            continue
        for span in note.verbatim_spans:
            spans_checked += 1
            if span in extracted:
                passed += 1
            else:
                failures.append(SpanFailure(slide_number=note.slide_number, span=span))

    return SpanScore(
        slides_checked=slides_checked,
        spans_checked=spans_checked,
        passed=passed,
        failed=len(failures),
        failures=failures,
        unscoreable=unscoreable,
        unscoreable_slides=unscoreable_slides,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score image-path verbatim spans against extracted page text."
    )
    parser.add_argument("run_dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = score_run(args.run_dir)
    print(f"slides checked: {result.slides_checked}")
    print(f"spans checked: {result.spans_checked}")
    print(f"passes: {result.passed}")
    print(f"failures: {result.failed}")
    print(f"unscoreable: {result.unscoreable}")
    for failure in result.failures:
        print(f"slide {failure.slide_number}: {failure.span}")
    for slide_number in result.unscoreable_slides:
        print(f"no extracted text for slide {slide_number}")
    # Only a failure fails the check. An unscoreable page is reported and does
    # not change the exit code, because it is a missing measurement rather than
    # a wrong one, and exiting non-zero on it would make the eval unrunnable
    # over any run with a gap in it.
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
