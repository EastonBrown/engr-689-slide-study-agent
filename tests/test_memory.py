"""The subject registry, the profile, and performance derived from attempts."""

from __future__ import annotations

import json

import pytest

from study_agent import config, memory, paths
from study_agent.schemas import Attempt, AttemptKind, Response, TopicRecord


@pytest.fixture
def layout(tmp_path):
    return paths.Layout(root=tmp_path)


def write_attempt(layout, subject_slug, attempt_id, responses, kind=AttemptKind.first_pass):
    attempt = Attempt(
        attempt_id=attempt_id,
        subject_slug=subject_slug,
        deck_slug="day3-principle",
        run_timestamp="2026-08-20T09-00-00Z",
        quiz_sha256="a" * 64,
        kind=kind,
        taken_at=paths.utc_iso(),
        responses=[
            Response(question_id=f"q{i}", topic=topic, chosen_index=0, correct=correct)
            for i, (topic, correct) in enumerate(responses)
        ],
    )
    paths.write_model(layout.attempt_file(subject_slug, attempt_id), attempt)
    return attempt


class TestCreateSubject:
    def test_writes_both_the_registry_and_an_empty_profile(self, layout):
        entry = memory.create_subject("Multimodal LLM Agents", layout)

        assert entry.slug == "multimodal-llm-agents"
        assert layout.subjects_file().is_file()
        assert layout.profile_file(entry.slug).is_file()

        profile = memory.load_profile(entry.slug, layout)
        assert profile.subject_slug == entry.slug
        assert profile.schema_version == config.SCHEMA_VERSION
        assert profile.topics == []

    def test_keeps_the_display_name_the_human_typed(self, layout):
        entry = memory.create_subject("  ENGR 689  ", layout)
        assert entry.display_name == "ENGR 689"
        assert entry.slug == "engr-689"

    def test_a_second_subject_is_appended_rather_than_replacing_the_first(self, layout):
        memory.create_subject("ENGR 689", layout)
        memory.create_subject("Thermodynamics", layout)

        slugs = [entry.slug for entry in memory.list_subjects(layout)]
        assert slugs == ["engr-689", "thermodynamics"]

    def test_creating_a_subject_that_already_exists_is_refused(self, layout):
        memory.create_subject("ENGR 689", layout)
        with pytest.raises(memory.SubjectExists):
            memory.create_subject("engr 689", layout)

    def test_a_name_with_nothing_sluggable_is_refused(self, layout):
        for nothing in ("   ", "???", "--"):
            with pytest.raises(ValueError):
                memory.create_subject(nothing, layout)

    def test_a_subject_actually_named_untitled_is_allowed(self, layout):
        # The slug sentinel is not evidence about the name that produced it.
        entry = memory.create_subject("Untitled", layout)
        assert entry.slug == "untitled"
        assert entry.display_name == "Untitled"

    def test_an_unregistered_profile_on_disk_is_never_written_over(self, layout):
        """A gitignored `memory/` means a lost registry beside a surviving
        subject directory is a real state, and it holds every topic that
        subject has ever seen."""

        memory.create_subject("ENGR 689", layout)
        profile = memory.load_profile("engr-689", layout)
        profile.topics = [
            TopicRecord(name="Tool use", first_seen_deck="day1-tool", exposure=42)
        ]
        memory.save_profile(profile, layout)
        layout.subjects_file().unlink()

        with pytest.raises(memory.MemoryUnreadable):
            memory.create_subject("ENGR 689", layout)

        stored = json.loads(layout.profile_file("engr-689").read_text(encoding="utf-8"))
        assert stored["topics"][0]["exposure"] == 42

    def test_the_registry_is_written_before_the_profile(self, layout, monkeypatch):
        """So a crash between the two writes leaves a plainly reported missing
        profile rather than an orphan directory that blocks its own slug."""

        real_write_model = paths.write_model

        def die_on_the_profile(target, model):
            if target.name == "profile.json":
                raise OSError("disk full")
            real_write_model(target, model)

        monkeypatch.setattr(paths, "write_model", die_on_the_profile)
        with pytest.raises(OSError):
            memory.create_subject("ENGR 689", layout)

        monkeypatch.undo()
        assert [e.slug for e in memory.list_subjects(layout)] == ["engr-689"]
        with pytest.raises(memory.MemoryUnreadable):
            memory.load_profile("engr-689", layout)


