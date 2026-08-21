"""Tests for the file-only replay controller (issue #27)."""

from __future__ import annotations

from pathlib import Path

from study_agent import replay, run_view


def test_replay_emits_each_stage_and_delays_each_detail_line(tmp_path, monkeypatch):
    views = [
        run_view.StageView(
            key="render",
            label="Render and preflight",
            state=run_view.StageState.complete,
            summary="complete",
            detail=["rendered slide 1", "rendered slide 2"],
        ),
        run_view.StageView(
            key="quiz",
            label="Quiz",
            state=run_view.StageState.pending,
            summary="not written",
        ),
    ]
    monkeypatch.setattr(run_view, "stage_views", lambda run_dir: views)
    stages: list[str] = []
    completed: list[str] = []
    lines: list[tuple[str, str]] = []
    delays: list[float] = []

    replay.replay_run(
        tmp_path,
        on_stage=lambda view: stages.append(view.key),
        on_line=lambda view, line: lines.append((view.key, line)),
        on_stage_complete=lambda view: completed.append(view.key),
        sleep=delays.append,
    )

    assert stages == ["render", "quiz"]
    assert completed == ["render", "quiz"]
    assert lines == [("render", "rendered slide 1"), ("render", "rendered slide 2")]
    assert delays == [replay.LINE_DELAY_S, replay.LINE_DELAY_S]


def test_replay_uses_the_configured_delay_and_never_requires_an_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        run_view,
        "stage_views",
        lambda run_dir: [
            run_view.StageView(
                key="review",
                label="Review",
                state=run_view.StageState.complete,
                summary="written",
                detail=["review written"],
            )
        ],
    )
    delays: list[float] = []

    replay.replay_run(
        tmp_path,
        on_stage=lambda view: None,
        on_line=lambda view, line: None,
        on_stage_complete=lambda view: None,
        sleep=delays.append,
    )

    assert delays == [replay.LINE_DELAY_S]


def test_replay_directory_reads_the_path_after_streamlit_separator(tmp_path):
    assert replay.replay_directory(["streamlit", "run", "app.py", "--", "--replay", str(tmp_path)]) == tmp_path
