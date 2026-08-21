"""Replaying a completed run with no API calls, issue #27.

Every test here builds a source run on disk and replays it into a temporary
layout. Nothing constructs a model client, and `drive` is walked with a
recording sleep rather than a real one, so the suite does not pay the demo's
animation delay to assert on its ordering.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from study_agent import paths, replay, run_view, schemas


def _manifest(run_dir: Path, slides: int) -> None:
    manifest = schemas.Manifest(
        schema_version=1,
        subject_slug="engr-689",
        deck_slug="day3-principle",
        deck_sha256="a" * 64,
        deck_filename="Day3 Principle.pdf",
        run_timestamp="2026-08-20T12-00-00Z",
        started_at="2026-08-20T12-00-00Z",
        ended_at="2026-08-20T12-05-00Z",
        model="claude-opus-5",
        prompt_version="v1",
        dpi=150,
        preflight=schemas.Preflight(
            readable=True,
            page_count=slides,
            text_native_pages=slides,
            text_native_fraction=1.0,
            image_only=False,
            page_width_px=2000,
            page_height_px=1125,
            downscaled=False,
            buildup_detection_ran=True,
            superseded_count=0,
            superseded=[],
            long_deck=False,
        ),
        paths=[
            schemas.PathStats(
                path=kind,
                slides_attempted=slides,
                slides_succeeded=slides,
                completed_stages=["render", "page_reader"],
            )
            for kind in (schemas.PathKind.image, schemas.PathKind.text)
        ],
        stage_usage=[schemas.StageUsage(stage="render")],
        total_cost_usd=0.0,
    )
    paths.write_model(paths.manifest_file(run_dir), manifest)


def _note(slide: int) -> schemas.SlideNote:
    return schemas.SlideNote(
        slide_number=slide,
        page_role=schemas.PageRole.content,
        title=f"Slide {slide}",
        reading="what the slide says",
        visuals=[],
        concepts=[],
        verbatim_spans=[],
        reader_note=None,
    )



@pytest.fixture(autouse=True)
def _no_replay_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer's own demo pacing must not change what the suite asserts."""

    for name in (replay.LINE_DELAY_ENV, replay.STAGE_DELAY_ENV, replay.REPLAY_RUN_ENV):
        monkeypatch.delenv(name, raising=False)


def source_run(root: Path, *, slides: int = 3, with_memory: bool = True) -> Path:
    """A committed run in the shape `examples/golden/` has, at any root."""

    source = root / "golden"
    source.mkdir(parents=True, exist_ok=True)
    _manifest(source, slides)
    for slide in range(1, slides + 1):
        target = paths.page_render_png(source, slide)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"png")
        paths.write_text(paths.page_render_txt(source, slide), f"slide {slide}")
        for kind in (schemas.PathKind.image, schemas.PathKind.text):
            paths.write_model(
                paths.page_note(source, kind.value, slide), _note(slide)
            )
    (source / "README.md").write_text("not a run artifact\n", encoding="utf-8")
    if with_memory:
        memory_dir = source / "memory"
        paths.write_json(
            memory_dir / "subjects.json",
            {
                "subjects": [
                    {
                        "slug": "engr-689",
                        "display_name": "engr-689",
                        "created_at": "2026-08-21T03:48:58Z",
                    }
                ]
            },
        )
        paths.write_json(
            memory_dir / "engr-689" / "profile.json",
            {"schema_version": 1, "subject_slug": "engr-689", "topics": []},
        )
        paths.write_json(
            memory_dir / "engr-689" / "contributions" / "day3-principle.json",
            {"deck_slug": "day3-principle"},
        )
    return source


def installed_layout(tmp_path: Path) -> paths.Layout:
    return paths.Layout(root=tmp_path / "repo")


# --- Installing -------------------------------------------------------------


def test_install_puts_the_run_where_the_interface_reads_it(tmp_path: Path) -> None:
    source = source_run(tmp_path)
    layout = installed_layout(tmp_path)

    run_dir = replay.install_run(source, layout)

    assert run_dir == layout.run_dir("engr-689", "day3-principle", "2026-08-20T12-00-00Z")
    assert paths.manifest_file(run_dir).is_file()
    assert layout.read_latest("engr-689", "day3-principle") == "2026-08-20T12-00-00Z"
    assert run_view.run_summary(run_dir) is not None


def test_install_copies_artifact_trees_but_not_the_source_readme(tmp_path: Path) -> None:
    source = source_run(tmp_path)
    layout = installed_layout(tmp_path)

    run_dir = replay.install_run(source, layout)

    assert paths.page_render_png(run_dir, 1).is_file()
    assert paths.page_note(run_dir, "image", 3).is_file()
    assert not (run_dir / "README.md").exists()
    assert not (run_dir / "memory").exists()