class TestTheRegistryIsTheAuthority:
    def test_a_subject_directory_with_no_registry_entry_is_an_error(self, layout):
        # Everything a subject has on disk, but nothing in the registry.
        paths.write_json(
            layout.profile_file("orphan"),
            {"schema_version": config.SCHEMA_VERSION, "subject_slug": "orphan", "topics": []},
        )
        with pytest.raises(memory.UnknownSubject):
            memory.require_subject("orphan", layout)
        with pytest.raises(memory.UnknownSubject):
            memory.load_profile("orphan", layout)

    def test_a_missing_registry_reads_as_no_subjects(self, layout):
        assert memory.list_subjects(layout) == []

    def test_a_name_supplied_to_a_run_never_creates_the_subject(self, layout):
        with pytest.raises(memory.UnknownSubject):
            memory.require_subject("engr-689", layout)
        assert not layout.subject_dir("engr-689").exists()
        assert not layout.subjects_file().exists()

    def test_an_unparseable_registry_is_a_refusal_rather_than_an_empty_one(self, layout):
        paths.write_text(layout.subjects_file(), "{ not json")
        with pytest.raises(memory.MemoryUnreadable):
            memory.list_subjects(layout)


class TestLoadProfile:
    def test_a_fresh_subject_reads_back_an_empty_topic_list(self, layout):
        memory.create_subject("ENGR 689", layout)
        assert memory.load_profile("engr-689", layout).topics == []
        assert memory.topic_exposure("engr-689", layout) == {}

    def test_a_registered_subject_with_no_profile_file_is_an_error(self, layout):
        memory.create_subject("ENGR 689", layout)
        layout.profile_file("engr-689").unlink()
        with pytest.raises(memory.MemoryUnreadable):
            memory.load_profile("engr-689", layout)

    def test_a_schema_version_mismatch_is_a_refusal_not_a_migration(self, layout):
        memory.create_subject("ENGR 689", layout)
        stored = json.loads(layout.profile_file("engr-689").read_text(encoding="utf-8"))
        stored["schema_version"] = config.SCHEMA_VERSION + 1
        paths.write_json(layout.profile_file("engr-689"), stored)

        with pytest.raises(memory.SchemaVersionMismatch) as caught:
            memory.load_profile("engr-689", layout)
        assert str(config.SCHEMA_VERSION) in str(caught.value)

        # The refusal leaves the file exactly as it was.
        after = json.loads(layout.profile_file("engr-689").read_text(encoding="utf-8"))
        assert after["schema_version"] == config.SCHEMA_VERSION + 1

    def test_topic_exposure_reports_the_stored_counts(self, layout):
        memory.create_subject("ENGR 689", layout)
        profile = memory.load_profile("engr-689", layout)
        profile.topics = [
            TopicRecord(name="Tool use", first_seen_deck="day1-tool", exposure=7),
            TopicRecord(name="Encoders", first_seen_deck="day3-principle", exposure=2),
        ]
        memory.save_profile(profile, layout)

        assert memory.topic_exposure("engr-689", layout) == {"Tool use": 7, "Encoders": 2}

    def test_saving_a_profile_for_an_unregistered_subject_is_refused(self, layout):
        memory.create_subject("ENGR 689", layout)
        profile = memory.load_profile("engr-689", layout)
        profile.subject_slug = "orphan"
        with pytest.raises(memory.UnknownSubject):
            memory.save_profile(profile, layout)


