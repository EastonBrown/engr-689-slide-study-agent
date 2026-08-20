"""The knobs the rest of the pipeline reads, and the rule that keeps it portable."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from study_agent import config, paths


class TestIdentityWrittenIntoArtifacts:
    def test_prompt_version_is_a_single_string(self):
        """One string covers every prompt, per docs/spec.md."""

        assert isinstance(config.PROMPT_VERSION, str)
        assert config.PROMPT_VERSION.strip() == config.PROMPT_VERSION
        assert config.PROMPT_VERSION

    def test_there_is_no_second_per_stage_prompt_version(self):
        versions = [n for n in dir(config) if "PROMPT_VERSION" in n]
        assert versions == ["PROMPT_VERSION"]

    def test_schema_version_is_an_int(self):
        assert isinstance(config.SCHEMA_VERSION, int)


class TestTheLockedNumbers:
    def test_one_model_everywhere_per_adr_0001(self):
        assert config.MODEL_ID == "claude-opus-5"

    def test_the_render_dpi_is_150(self):
        assert config.RENDER_DPI == 150

    def test_the_caps_match_the_ticket(self):
        assert config.TOPIC_CAP == 12
        assert config.RESEARCH_LOOKUP_CAP == 15
        assert config.QUIZ_QUESTIONS == 10

    def test_effort_per_stage_matches_adr_0001(self):
        assert config.EFFORT_PAGE_READER == "low"
        assert config.EFFORT_OUTLINE == "high"
        assert config.EFFORT_REVIEW == "high"
        assert config.EFFORT_QUIZ == "high"
        assert config.EFFORT_RESEARCH is None

    def test_the_reader_pool_is_bounded(self):
        assert isinstance(config.READER_CONCURRENCY, int)
        assert config.READER_CONCURRENCY > 0

    def test_build_up_detection_can_be_disabled_outright(self):
        assert isinstance(config.BUILDUP_DETECTION_ENABLED, bool)

    def test_performance_needs_three_sightings_per_adr_0005(self):
        assert config.MIN_SIGHTINGS_FOR_PERFORMANCE == 3


# --- No hardcoded absolute paths, docs/spec.md ------------------------------

SOURCE_FILES = sorted((paths.repo_root() / "src").rglob("*.py"))

# A drive letter, a UNC share, or a POSIX root in a string literal.
ABSOLUTE_PATH = re.compile(r"""['"](?:[A-Za-z]:[\\/]|\\\\|/(?:home|Users|mnt|opt|var)/)""")


def test_the_source_tree_is_not_empty():
    """Guards the scan below from passing because it found nothing to scan."""

    assert SOURCE_FILES


@pytest.mark.parametrize("source", SOURCE_FILES, ids=lambda p: p.name)
def test_no_absolute_path_appears_anywhere_in_the_source(source: Path):
    for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        assert not ABSOLUTE_PATH.search(line), f"{source.name}:{number}: {line.strip()}"


class TestEverythingResolvesFromTheRepoRoot:
    def test_the_repo_root_is_the_directory_holding_docs_and_src(self):
        root = paths.repo_root()
        assert (root / "docs" / "spec.md").is_file()
        assert (root / "src" / "study_agent").is_dir()

    def test_a_layout_rooted_in_tmp_puts_every_tree_under_tmp(self, tmp_path):
        layout = paths.Layout(tmp_path)
        trees = [
            layout.runs_dir(),
            layout.memory_dir(),
            layout.subjects_file(),
            layout.profile_file("engr-689"),
            layout.attempts_dir("engr-689"),
            layout.retakes_dir("engr-689"),
            layout.contributions_dir("engr-689"),
            layout.research_cache_dir(),
            layout.figure_only_facts_file(),
            layout.golden_run_dir(),
        ]
        for tree in trees:
            assert tmp_path in tree.parents, tree

    def test_the_default_layout_is_rooted_at_the_repo_root(self):
        assert paths.Layout().root == paths.repo_root()


class TestSlugCollisionsSeparateOnDisk:
    def test_two_pdfs_that_slugify_alike_get_different_run_directories(self, tmp_path):
        """The acceptance criterion, taken all the way to the directory."""

        layout = paths.Layout(tmp_path)
        first_sha, second_sha = "a" * 64, "b" * 64

        first = paths.deck_slug("Day3 Principle.pdf", first_sha, {})
        second = paths.deck_slug("day3  principle.PDF", second_sha, {first: first_sha})

        assert first != second
        assert layout.run_dir("engr-689", first, "t") != layout.run_dir(
            "engr-689", second, "t"
        )

    def test_the_same_pdf_re_run_keeps_its_deck_directory(self, tmp_path):
        """A re-run is a new timestamp under the same deck, per ADR 0004."""

        layout = paths.Layout(tmp_path)
        sha = "c" * 64
        slug = paths.deck_slug("Day3 Principle.pdf", sha, {"day3-principle": sha})

        assert slug == "day3-principle"
        assert layout.run_dir("engr-689", slug, "t1") != layout.run_dir(
            "engr-689", slug, "t2"
        )
        assert (
            layout.run_dir("engr-689", slug, "t1").parent
            == layout.run_dir("engr-689", slug, "t2").parent
        )
