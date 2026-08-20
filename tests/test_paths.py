"""Slugs, run directories, and the latest pointer."""

from __future__ import annotations

import json

import pytest

from study_agent import paths


class TestSlugify:
    def test_lowercases_and_hyphenates(self):
        assert paths.slugify("Multimodal LLM Agents") == "multimodal-llm-agents"

    def test_the_course_deck_filenames_slug_as_the_eval_labels_name_them(self):
        assert paths.slugify("Day3 Principle") == "day3-principle"
        assert paths.slugify("Day1 Tool") == "day1-tool"

    def test_strips_punctuation_and_collapses_runs(self):
        assert paths.slugify("Day1  Tool!!.pdf") == "day1-tool-pdf"

    def test_trims_leading_and_trailing_separators(self):
        assert paths.slugify("  --Multimodal LLMs--  ") == "multimodal-llms"

    def test_a_string_with_nothing_sluggable_is_not_empty(self):
        assert paths.slugify("???") == "untitled"


class TestDeckSlug:
    def test_slugifies_the_filename(self):
        assert paths.deck_slug("Day3 Principle.pdf", "a" * 64, {}) == "day3-principle"

    def test_same_slug_and_same_hash_reuses_the_directory(self):
        existing = {"day3-principle": "b" * 64}
        assert paths.deck_slug("Day3 Principle.pdf", "b" * 64, existing) == "day3-principle"

    def test_same_slug_different_hash_appends_the_hash_prefix(self):
        existing = {"day3-principle": "b" * 64}
        sha = "c" * 64
        assert paths.deck_slug("Day3 Principle.pdf", sha, existing) == "day3-principle-" + "c" * 8

    def test_the_extension_does_not_survive_into_the_slug(self):
        assert paths.deck_slug("notes.PDF", "d" * 64, {}) == "notes"


class TestRunPaths:
    def test_run_dir_nests_subject_then_deck_then_timestamp(self, tmp_path):
        root = paths.Layout(tmp_path)
        run = root.run_dir("engr-689", "day3-principle", "2026-08-20T12-00-00Z")
        assert run == tmp_path / "runs" / "engr-689" / "day3-principle" / "2026-08-20T12-00-00Z"

    def test_page_files_are_zero_padded_to_four_digits(self, tmp_path):
        root = paths.Layout(tmp_path)
        run = root.run_dir("s", "d", "t")
        assert paths.page_render_png(run, 7).name == "0007.png"
        assert paths.page_render_txt(run, 61).name == "0061.txt"
        assert paths.page_note(run, "image", 7).name == "0007.json"

    def test_latest_pointer_round_trips(self, tmp_path):
        root = paths.Layout(tmp_path)
        deck = root.deck_dir("engr-689", "day3-principle")
        deck.mkdir(parents=True)
        root.write_latest("engr-689", "day3-principle", "2026-08-20T12-00-00Z")
        assert root.read_latest("engr-689", "day3-principle") == "2026-08-20T12-00-00Z"

    def test_latest_pointer_is_none_before_any_run(self, tmp_path):
        root = paths.Layout(tmp_path)
        assert root.read_latest("engr-689", "day3-principle") is None


class TestResearchCacheKey:
    def test_normalization_lowercases_and_collapses_whitespace(self):
        assert paths.normalize_query("  What   is  RAG?  ") == "what is rag"

    def test_normalization_strips_trailing_punctuation_only(self):
        assert paths.normalize_query("CLIP-style encoders!!!") == "clip-style encoders"

    def test_queries_differing_only_in_spacing_share_a_key(self, tmp_path):
        root = paths.Layout(tmp_path)
        a = root.research_cache_file("What is RAG?")
        b = root.research_cache_file("what is    rag")
        assert a == b
        assert a.name.endswith(".json")


