"""Replay a completed run from disk with no model calls."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from study_agent import config, interface


@dataclass(frozen=True)
class ReplayPlan:
    run_dir: Path
    stages: list[interface.StageState]
    summary: interface.RunSummary | None


def replay_plan(run_dir: Path) -> ReplayPlan:
    run_dir = Path(run_dir)
    return ReplayPlan(
        run_dir=run_dir,
        stages=interface.stage_states(run_dir),
        summary=interface.run_summary(run_dir),
    )


def emit_replay_lines(
    run_dir: Path,
    *,
    delay_s: float = config.REPLAY_LINE_DELAY_S,
    sleep: Callable[[float], None] = time.sleep,
) -> list[str]:
    lines: list[str] = []
    for stage in replay_plan(run_dir).stages:
        lines.append(f"{stage.name}: {stage.summary}")
        sleep(delay_s)
        for line in stage.log_lines:
            lines.append(line)
            sleep(delay_s)
    return lines


def print_replay(
    run_dir: Path,
    *,
    delay_s: float = config.REPLAY_LINE_DELAY_S,
    sleep: Callable[[float], None] = time.sleep,
    write: Callable[[str], None] = print,
) -> None:
    for stage in replay_plan(run_dir).stages:
        sleep(delay_s)
        write(f"{stage.name}: {stage.summary}")
        for line in stage.log_lines:
            sleep(delay_s)
            write(line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay a completed run from disk.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--delay", type=float, default=config.REPLAY_LINE_DELAY_S)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        replay_plan(args.run_dir)
        return 0
    print_replay(args.run_dir, delay_s=args.delay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
