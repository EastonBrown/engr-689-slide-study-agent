"""Research-stage cache and accounting behavior."""

from __future__ import annotations

import pytest

from study_agent import paths, schemas
from study_agent.stages import research


def note(slide: int, *concepts: tuple[str, schemas.ConceptStatus]) -> schemas.SlideNote:
    return schemas.SlideNote(
        slide_number=slide,
        page_role=schemas.PageRole.content,
        title=None,
        reading="A page.",
        visuals=[],
        concepts=[
            schemas.Concept(name=name, status=status, why_it_matters="Test.")
            for name, status in concepts
        ],
        verbatim_spans=[],
        reader_note=None,
    )


class Researcher:
    def __init__(self, *, cost_per_call: float = 0.0) -> None:
        self.queries: list[str] = []
        self.usage = schemas.StageUsage(stage="research")
        self._cost_per_call = cost_per_call

    def lookup(self, concept: str) -> schemas.CacheEntry:
        self.queries.append(concept)
        self.usage = schemas.StageUsage(
            stage="research",
            calls=self.usage.calls + 1,
            cost_usd=self.usage.cost_usd + self._cost_per_call,
        )
        return schemas.CacheEntry(
            query=f"What is {concept}?",
            normalized_query=paths.normalize_query(f"What is {concept}?"),
            asked_at="2026-08-20T12:00:00Z",
            model="claude-opus-5",
            prompt_version="2026-08-20.1",
            concept=concept,
            answer=f"An explanation of {concept}.",
            citations=[schemas.Citation(title="Source", url="https://example.test/source")],
        )


def write_manifest(run_dir, *, paths_stats=None) -> None:
    paths.write_model(
        paths.manifest_file(run_dir),
        schemas.Manifest(
            schema_version=1,
            subject_slug="engr-689",
            deck_slug="deck",
            deck_sha256="a" * 64,
            deck_filename="deck.pdf",
            run_timestamp="2026-08-20T12-00-00Z",
            started_at="2026-08-20T12:00:00Z",
            model="claude-opus-5",
            prompt_version="2026-08-20.1",
            dpi=150,
            preflight=schemas.Preflight(
                readable=True, page_count=1, text_native_pages=1, text_native_fraction=1,
                image_only=False, page_width_px=1, page_height_px=1, downscaled=False,
                buildup_detection_ran=True, superseded_count=0,
            ),
            paths=paths_stats or [
                schemas.PathStats(path=schemas.PathKind.image, completed_stages=["render"]),
                schemas.PathStats(path=schemas.PathKind.text, completed_stages=["render"]),
            ],
            stage_usage=[schemas.StageUsage(stage="render")],
        ),
    )


def test_researches_only_named_concepts_caches_once_and_copies_entries(tmp_path):
    layout = paths.Layout(tmp_path)
    run_dir = tmp_path / "run"
    write_manifest(run_dir)
    reader = Researcher()

    research.research_run(
        run_dir,
        layout=layout,
        notes_by_path={
            schemas.PathKind.image: [
                note(1, ("RAG", schemas.ConceptStatus.named_only), ("known", schemas.ConceptStatus.explained_here)),
            ],
            schemas.PathKind.text: [note(1, ("RAG", schemas.ConceptStatus.named_only))],
        },
        researcher=reader,
    )

    assert reader.queries == ["RAG"]
    cached = layout.research_cache_file("What is RAG?")
    assert schemas.CacheEntry.model_validate(paths.read_json(cached)).citations
    assert schemas.CacheEntry.model_validate(paths.read_json(next(paths.run_research_dir(run_dir).iterdir()))).answer
    manifest = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    image, text = manifest.paths
    assert (image.research_lookups, image.research_cache_hits) == (1, 0)
    assert (text.research_lookups, text.research_cache_hits) == (0, 1)
    assert all("research" in item.completed_stages for item in manifest.paths)


