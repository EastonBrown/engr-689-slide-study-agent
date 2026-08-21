"""Replay a completed run from disk without starting the pipeline.

The Streamlit shell supplies the callbacks that draw and update its status
boxes. This module only obtains the disk-backed stage views and paces their
detail lines, so importing or using it cannot create an Anthropic client.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from time import sleep as _sleep
from typing import Sequence

from . import config, run_view

LINE_DELAY_S = config.REPLAY_LINE_DELAY_S

StageCallback = Callable[[run_view.StageView], None]
LineCallback = Callable[[run_view.StageView, str], None]
Sleep = Callable[[float], None]


def replay_run(
    run_dir: Path,
    *,
    on_stage: StageCallback,
    on_line: LineCallback,
    on_stage_complete: StageCallback,
    sleep: Sleep = _sleep,
) -> None:
    """Drive stage callbacks from artifacts under ``run_dir``.

    Stages with no artifacts are still emitted so the caller can mark them
    absent. Delay applies only between recorded detail lines; an absent stage
    never creates a fictitious line or a model call.
    """

    for view in run_view.stage_views(run_dir):
        on_stage(view)
        for line in view.detail:
            on_line(view, line)
            sleep(LINE_DELAY_S)
        on_stage_complete(view)


def replay_directory(arguments: Sequence[str]) -> Path | None:
    """Return the run directory supplied after ``--replay``, if any.

    Streamlit forwards application arguments after ``--``. Keeping this tiny
    parser here lets the app choose replay mode before it offers an upload.
    """

    try:
        option = arguments.index("--replay")
        value = arguments[option + 1]
    except (ValueError, IndexError):
        return None
    return Path(value)
