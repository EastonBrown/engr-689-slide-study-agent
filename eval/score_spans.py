"""Score image-path verbatim spans against extracted page text."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
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


def _image_note_files(run_dir: Path) -> list[Path]:
    return sorted(paths.notes_dir(run_dir, "image").glob("*.json"))


def score_run(run_dir: Path) -> SpanScore:
    """Check every image-path `verbatim_spans` entry in a run."""

    failures: list[SpanFailure] = []
    passed = 0
    spans_checked = 0
    slides_checked = 0

    for note_file in _image_note_files(Path(run_dir)):
        note = schemas.SlideNote.model_validate(paths.read_json(note_file))
        slides_checked += 1
        extracted = paths.page_render_txt(run_dir, note.slide_number).read_text(
            encoding="utf-8"
        )
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
    for failure in result.failures:
        print(f"slide {failure.slide_number}: {failure.span}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