class TestJsonIO:
    def test_write_json_creates_parents_and_reads_back(self, tmp_path):
        target = tmp_path / "a" / "b" / "c.json"
        paths.write_json(target, {"x": 1})
        assert json.loads(target.read_text(encoding="utf-8")) == {"x": 1}

    def test_read_json_missing_file_returns_none(self, tmp_path):
        assert paths.read_json(tmp_path / "nope.json") is None

    def test_write_json_replaces_rather_than_appending(self, tmp_path):
        target = tmp_path / "c.json"
        paths.write_json(target, {"x": 1})
        paths.write_json(target, {"y": 2})
        assert json.loads(target.read_text(encoding="utf-8")) == {"y": 2}


class TestTimestamp:
    def test_timestamp_is_filename_safe_and_sortable(self):
        stamp = paths.utc_timestamp()
        assert stamp.endswith("Z")
        assert ":" not in stamp
        assert len(stamp) == len("2026-08-20T12-00-00Z")

    def test_attempt_id_carries_a_suffix_so_two_in_one_second_differ(self):
        first = paths.new_attempt_id()
        second = paths.new_attempt_id()
        assert first != second


def test_sha256_of_a_file_is_stable(tmp_path):
    target = tmp_path / "deck.pdf"
    target.write_bytes(b"pdf bytes")
    assert paths.sha256_file(target) == paths.sha256_file(target)
    assert len(paths.sha256_file(target)) == 64


def test_layout_defaults_to_the_repo_root():
    layout = paths.Layout()
    assert (layout.root / "docs" / "spec.md").exists()


@pytest.mark.parametrize("path_kind", ["image", "text"])
def test_outline_file_is_named_per_path(tmp_path, path_kind):
    run = paths.Layout(tmp_path).run_dir("s", "d", "t")
    assert paths.outline_file(run, path_kind).name == f"outline-{path_kind}.json"
    assert paths.review_file(run, path_kind).name == f"review-{path_kind}.md"


class TestDeckSlugsAlreadyUsedInASubject:
    """`deck_slug` needs a map of slug to sha256; this is where it comes from."""

    def _write_run(self, layout, deck_slug_, stamp, sha):
        run = layout.run_dir("engr-689", deck_slug_, stamp)
        paths.write_json(paths.manifest_file(run), {"deck_sha256": sha})
        layout.write_latest("engr-689", deck_slug_, stamp)

    def test_no_subject_directory_yet_reads_as_no_decks(self, tmp_path):
        layout = paths.Layout(tmp_path)
        assert layout.deck_slugs_with_hashes("engr-689") == {}

    def test_one_deck_maps_its_slug_to_its_hash(self, tmp_path):
        layout = paths.Layout(tmp_path)
        self._write_run(layout, "day3-principle", "2026-08-20T12-00-00Z", "a" * 64)
        assert layout.deck_slugs_with_hashes("engr-689") == {"day3-principle": "a" * 64}

    def test_the_newest_run_wins_when_a_deck_has_several(self, tmp_path):
        layout = paths.Layout(tmp_path)
        self._write_run(layout, "day3-principle", "2026-08-19T12-00-00Z", "a" * 64)
        self._write_run(layout, "day3-principle", "2026-08-20T12-00-00Z", "b" * 64)
        assert layout.deck_slugs_with_hashes("engr-689") == {"day3-principle": "b" * 64}

    def test_a_deck_directory_with_no_readable_manifest_is_skipped(self, tmp_path):
        layout = paths.Layout(tmp_path)
        layout.run_dir("engr-689", "half-written", "t").mkdir(parents=True)
        assert layout.deck_slugs_with_hashes("engr-689") == {}

    def test_it_feeds_deck_slug_so_a_collision_disambiguates(self, tmp_path):
        layout = paths.Layout(tmp_path)
        self._write_run(layout, "day3-principle", "2026-08-20T12-00-00Z", "a" * 64)
        existing = layout.deck_slugs_with_hashes("engr-689")
        assert paths.deck_slug("Day3 Principle.pdf", "e" * 64, existing) == (
            "day3-principle-" + "e" * 8
        )


