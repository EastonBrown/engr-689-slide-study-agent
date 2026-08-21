"""Headless pipeline orchestration from render through optional research."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import config, paths, render
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


def _load_manifest(run_dir: Path) -> Manifest | None:
    payload = paths.read_json(paths.manifest_file(run_dir))
    return Manifest.model_validate(payload) if payload is not None else None


def _require_slides_in_deck(slide_numbers: list[int], page_count: int) -> None:
    """Refuse a slice naming a page the deck does not have.

    Checked once the deck's length is known and before any note is read, so a
    mistyped range costs the render it already paid for and no model calls.
    """

    past_end = [slide for slide in slide_numbers if slide > page_count]
    if past_end:
        raise PipelineError(
            f"deck has {page_count} slides; --slides names "
            f"{', '.join(str(slide) for slide in past_end)}"
        )


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
    research_concepts: bool = False,
    researcher: research.Researcher | None = None,
    review_pages: bool = False,
    reviewer: review.Reviewer | None = None,
    quiz_pages: bool = False,
    quiz_generator: quiz.QuizGenerator | None = None,
) -> PipelineResult:
    """Run render/preflight, and optionally the page-reader stage."""

    if research_concepts and not (read_pages and outline_pages):
        raise PipelineError("--research requires --read-pages and --outline")
    if review_pages and not (read_pages and outline_pages):
        raise PipelineError("--review requires --read-pages and --outline")
    if quiz_pages and not (read_pages and outline_pages):
        raise PipelineError("--quiz requires --read-pages and --outline")

    deck_path = Path(deck_path)
    if not deck_path.is_file():
        raise PipelineError(f"deck not found: {deck_path}")

    # A range outside the deck is a typo, not a render request. Count the PDF
    # before allocating a run directory so this refusal creates no artifacts
    # or latest pointer and makes no model calls.
    if slide_numbers:
        try:
            _require_slides_in_deck(slide_numbers, render.page_count(deck_path))
        except render.DeckUnreadable as error:
            raise PipelineError(str(error)) from error

    layout = layout or paths.Layout()
    deck_sha256 = paths.sha256_file(deck_path)
    deck_slug = paths.deck_slug(
        deck_path.name, deck_sha256, layout.deck_slugs_with_hashes(subject_slug)
    )

    if resume:
        # Re-entering an existing run, not allocating one. The run directory,
        # its manifest, and the `latest` pointer are all left exactly as they
        # were; only the stages below act, and page_reader is told to retry
        # only what still needs it.
        run_dir = layout.latest_run_dir(subject_slug, deck_slug)
        if run_dir is None:
            raise PipelineError(
                f"no run to resume for {subject_slug}/{deck_slug}; "
                "run once without --resume first"
            )
        manifest = _load_manifest(run_dir)
        if manifest is None:
            raise PipelineError(f"run directory has no manifest: {run_dir}")
        if manifest.deck_sha256 != deck_sha256:
            raise PipelineError(
                f"{deck_path.name} does not match the deck run at {run_dir} "
                "was rendered from"
            )
        run_timestamp = manifest.run_timestamp
        superseded = manifest.preflight.superseded
        if log:
            log(f"resuming run {subject_slug}/{deck_slug}/{run_timestamp}")
    else:
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

        manifest = Manifest(
            schema_version=config.SCHEMA_VERSION,
            subject_slug=subject_slug,
            deck_slug=deck_slug,
            deck_sha256=deck_sha256,
            deck_filename=deck_path.name,
            run_timestamp=run_timestamp,
            started_at=started_stamp,
            ended_at=paths.utc_timestamp(),
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
        superseded = render_result.preflight.superseded

    if read_pages:
        page_reader.read_run_pages(
            run_dir,
            reader=reader,
            slide_numbers=slide_numbers,
            resume=resume,
        )
        manifest = Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))

    if outline_pages:
        outline.outline_run(
            run_dir,
            deck_slug=deck_slug,
            superseded=superseded,
            subject_slug=subject_slug,
            layout=layout,
            outliner=outliner,
        )
        manifest = Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))

    if research_concepts:
        research.research_run(run_dir, layout=layout, researcher=researcher)
        manifest = Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))

    if review_pages:
        review.review_run(run_dir, reviewer=reviewer)
        manifest = Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))

    if quiz_pages:
        quiz.quiz_run(run_dir, generator=quiz_generator)
        manifest = Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))

    # Re-stamped last, because every stage above rewrites the manifest from
    # its own copy and would otherwise leave `ended_at` at the moment render
    # finished. A run's recorded duration has to cover the model stages, which
    # are nearly all of its wall time.
    manifest = manifest.model_copy(update={"ended_at": paths.utc_timestamp()})
    paths.write_model(paths.manifest_file(run_dir), manifest)

    if log:
        log(f"wrote {paths.manifest_file(run_dir)}")
        if not resume:
            log(f"latest -> {run_timestamp}")
    return PipelineResult(run_dir=run_dir, manifest=manifest)


def parse_slide_numbers(raw: str) -> list[int]:
    """Parse `55-61,70` into sorted slide numbers."""

    slides: set[int] = set()
    for part in raw.split(","):
        piece = part.strip()
        if not piece:
            continue
        if "-" in piece.lstrip("-"):
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
    # Slides are 1-based everywhere: the render filenames, the manifest counts,
    # and every citation. A 0 reaching the reader asks for a page that cannot
    # exist, so it is a typo worth naming rather than a read worth attempting.
    below = sorted(slide for slide in slides if slide < 1)
    if below:
        raise PipelineError(f"slide numbers start at 1, got {below[0]}")
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
        help=(
            "Reopen the latest run for this deck instead of starting a new "
            "one. With --read-pages, retry only notes whose reader_note is "
            "non-null."
        ),
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
        help="Look up named-only concepts and populate the shared research cache.",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Continue after outlining and write both Markdown lesson reviews.",
    )
    parser.add_argument(
        "--quiz",
        action="store_true",
        help="Continue after outlining and write the image-path quiz.",
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
            research_concepts=args.research,
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