class TestPerformance:
    def test_no_attempts_on_record_is_reported_rather_than_failing(self, layout):
        memory.create_subject("ENGR 689", layout)
        assert memory.load_attempts("engr-689", layout) == []
        assert memory.topic_performance("engr-689", layout) == []

    def test_a_topic_below_three_sightings_reports_insufficient_evidence(self, layout):
        memory.create_subject("ENGR 689", layout)
        write_attempt(layout, "engr-689", "a1", [("Encoders", True), ("Encoders", False)])

        (encoders,) = memory.topic_performance("engr-689", layout)
        assert (encoders.topic, encoders.correct, encoders.seen) == ("Encoders", 1, 2)
        assert encoders.insufficient_evidence is True

    def test_sightings_accumulate_across_attempts(self, layout):
        memory.create_subject("ENGR 689", layout)
        write_attempt(layout, "engr-689", "a1", [("Encoders", True), ("Encoders", False)])
        write_attempt(
            layout,
            "engr-689",
            "a2",
            [("Encoders", True), ("Tool use", True)],
            kind=AttemptKind.retake,
        )

        by_topic = {p.topic: p for p in memory.topic_performance("engr-689", layout)}
        assert (by_topic["Encoders"].correct, by_topic["Encoders"].seen) == (2, 3)
        assert by_topic["Encoders"].insufficient_evidence is False
        assert by_topic["Tool use"].insufficient_evidence is True

    def test_three_sightings_is_the_threshold_config_names(self, layout):
        assert config.MIN_SIGHTINGS_FOR_PERFORMANCE == 3
        memory.create_subject("ENGR 689", layout)
        write_attempt(
            layout,
            "engr-689",
            "a1",
            [("Encoders", False)] * config.MIN_SIGHTINGS_FOR_PERFORMANCE,
        )
        (encoders,) = memory.topic_performance("engr-689", layout)
        assert (encoders.correct, encoders.seen) == (0, 3)
        assert encoders.insufficient_evidence is False

    def test_performance_is_never_written_back_to_the_profile(self, layout):
        memory.create_subject("ENGR 689", layout)
        before = layout.profile_file("engr-689").read_text(encoding="utf-8")
        write_attempt(layout, "engr-689", "a1", [("Encoders", True)])
        memory.topic_performance("engr-689", layout)
        assert layout.profile_file("engr-689").read_text(encoding="utf-8") == before

    def test_attempts_come_back_oldest_first(self, layout):
        memory.create_subject("ENGR 689", layout)
        write_attempt(layout, "engr-689", "2026-08-20T09-00-00Z-bbbbbb", [("Encoders", True)])
        write_attempt(layout, "engr-689", "2026-08-19T09-00-00Z-aaaaaa", [("Encoders", True)])

        ids = [a.attempt_id for a in memory.load_attempts("engr-689", layout)]
        assert ids == [
            "2026-08-19T09-00-00Z-aaaaaa",
            "2026-08-20T09-00-00Z-bbbbbb",
        ]

    def test_an_unreadable_attempt_file_is_skipped_rather_than_taking_the_walk_down(
        self, layout
    ):
        memory.create_subject("ENGR 689", layout)
        write_attempt(layout, "engr-689", "a1", [("Encoders", True)])
        paths.write_text(layout.attempt_file("engr-689", "a2"), "{ truncated")
        paths.write_json(layout.attempt_file("engr-689", "a3"), {"attempt_id": "a3"})

        attempts = memory.load_attempts("engr-689", layout)
        assert [a.attempt_id for a in attempts] == ["a1"]

    def test_a_skipped_attempt_file_is_reported_rather_than_vanishing(self, layout):
        """Zero attempts and every attempt unreadable both count to zero, and
        only the second one means the reported performance is wrong."""

        memory.create_subject("ENGR 689", layout)
        paths.write_text(layout.attempt_file("engr-689", "a2"), "{ truncated")
        paths.write_json(layout.attempt_file("engr-689", "a3"), {"attempt_id": "a3"})

        found = memory.read_attempts("engr-689", layout)
        assert found.attempts == []
        assert found.unreadable == ["a2.json", "a3.json"]

    def test_a_clean_read_reports_nothing_skipped(self, layout):
        memory.create_subject("ENGR 689", layout)
        write_attempt(layout, "engr-689", "a1", [("Encoders", True)])

        found = memory.read_attempts("engr-689", layout)
        assert [a.attempt_id for a in found.attempts] == ["a1"]
        assert found.unreadable == []

    def test_no_attempts_directory_reports_nothing_skipped(self, layout):
        memory.create_subject("ENGR 689", layout)
        found = memory.read_attempts("engr-689", layout)
        assert (found.attempts, found.unreadable) == ([], [])

    def test_performance_on_an_unregistered_subject_is_an_error(self, layout):
        with pytest.raises(memory.UnknownSubject):
            memory.topic_performance("engr-689", layout)


class TestMemoryStaysGitignored:
    def test_the_repo_ignores_the_memory_tree(self):
        ignored = (paths.repo_root() / ".gitignore").read_text(encoding="utf-8").split()
        assert "memory/" in ignored
