"""Replaying a completed run on screen, with no API calls (issue #27).

A run that has already been produced is a directory of files. Everything the
interface shows is reconstructed from that directory by `run_view`, so a replay
does not need a model, a key, or a network: it needs the files in place and a
clock. This module supplies both halves.

`install_run` puts a committed run (`examples/golden/`, per ADR 0004) into the
gitignored `runs/` and `memory/` trees the interface actually reads, and
`replay_stages` turns that run into the same seven stage boxes the live path
fills in, with the log lines they would have streamed. `drive` walks those
lines at a fixed delay so the animation reads on video rather than appearing
all at once.

Nothing here imports Streamlit, and nothing here writes into a run that already
exists. The rendering below the stage boxes (summary, failures, comparison,
quiz) is not duplicated for replay: it is the same `run_view` code reading the
same directory, which is the point of installing rather than special-casing.
"""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from . import paths, run_view
from .paths import Layout
from .schemas import SubjectEntry, SubjectsRegistry

# Seconds per replayed log line, and the pause held on a finished stage box
# before the next one opens. Both are overridable from the environment so the
# demo can be slowed down for a room or sped up for a rehearsal.
DEFAULT_LINE_DELAY_S = 0.06
DEFAULT_STAGE_DELAY_S = 0.6

LINE_DELAY_ENV = "STUDY_AGENT_REPLAY_DELAY"
STAGE_DELAY_ENV = "STUDY_AGENT_REPLAY_STAGE_DELAY"

# Points the interface at a run directory instead of an upload, which is how
# issue #27 asks replay mode to be entered.
REPLAY_RUN_ENV = "STUDY_AGENT_REPLAY_RUN"

# Everything in a committed run directory that is not part of the run itself.
_NOT_RUN_ARTIFACTS = frozenset({"README.md", "memory"})


class ReplayError(RuntimeError):
    """A replay that cannot start. Never raised for a stage that is absent."""


@dataclass(frozen=True)
class ReplayStage:
    """One stage box, with the lines it replays into it.

    `state` is whatever the files say, `run_view.StageState.pending` included:
    a run that stopped before the quiz replays what exists and leaves the rest
    marked absent rather than inventing lines for it.
    """

    key: str
    label: str
    state: run_view.StageState
    summary: str
    detail: list[str] = field(default_factory=list)

    @property
    def absent(self) -> bool:
        return self.state is run_view.StageState.pending


# --- Timing -----------------------------------------------------------------


def _seconds(name: str, fallback: float) -> float:
    """A non-negative delay from the environment, or the default.

    A value that does not parse is the default rather than an error: the demo
    should not fail to start over a typo in an environment variable.
    """

    raw = os.environ.get(name)
    if raw is None:
        return fallback
    try:
        value = float(raw)
    except ValueError:
        return fallback
    return value if value >= 0 else fallback


def line_delay() -> float:
    return _seconds(LINE_DELAY_ENV, DEFAULT_LINE_DELAY_S)


def stage_delay() -> float:
    return _seconds(STAGE_DELAY_ENV, DEFAULT_STAGE_DELAY_S)


# --- What to replay ---------------------------------------------------------


def replay_stages(run_dir: Path) -> list[ReplayStage]:
    """The seven boxes for a run directory, in screen order.

    Read through `run_view.stage_views`, so a replayed box says exactly what
    the live box says once the live run has finished writing.
    """

    return [
        ReplayStage(
            key=view.key,
            label=view.label,
            state=view.state,
            summary=view.summary,
            detail=list(view.detail),
        )
        for view in run_view.stage_views(Path(run_dir))
    ]