def test_second_run_uses_the_global_cache_without_a_model_call(tmp_path):
    layout = paths.Layout(tmp_path)
    reader = Researcher()
    for index in range(2):
        run_dir = tmp_path / f"run-{index}"
        write_manifest(run_dir)
        research.research_run(
            run_dir,
            layout=layout,
            notes_by_path={schemas.PathKind.image: [note(1, ("RAG", schemas.ConceptStatus.named_only))]},
            researcher=reader,
        )
    assert reader.queries == ["RAG"]


def test_cap_is_recorded_in_the_manifest(tmp_path, monkeypatch):
    layout = paths.Layout(tmp_path)
    run_dir = tmp_path / "run"
    write_manifest(run_dir)
    monkeypatch.setattr(research.config, "RESEARCH_LOOKUP_CAP", 1)
    reader = Researcher()

    research.research_run(
        run_dir,
        layout=layout,
        notes_by_path={schemas.PathKind.image: [note(1, ("one", schemas.ConceptStatus.named_only), ("two", schemas.ConceptStatus.named_only))]},
        researcher=reader,
    )

    manifest = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    assert manifest.paths[0].research_lookups == 1
    assert manifest.paths[0].research_cap_exceeded is True


def _seed_research_cost(run_dir, *, calls: int, cost_usd: float) -> None:
    """Overwrite the manifest's research row as if an earlier invocation paid it."""

    manifest = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    manifest = manifest.model_copy(
        update={
            "stage_usage": [
                schemas.StageUsage(stage="research", calls=calls, cost_usd=cost_usd)
            ],
            "total_cost_usd": cost_usd,
        }
    )
    paths.write_model(paths.manifest_file(run_dir), manifest)


def test_a_resume_that_hits_cache_for_everything_does_not_erase_the_earlier_cost(
    tmp_path,
):
    """Sibling bug to the page-reader fix (issue #31): a resume that makes zero

    new lookups (every concept this time is already cached) must not replace
    the manifest's `research` row with a zero-cost one and silently erase real
    money an earlier invocation already spent.
    """

    layout = paths.Layout(tmp_path)
    run_dir = tmp_path / "run"
    write_manifest(run_dir)
    paths.write_model(
        layout.research_cache_file("What is RAG?"),
        Researcher().lookup("RAG"),
    )
    _seed_research_cost(run_dir, calls=3, cost_usd=0.50)
    reader = Researcher(cost_per_call=0.05)

    research.research_run(
        run_dir,
        layout=layout,
        notes_by_path={schemas.PathKind.image: [note(1, ("RAG", schemas.ConceptStatus.named_only))]},
        researcher=reader,
    )

    assert reader.queries == []  # cache hit, no new spend this invocation
    updated = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    rows = [item for item in updated.stage_usage if item.stage == "research"]
    assert len(rows) == 1
    assert rows[0].cost_usd == pytest.approx(0.50)
    assert updated.total_cost_usd == pytest.approx(0.50)


def test_a_resume_with_new_lookups_adds_to_the_earlier_invocations_cost(tmp_path):
    """A resume that researches one new concept must not drop the rest.

    The non-zero counterpart of the test above: an earlier invocation already
    paid to research some concepts, a later resume pays for one more, and the
    manifest must report the sum rather than only the newest invocation.
    """

    layout = paths.Layout(tmp_path)
    run_dir = tmp_path / "run"
    write_manifest(run_dir)
    _seed_research_cost(run_dir, calls=3, cost_usd=0.50)
    reader = Researcher(cost_per_call=0.05)

    research.research_run(
        run_dir,
        layout=layout,
        notes_by_path={
            schemas.PathKind.image: [note(1, ("new-concept", schemas.ConceptStatus.named_only))]
        },
        researcher=reader,
    )

    assert reader.queries == ["new-concept"]
    updated = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    rows = [item for item in updated.stage_usage if item.stage == "research"]
    assert len(rows) == 1
    assert rows[0].cost_usd == pytest.approx(0.55)
    assert updated.total_cost_usd == pytest.approx(0.55)
