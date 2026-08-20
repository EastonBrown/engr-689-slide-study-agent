"""Replay mode reads completed runs without invoking live pipeline work."""

from __future__ import annotations

from study_agent import config, paths, replay, schemas


def manifest(completed: list[str]) -> schemas.Manifest:
    return schemas.Manifest(
        schema_version=config.SCHEMA_VERSION,
        subject_slug="engr-689",
        deck_slug="deck",
        deck_sha256="a" * 64,
        deck_filename="Deck.pdf",
        run_timestamp="2026-08-20T12-00-00Z",
        started_at="2026-08-20T12-00-00Z",
        ended_at="2026-08-20T12-10-00Z",
        model=config.MODEL_ID,
        prompt_version=config.PROMPT_VERSION,
        dpi=config.RENDER_DPI,
        preflight=schemas.Preflight(
            readable=True,
            page_count=2,
            text_native_pages=2,
            text_native_fraction=1.0,
            image_only=False,
            page_width_px=2000,
            page_height_px=1125,
            downscaled=False,
            buildup_detection_ran=True,
            superseded_count=0,
            superseded=[],
        ),
        paths=[
            schemas.PathStats(path=schemas.PathKind.image, completed_stages=completed),
            schemas.PathStats(path=schemas.PathKind.text, completed_stages=completed),
        ],
        stage_usage=[],
        total_cost_usd=0,
    )


def test_replay_plan_reads_stage_lines_from_existing_files(tmp_path):
    run_dir = tmp_path / "run"
    paths.write_model(paths.manifest_file(run_dir), manifest(["render", "page_reader"]))

    plan = replay.replay_plan(run_dir)

    assert [item.name for item in plan.stages][:3] == ["Render", "Page reader", "Outline"]
    assert plan.stages[0].state == "complete"
    assert plan.stages[2].state == "pending"
    assert plan.summary is not None


def test_replay_sleeps_once_per_line_with_configurable_delay(tmp_path):
    run_dir = tmp_path / "run"
    paths.write_model(paths.manifest_file(run_dir), manifest(["render"]))
    sleeps: list[float] = []

    lines = replay.emit_replay_lines(run_dir, delay_s=0.25, sleep=sleeps.append)

    assert sleeps == [0.25] * len(lines)


def test_replay_does_not_require_an_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    run_dir = tmp_path / "run"
    paths.write_model(paths.manifest_file(run_dir), manifest(["render"]))

    plan = replay.replay_plan(run_dir)

    assert plan.run_dir == run_dir


def test_replay_cli_accepts_run_directory(tmp_path):
    run_dir = tmp_path / "run"
    paths.write_model(paths.manifest_file(run_dir), manifest(["render"]))

    assert replay.main([str(run_dir), "--dry-run"]) == 0


def test_replay_cli_writes_each_line_after_delay(tmp_path):
    run_dir = tmp_path / "run"
    paths.write_model(paths.manifest_file(run_dir), manifest(["render"]))
    events: list[str] = []

    replay.print_replay(run_dir, delay_s=0.25, sleep=lambda value: events.append(f"sleep:{value}"), write=events.append)

    assert events[0] == "sleep:0.25"
    assert events[1].startswith("Render:")