def drive(
    stages: list[ReplayStage],
    *,
    on_line: Callable[[ReplayStage, str], None],
    on_stage_start: Callable[[ReplayStage], None] | None = None,
    on_stage_end: Callable[[ReplayStage], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Walk the stages, handing each line to the caller at the line delay.

    The caller owns every widget; this owns only the order and the clock, which
    is what keeps it testable with `sleep` swapped for a recorder.
    """

    per_line = line_delay()
    per_stage = stage_delay()
    for stage in stages:
        if on_stage_start is not None:
            on_stage_start(stage)
        if not stage.absent:
            for line in stage.detail:
                on_line(stage, line)
                if per_line:
                    sleep(per_line)
        if on_stage_end is not None:
            on_stage_end(stage)
        if per_stage and not stage.absent:
            sleep(per_stage)


# --- Finding a run to replay ------------------------------------------------


def golden_run_dir(layout: Layout | None = None) -> Path:
    return (layout or Layout()).golden_run_dir()


def _manifest_field(source: Path, name: str) -> str | None:
    payload = paths.read_json(paths.manifest_file(Path(source)))
    if not isinstance(payload, dict):
        return None
    value = payload.get(name)
    return value if isinstance(value, str) and value else None


def deck_sha256(source: Path) -> str | None:
    """The sha256 of the PDF a committed run was produced from."""

    return _manifest_field(source, "deck_sha256")


def run_subject(source: Path) -> str | None:
    """The subject slug a committed run belongs to, read from its manifest."""

    return _manifest_field(source, "subject_slug")


def source_for_deck(deck_sha256_: str, layout: Layout | None = None) -> Path | None:
    """The committed run produced from this exact PDF, if there is one.

    Content hash, not filename: the demo deck is selected from wherever the
    presenter keeps it, and a renamed copy is still the same deck.
    """

    source = golden_run_dir(layout)
    if not source.is_dir():
        return None
    return source if deck_sha256(source) == deck_sha256_ else None


def installed_run(source: Path, layout: Layout | None = None) -> Path | None:
    """Where `install_run` has already put this run, if it has.

    Streamlit reruns its script on every interaction. After the animation has
    played once, those reruns have to find the same run directory without
    replaying it, and without depending on a subject being selected.
    """

    layout = layout or Layout()
    manifest = run_view.load_manifest(Path(source))
    if manifest is None:
        return None
    target = layout.run_dir(
        manifest.subject_slug, manifest.deck_slug, manifest.run_timestamp
    )
    return target if target.is_dir() else None


def replay_run_from_env(layout: Layout | None = None) -> Path | None:
    """A run directory named by `STUDY_AGENT_REPLAY_RUN`, resolved and checked.

    Relative paths resolve against the repo root rather than the working
    directory, since Streamlit is not always started from the root.
    """

    raw = os.environ.get(REPLAY_RUN_ENV, "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (layout or Layout()).root / candidate
    if not candidate.is_dir():
        raise ReplayError(f"{REPLAY_RUN_ENV} names {candidate}, which is not a directory")
    if run_view.load_manifest(candidate) is None:
        raise ReplayError(f"{candidate} has no manifest.json that parses; it is not a run")
    return candidate


# --- Installing a committed run into the trees the interface reads ----------


def _run_artifacts(source: Path) -> Iterator[Path]:
    for entry in sorted(source.iterdir()):
        if entry.name not in _NOT_RUN_ARTIFACTS:
            yield entry


def install_run(
    source: Path,
    layout: Layout | None = None,
    *,
    overwrite: bool = False,
) -> Path:
    """Copy a committed run into `runs/`, and its memory state into `memory/`.

    Returns the run directory the interface should display. The run keeps the
    timestamp, subject, and deck slug recorded in its own manifest, so what is
    on screen agrees with the manifest that produced it.

    Installing twice is a no-op by default rather than a re-copy: a rerun of
    the Streamlit script must not spend seconds copying 66 page images again.
    Pass `overwrite=True` to replace an installed copy that has been edited.
    """

    source = Path(source)
    layout = layout or Layout()
    manifest = run_view.load_manifest(source)
    if manifest is None:
        raise ReplayError(f"{source} has no manifest.json that parses; it is not a run")

    target = layout.run_dir(
        manifest.subject_slug, manifest.deck_slug, manifest.run_timestamp
    )
    if target.is_dir() and overwrite:
        shutil.rmtree(target)
    if not target.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for entry in _run_artifacts(source):
            destination = target / entry.name
            if entry.is_dir():
                shutil.copytree(entry, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(entry, destination)

    layout.write_latest(
        manifest.subject_slug, manifest.deck_slug, manifest.run_timestamp
    )
    install_memory(source, layout)
    return target


def install_memory(source: Path, layout: Layout | None = None) -> None:
    """Put the run's subject state into `memory/`, without clobbering history.

    A committed run carries the memory it wrote: the subject registry entry,
    the profile, and the deck contribution. Those are installed only where the
    local tree has nothing, because `memory/` is where a real user's attempts
    and retakes accumulate and a demo must not overwrite them. The registry is
    merged entry by entry for the same reason.
    """

    source = Path(source)
    layout = layout or Layout()
    memory_dir = source / "memory"
    if not memory_dir.is_dir():
        return

    registry_payload = paths.read_json(memory_dir / "subjects.json")
    if isinstance(registry_payload, dict):
        _merge_registry(SubjectsRegistry.model_validate(registry_payload), layout)

    for subject_dir in sorted(entry for entry in memory_dir.iterdir() if entry.is_dir()):
        _copy_missing(subject_dir, layout.subject_dir(subject_dir.name))


def _merge_registry(incoming: SubjectsRegistry, layout: Layout) -> None:
    """Add any subject the local registry does not have, keeping the local one.

    Local wins on a slug collision: the display name a user typed is theirs,
    and the slug is what every path is built from either way.
    """

    target = layout.subjects_file()
    existing_payload = paths.read_json(target)
    existing = (
        SubjectsRegistry.model_validate(existing_payload)
        if isinstance(existing_payload, dict)
        else SubjectsRegistry()
    )
    known = {entry.slug for entry in existing.subjects}
    added: list[SubjectEntry] = [
        entry for entry in incoming.subjects if entry.slug not in known
    ]
    if not added:
        return
    existing.subjects.extend(added)
    paths.write_model(target, existing)


def _copy_missing(source: Path, target: Path) -> None:
    """Copy a tree, skipping every file that already exists at the target."""

    target.mkdir(parents=True, exist_ok=True)
    for entry in sorted(source.iterdir()):
        destination = target / entry.name
        if entry.is_dir():
            _copy_missing(entry, destination)
        elif not destination.exists():
            shutil.copy2(entry, destination)


def clear_attempts(subject_slug: str, layout: Layout | None = None) -> int:
    """Delete a subject's quiz attempts, returning how many were removed.

    Rehearsing the demo grades the quiz, and a graded attempt makes the next
    run of the same quiz open with the answer key already showing. This exists
    so that state can be cleared deliberately, by a button press, rather than
    by a replay quietly deleting a user's history behind them.
    """

    layout = layout or Layout()
    directory = layout.attempts_dir(subject_slug)
    if not directory.is_dir():
        return 0
    removed = 0
    for target in sorted(directory.glob("*.json")):
        target.unlink()
        removed += 1
    return removed