class TestLatestPointer:
    def test_latest_run_dir_is_none_when_the_named_run_is_gone(self, tmp_path):
        layout = paths.Layout(tmp_path)
        layout.write_latest("engr-689", "day3-principle", "2026-08-20T12-00-00Z")
        assert layout.latest_run_dir("engr-689", "day3-principle") is None

    def test_latest_run_dir_resolves_once_the_run_exists(self, tmp_path):
        layout = paths.Layout(tmp_path)
        stamp = "2026-08-20T12-00-00Z"
        run = layout.run_dir("engr-689", "day3-principle", stamp)
        run.mkdir(parents=True)
        layout.write_latest("engr-689", "day3-principle", stamp)
        assert layout.latest_run_dir("engr-689", "day3-principle") == run


def test_write_model_flattens_enums_to_their_values(tmp_path):
    from study_agent import schemas

    target = tmp_path / "note.json"
    note = schemas.SlideNote(
        slide_number=1,
        page_role=schemas.PageRole.content,
        title=None,
        reading="A page.",
        visuals=[],
        concepts=[],
        verbatim_spans=[],
        reader_note=None,
    )
    paths.write_model(target, note)
    assert paths.read_json(target)["page_role"] == "content"


def test_read_json_on_a_corrupt_file_reads_as_none(tmp_path):
    target = tmp_path / "broken.json"
    target.write_text("{not json", encoding="utf-8")
    assert paths.read_json(target) is None

class TestTimestampIsActuallyUtc:
    """The stamp names the run directory and sorts `latest`, so a mislabeled
    one can make an older run sort as newer."""

    def test_an_aware_non_utc_datetime_is_converted_not_just_suffixed(self):
        from datetime import datetime, timedelta, timezone

        noon_utc = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        tokyo = noon_utc.astimezone(timezone(timedelta(hours=9)))
        assert paths.utc_timestamp(tokyo) == paths.utc_timestamp(noon_utc)
        assert paths.utc_timestamp(tokyo) == "2026-08-20T12-00-00Z"

    def test_a_naive_datetime_is_taken_as_utc_rather_than_local(self):
        from datetime import datetime

        naive = datetime(2026, 8, 20, 12, 0, 0)
        assert paths.utc_timestamp(naive) == "2026-08-20T12-00-00Z"

    def test_two_stamps_of_one_instant_sort_identically(self):
        from datetime import datetime, timedelta, timezone

        instant = datetime(2026, 8, 20, 23, 30, 0, tzinfo=timezone.utc)
        west = instant.astimezone(timezone(timedelta(hours=-8)))
        assert paths.utc_timestamp(west) == paths.utc_timestamp(instant)


# A manifest whose write died partway through: unterminated, and carrying bytes
# that are not valid UTF-8. Built rather than written as a literal so the file
# itself stays ASCII.
TRUNCATED_MANIFEST = b'{"deck_sha256": "' + bytes([0xFF, 0xFE]) + b" truncated"


class TestReadJsonSurvivesACrashedWrite:
    """ADR 0004 anticipates a run dying mid-write. `read_json` is the reader for
    every manifest on disk, so it has to degrade rather than raise."""

    def test_invalid_utf8_reads_as_none(self, tmp_path):
        target = tmp_path / "manifest.json"
        target.write_bytes(TRUNCATED_MANIFEST)
        assert paths.read_json(target) is None

    def test_a_directory_where_a_file_was_expected_reads_as_none(self, tmp_path):
        target = tmp_path / "manifest.json"
        target.mkdir()
        assert paths.read_json(target) is None

    def test_one_corrupt_manifest_does_not_abort_deck_discovery(self, tmp_path):
        """The failure that motivated this: `deck_slugs_with_hashes` walks every
        manifest under a subject, so one bad file must not take the rest down."""

        layout = paths.Layout(tmp_path)

        good = layout.run_dir("engr-689", "day3-principle", "2026-08-20T12-00-00Z")
        paths.write_json(paths.manifest_file(good), {"deck_sha256": "a" * 64})

        broken = layout.run_dir("engr-689", "day1-tool", "2026-08-20T12-00-00Z")
        broken.mkdir(parents=True)
        paths.manifest_file(broken).write_bytes(TRUNCATED_MANIFEST)

        found = layout.deck_slugs_with_hashes("engr-689")
        assert found == {"day3-principle": "a" * 64}
