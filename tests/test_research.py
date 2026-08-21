"""Research-stage cache and accounting behavior."""

from __future__ import annotations

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
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.usage = schemas.StageUsage(stage="research")

    def lookup(self, concept: str) -> schemas.CacheEntry:
        self.queries.append(concept)
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
