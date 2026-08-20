"""Headless pipeline orchestration.

Issue #16 stops after render: it creates a run directory, writes rendered page
artifacts and a manifest, and updates the latest pointer. No model client is
imported here.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import config, memory, paths, render
from .schemas import Manifest, PathKind, PathStats, StageUsage
from .stages import outline, page_reader, quiz, research, review


class PipelineError(RuntimeError):
    """A user-facing refusal from the headless command."""


@dataclass(frozen=True)
class PipelineResult:
    run_dir: Path
    manifest: Manifest


def _next_run_slot(
    layout: paths.Layout,
    subject_slug: str,
    deck_slug: str,
    started_at: datetime | None,
) -> tuple[str, Path]:
    """Return a timestamp and directory that do not already exist."""

    moment = started_at
    while True:
        stamp = paths.utc_timestamp(moment)
        run_dir = layout.run_dir(subject_slug, deck_slug, stamp)
        if not run_dir.exists():
            return stamp, run_dir
        if started_at is not None:
            raise PipelineError(f"run directory already exists: {run_dir}")
        time.sleep(1.0)
        moment = None


def run_render_pipeline(
    deck_path: Path,
    subject_slug: str,
    *,
    layout: paths.Layout | None = None,
    started_at: datetime | None = None,
    log: Callable[[str], None] | None = None,
    read_pages: bool = False,
    resume: bool = False,
    slide_numbers: list[int] | None = None,
    reader: page_reader.PageReader | None = None,
    outline_pages: bool = False,
    outliner: outline.Outliner | None = None,
    research_pages: bool = False,
    researcher: research.Researcher | None = None,
    review_pages: bool = False,
    review_writer: review.ReviewWriter | None = None,
    quiz_pages: bool = False,
    quiz_generator: quiz.QuizGenerator | None = None,
) -> PipelineResult:
    """Run render/preflight, and optionally the page-reader stage."""

    deck_path = Path(deck_path)
    if not deck_path.is_file():
        raise PipelineError(f"deck not found: {deck_path}")

    layout = layout or paths.Layout()
    deck_sha256 = paths.sha256_file(deck_path)
    deck_slug = paths.deck_slug(
        deck_path.name, deck_sha256, layout.deck_slugs_with_hashes(subject_slug)
    )
    caller_started_at = started_at
    if started_at is None:
        started_at = datetime.now(timezone.utc)
    run_timestamp, run_dir = _next_run_slot(
        layout, subject_slug, deck_slug, started_at=caller_started_at
    )
    started_stamp = (
        paths.utc_timestamp(started_at)
        if caller_started_at is not None
        else run_timestamp
    )

    if log:
        log(f"creating run {subject_slug}/{deck_slug}/{run_timestamp}")

    try:
        render_result = render.render_deck(deck_path, run_dir, log=log)
    except render.DeckUnreadable as error:
        raise PipelineError(str(error)) from error

    ended_stamp = paths.utc_timestamp()
    manifest = Manifest(
        schema_version=config.SCHEMA_VERSION,
        subject_slug=subject_slug,
        deck_slug=deck_slug,
        deck_sha256=deck_sha256,
        deck_filename=deck_path.name,
        run_timestamp=run_timestamp,
        started_at=started_stamp,
        ended_at=ended_stamp,
        model=config.MODEL_ID,
        prompt_version=config.PROMPT_VERSION,
        dpi=config.RENDER_DPI,
        preflight=render_result.preflight,
        paths=[
            PathStats(path=PathKind.image, completed_stages=["render"]),
            PathStats(path=PathKind.text, completed_stages=["render"]),
        ],
        stage_usage=[StageUsage(stage="render")],
        total_cost_usd=0.0,
    )

    paths.write_model(paths.manifest_file(run_dir), manifest)
    layout.write_latest(subject_slug, deck_slug, run_timestamp)

    should_review_pages = review_pages or quiz_pages
    should_research_pages = research_pages or should_review_pages
    should_outline_pages = outline_pages or should_research_pages
    should_read_pages = read_pages or should_outline_pages

    if should_read_pages:
        page_reader.read_run_pages(
            run_dir,
            reader=reader,
            slide_numbers=slide_numbers,
            resume=resume,
        )
        manifest = Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))

    if should_outline_pages:
        outline.outline_run(
            run_dir,
            deck_slug=deck_slug,
            superseded=render_result.preflight.superseded,
            subject_slug=subject_slug,
            layout=layout,
            outliner=outliner,
        )
        memory.write_deck_contribution(run_dir, layout=layout)
        manifest = Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))

    if should_research_pages:
        research.research_run(run_dir, layout=layout, researcher=researcher)
        manifest = Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))

    if should_review_pages:
        review.review_run(run_dir, writer=review_writer)
        manifest = Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))

    if quiz_pages:
        quiz.quiz_run(run_dir, generator=quiz_generator)
        manifest = Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))

    if log:
        log(f"wrote {paths.manifest_file(run_dir)}")
        log(f"latest -> {run_timestamp}")
    return PipelineResult(run_dir=run_dir, manifest=manifest)


def parse_slide_numbers(raw: str) -> list[int]:
    """Parse `55-61,70` into sorted slide numbers."""

    slides: set[int] = set()
    for part in raw.split(","):
        piece = part.strip()
        if not piece:
            continue
        if "-" in piece:
            start_raw, end_raw = piece.split("-", 1)
            try:
                start, end = int(start_raw), int(end_raw)
            except ValueError as error:
                raise PipelineError(f"invalid slide range: {piece}") from error
            if end < start:
                raise PipelineError(f"slide range ends before it starts: {piece}")
            slides.update(range(start, end + 1))
        else:
            try:
                slides.add(int(piece))
            except ValueError as error:
                raise PipelineError(f"invalid slide number: {piece}") from error
    return sorted(slides)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m study_agent.pipeline",
        description="Render a slide deck into a timestamped run directory.",
    )
    parser.add_argument("deck_pdf", type=Path, help="PDF slide deck to process")
    parser.add_argument(
        "--subject",
        required=True,
        help="Subject slug, for example engr-689",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--read-pages",
        action="store_true",
        help="Continue after render and read pages into SlideNote files.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="With --read-pages, retry only notes whose reader_note is non-null.",
    )
    parser.add_argument(
        "--slides",
        help="Optional slide list for page reads, for example 55-61 or 1,3,5.",
    )
    parser.add_argument(
        "--outline",
        action="store_true",
        help="Continue after page reading and write outline-image/text.json.",
    )
    parser.add_argument(
        "--research",
        action="store_true",
        help="Continue after page reading and write cached research entries.",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Continue through research and write review-image/text.md.",
    )
    parser.add_argument(
        "--quiz",
        action="store_true",
        help="Continue through review and write image-path quiz.json.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    layout = paths.Layout(args.root) if args.root is not None else paths.Layout()
    try:
        slide_numbers = parse_slide_numbers(args.slides) if args.slides else None
        result = run_render_pipeline(
            args.deck_pdf,
            args.subject,
            layout=layout,
            read_pages=args.read_pages,
            resume=args.resume,
            slide_numbers=slide_numbers,
            outline_pages=args.outline,
            research_pages=args.research,
            review_pages=args.review,
            quiz_pages=args.quiz,
            log=lambda message: print(message, file=sys.stderr),
        )
    except PipelineError as error:
        print(error, file=sys.stderr)
        return 1
    print(result.run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