def test_install_registers_the_subject_and_its_memory(tmp_path: Path) -> None:
    source = source_run(tmp_path)
    layout = installed_layout(tmp_path)

    replay.install_run(source, layout)

    registry = json.loads(layout.subjects_file().read_text(encoding="utf-8"))
    assert [entry["slug"] for entry in registry["subjects"]] == ["engr-689"]
    assert layout.profile_file("engr-689").is_file()
    assert layout.contribution_file("engr-689", "day3-principle").is_file()


def test_install_is_idempotent_and_keeps_local_edits(tmp_path: Path) -> None:
    """A Streamlit rerun must not re-copy, and must not undo what is there."""

    source = source_run(tmp_path)
    layout = installed_layout(tmp_path)
    run_dir = replay.install_run(source, layout)
    marker = run_dir / "local-marker.txt"
    marker.write_text("kept", encoding="utf-8")

    again = replay.install_run(source, layout)

    assert again == run_dir
    assert marker.is_file()


def test_install_overwrite_replaces_the_installed_copy(tmp_path: Path) -> None:
    source = source_run(tmp_path)
    layout = installed_layout(tmp_path)
    run_dir = replay.install_run(source, layout)
    (run_dir / "local-marker.txt").write_text("stale", encoding="utf-8")

    again = replay.install_run(source, layout, overwrite=True)

    assert not (again / "local-marker.txt").exists()
    assert paths.manifest_file(again).is_file()


def test_install_never_overwrites_existing_memory(tmp_path: Path) -> None:
    """`memory/` is where a user's own history lives. A demo does not touch it."""

    source = source_run(tmp_path)
    layout = installed_layout(tmp_path)
    paths.write_json(
        layout.subjects_file(),
        {
            "subjects": [
                {"slug": "engr-689", "display_name": "Mine", "created_at": "2026-01-01T00:00:00Z"},
                {"slug": "other", "display_name": "Other", "created_at": "2026-01-01T00:00:00Z"},
            ]
        },
    )
    paths.write_json(layout.profile_file("engr-689"), {"schema_version": 1, "subject_slug": "engr-689", "topics": ["mine"]})

    replay.install_run(source, layout)

    registry = json.loads(layout.subjects_file().read_text(encoding="utf-8"))
    names = {entry["slug"]: entry["display_name"] for entry in registry["subjects"]}
    assert names == {"engr-689": "Mine", "other": "Other"}
    profile = json.loads(layout.profile_file("engr-689").read_text(encoding="utf-8"))
    assert profile["topics"] == ["mine"]


def test_install_merges_a_subject_the_local_registry_lacks(tmp_path: Path) -> None:
    source = source_run(tmp_path)
    layout = installed_layout(tmp_path)
    paths.write_json(
        layout.subjects_file(),
        {"subjects": [{"slug": "other", "display_name": "Other", "created_at": "2026-01-01T00:00:00Z"}]},
    )

    replay.install_run(source, layout)

    registry = json.loads(layout.subjects_file().read_text(encoding="utf-8"))
    assert [entry["slug"] for entry in registry["subjects"]] == ["other", "engr-689"]


def test_install_refuses_a_directory_that_is_not_a_run(tmp_path: Path) -> None:
    not_a_run = tmp_path / "empty"
    not_a_run.mkdir()

    with pytest.raises(replay.ReplayError):
        replay.install_run(not_a_run, installed_layout(tmp_path))


def test_installed_run_finds_the_copy_only_once_it_exists(tmp_path: Path) -> None:
    source = source_run(tmp_path)
    layout = installed_layout(tmp_path)

    assert replay.installed_run(source, layout) is None
    run_dir = replay.install_run(source, layout)
    assert replay.installed_run(source, layout) == run_dir


# --- Matching an upload to a committed run ----------------------------------


def test_source_for_deck_matches_on_content_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = source_run(tmp_path)
    layout = installed_layout(tmp_path)
    monkeypatch.setattr(paths.Layout, "golden_run_dir", lambda self: source)

    assert replay.source_for_deck("a" * 64, layout) == source
    assert replay.source_for_deck("b" * 64, layout) is None


def test_source_for_deck_is_none_without_a_committed_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "nowhere"
    monkeypatch.setattr(paths.Layout, "golden_run_dir", lambda self: missing)

    assert replay.source_for_deck("a" * 64, installed_layout(tmp_path)) is None


def test_run_subject_reads_the_manifest(tmp_path: Path) -> None:
    assert replay.run_subject(source_run(tmp_path)) == "engr-689"


# --- Being pointed at a run directory ---------------------------------------


def test_env_names_a_run_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = source_run(tmp_path)
    monkeypatch.setenv(replay.REPLAY_RUN_ENV, str(source))

    assert replay.replay_run_from_env(installed_layout(tmp_path)) == source


def test_env_resolves_a_relative_path_against_the_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout = paths.Layout(root=tmp_path)
    source_run(tmp_path)
    monkeypatch.setenv(replay.REPLAY_RUN_ENV, "golden")

    assert replay.replay_run_from_env(layout) == tmp_path / "golden"


def test_env_unset_is_not_replay_mode(tmp_path: Path) -> None:
    assert replay.replay_run_from_env(installed_layout(tmp_path)) is None


def test_env_pointing_at_a_non_run_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv(replay.REPLAY_RUN_ENV, str(empty))

    with pytest.raises(replay.ReplayError):
        replay.replay_run_from_env(installed_layout(tmp_path))


# --- The stages and the animation -------------------------------------------


def test_stages_are_the_same_seven_boxes_the_live_screen_shows(tmp_path: Path) -> None:
    source = source_run(tmp_path)
    stages = replay.replay_stages(source)

    assert [stage.key for stage in stages] == list(run_view.STAGE_KEYS)
    live = run_view.stage_views(source)
    assert [stage.summary for stage in stages] == [view.summary for view in live]


def test_a_stage_that_never_ran_replays_as_absent(tmp_path: Path) -> None:
    stages = {stage.key: stage for stage in replay.replay_stages(source_run(tmp_path))}

    assert not stages[run_view.STAGE_RENDER].absent
    assert stages[run_view.STAGE_QUIZ].absent
    assert stages[run_view.STAGE_QUIZ].detail == []


def test_drive_walks_every_line_in_screen_order(tmp_path: Path) -> None:
    stages = replay.replay_stages(source_run(tmp_path))
    seen: list[tuple[str, str]] = []
    slept: list[float] = []

    replay.drive(
        stages,
        on_line=lambda stage, line: seen.append((stage.key, line)),
        sleep=slept.append,
    )

    expected = [(stage.key, line) for stage in stages for line in stage.detail]
    assert seen == expected
    assert len(slept) >= len(expected)
    assert all(delay > 0 for delay in slept)


def test_drive_opens_and_closes_each_stage_once(tmp_path: Path) -> None:
    stages = replay.replay_stages(source_run(tmp_path))
    events: list[tuple[str, str]] = []

    replay.drive(
        stages,
        on_line=lambda stage, line: events.append(("line", stage.key)),
        on_stage_start=lambda stage: events.append(("start", stage.key)),
        on_stage_end=lambda stage: events.append(("end", stage.key)),
        sleep=lambda _: None,
    )

    for stage in stages:
        assert events.count(("start", stage.key)) == 1
        assert events.count(("end", stage.key)) == 1
    starts = [key for kind, key in events if kind == "start"]
    assert starts == [stage.key for stage in stages]


def test_drive_holds_no_delay_when_the_environment_sets_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(replay.LINE_DELAY_ENV, "0")
    monkeypatch.setenv(replay.STAGE_DELAY_ENV, "0")
    slept: list[float] = []

    replay.drive(
        replay.replay_stages(source_run(tmp_path)),
        on_line=lambda stage, line: None,
        sleep=slept.append,
    )

    assert slept == []


@pytest.mark.parametrize("raw", ["not a number", "-1", ""])
def test_a_bad_delay_falls_back_rather_than_failing_the_demo(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv(replay.LINE_DELAY_ENV, raw)

    assert replay.line_delay() == replay.DEFAULT_LINE_DELAY_S


def test_delays_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(replay.LINE_DELAY_ENV, "0.25")
    monkeypatch.setenv(replay.STAGE_DELAY_ENV, "2")

    assert replay.line_delay() == 0.25
    assert replay.stage_delay() == 2.0


# --- Attempts ---------------------------------------------------------------


def test_clear_attempts_removes_only_attempt_files(tmp_path: Path) -> None:
    layout = installed_layout(tmp_path)
    for name in ("one", "two"):
        paths.write_json(layout.attempt_file("engr-689", name), {"attempt_id": name})
    paths.write_json(layout.profile_file("engr-689"), {"subject_slug": "engr-689"})

    removed = replay.clear_attempts("engr-689", layout)

    assert removed == 2
    assert list(layout.attempts_dir("engr-689").glob("*.json")) == []
    assert layout.profile_file("engr-689").is_file()


def test_clear_attempts_on_a_subject_with_none(tmp_path: Path) -> None:
    assert replay.clear_attempts("engr-689", installed_layout(tmp_path)) == 0


# --- No API calls -----------------------------------------------------------


def test_replaying_never_builds_a_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The acceptance criterion in #27, asserted rather than described.

    `llm.create_client` and `llm.load_api_key` are the only two doors to the
    API. Replacing both with a detonator covers install, the stage views, and
    the animation in one pass.
    """

    from study_agent import llm

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def detonate(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("replay must not construct an API client")

    monkeypatch.setattr(llm, "create_client", detonate)
    monkeypatch.setattr(llm, "load_api_key", detonate)

    source = source_run(tmp_path)
    layout = installed_layout(tmp_path)
    run_dir = replay.install_run(source, layout)
    replay.drive(
        replay.replay_stages(run_dir),
        on_line=lambda stage, line: None,
        sleep=lambda _: None,
    )

    assert run_view.run_summary(run_dir) is not None
    assert run_view.failures(run_dir) == []
