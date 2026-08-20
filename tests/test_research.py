"""Research stage and cache behaviour."""

from __future__ import annotations

from datetime import datetime, timezone

from study_agent import config, paths, schemas
from study_agent.stages import research


def note(slide_number: int, concepts: list[schemas.Concept]) -> schemas.SlideNote:
    return schemas.SlideNote(
        slide_number=slide_number,
        page_role=schemas.PageRole.content,
        title="Slide",
        reading="reading",
        visuals=[],
        concepts=concepts,
        verbatim_spans=[],
        reader_note=None,
    )


def concept(name: str, status: schemas.ConceptStatus) -> schemas.Concept:
    return schemas.Concept(name=name, status=status, why_it_matters="matters")


class FakeResearcher:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def lookup(self, query: str, concept_name: str) -> research.ResearchLookupResult:
        self.queries.append(query)
        return research.ResearchLookupResult(
            answer=schemas.ResearchDraft(
                answer=f"answer for {concept_name}",
                citations=[schemas.Citation(title="Source", url="https://example.com")],
            ),
            usage=schemas.StageUsage(
                stage="research",
                calls=1,
                input_tokens=10,
                output_tokens=5,
                web_searches=1,
                cost_usd=0.1,
            ),
        )


def manifest(subject: str = "engr-689") -> schemas.Manifest:
    return schemas.Manifest(
        schema_version=config.SCHEMA_VERSION,
        subject_slug=subject,
        deck_slug="deck",
        deck_sha256="a" * 64,
        deck_filename="deck.pdf",
        run_timestamp="2026-08-20T12-00-00Z",
        started_at="2026-08-20T12-00-00Z",
        ended_at="2026-08-20T12-00-00Z",
        model=config.MODEL_ID,
        prompt_version=config.PROMPT_VERSION,
        dpi=config.RENDER_DPI,
        preflight=schemas.Preflight(
            readable=True,
            page_count=1,
            text_native_pages=1,
            text_native_fraction=1.0,
            image_only=False,
            page_width_px=1,
            page_height_px=1,
            downscaled=False,
            buildup_detection_ran=True,
            superseded_count=0,
            superseded=[],
        ),
        paths=[
            schemas.PathStats(path=schemas.PathKind.image, completed_stages=["render", "page_reader"]),
            schemas.PathStats(path=schemas.PathKind.text, completed_stages=["render", "page_reader"]),
        ],
        stage_usage=[schemas.StageUsage(stage="render")],
        total_cost_usd=0,
    )


def test_only_named_only_concepts_trigger_lookup(tmp_path):
    run_dir = tmp_path / "run"
    paths.write_model(
        paths.page_note(run_dir, "image", 1),
        note(
            1,
            [
                concept("RAG", schemas.ConceptStatus.named_only),
                concept("attention", schemas.ConceptStatus.explained_here),
                concept("neural network", schemas.ConceptStatus.assumed_prior),
            ],
        ),
    )
    researcher = FakeResearcher()

    entries, stats = research.research_path(
        run_dir,
        layout=paths.Layout(tmp_path),
        path_kind=schemas.PathKind.image,
        researcher=researcher,
        now=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert researcher.queries == ["RAG"]
    assert [entry.concept for entry in entries] == ["RAG"]
    assert stats.lookups == 1
    assert stats.cache_hits == 0


def test_cache_entries_are_keyed_by_normalized_query_and_copied_to_run(tmp_path):
    run_dir = tmp_path / "run"
    layout = paths.Layout(tmp_path)
    paths.write_model(
        paths.page_note(run_dir, "image", 1),
        note(1, [concept("  What   is RAG? ", schemas.ConceptStatus.named_only)]),
    )
    researcher = FakeResearcher()

    entries, _ = research.research_path(
        run_dir,
        layout=layout,
        path_kind=schemas.PathKind.image,
        researcher=researcher,
        now=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
    )

    expected_cache = layout.research_cache_file("what is rag")
    assert expected_cache.is_file()
    assert (paths.run_research_dir(run_dir) / expected_cache.name).is_file()
    entry = schemas.CacheEntry.model_validate(paths.read_json(expected_cache))
    assert entry == entries[0]
    assert entry.query == "  What   is RAG? "
    assert entry.normalized_query == "what is rag"
    assert entry.citations == [schemas.Citation(title="Source", url="https://example.com")]


def test_second_run_over_same_concept_makes_zero_api_calls_and_records_cache_hit(tmp_path):
    layout = paths.Layout(tmp_path)
    first_run = tmp_path / "first"
    second_run = tmp_path / "second"
    for run_dir in (first_run, second_run):
        paths.write_model(
            paths.page_note(run_dir, "image", 1),
            note(1, [concept("RAG", schemas.ConceptStatus.named_only)]),
        )

    first_researcher = FakeResearcher()
    research.research_path(
        first_run,
        layout=layout,
        path_kind=schemas.PathKind.image,
        researcher=first_researcher,
        now=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
    )
    second_researcher = FakeResearcher()
    _, stats = research.research_path(
        second_run,
        layout=layout,
        path_kind=schemas.PathKind.image,
        researcher=second_researcher,
        now=datetime(2026, 8, 20, 12, 1, 0, tzinfo=timezone.utc),
    )

    assert first_researcher.queries == ["RAG"]
    assert second_researcher.queries == []
    assert stats.lookups == 0
    assert stats.cache_hits == 1


def test_lookup_cap_is_per_path_and_recorded(tmp_path):
    run_dir = tmp_path / "run"
    for path_kind in ("image", "text"):
        paths.write_model(
            paths.page_note(run_dir, path_kind, 1),
            note(
                1,
                [
                    concept(f"{path_kind}-{index}", schemas.ConceptStatus.named_only)
                    for index in range(config.RESEARCH_LOOKUP_CAP + 1)
                ],
            ),
        )
    paths.write_model(paths.manifest_file(run_dir), manifest())
    researcher = FakeResearcher()

    research.research_run(
        run_dir,
        layout=paths.Layout(tmp_path),
        researcher=researcher,
        now=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
    )

    after = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    image = next(stat for stat in after.paths if stat.path == schemas.PathKind.image)
    text = next(stat for stat in after.paths if stat.path == schemas.PathKind.text)
    assert image.research_lookups == config.RESEARCH_LOOKUP_CAP
    assert text.research_lookups == config.RESEARCH_LOOKUP_CAP
    assert image.research_cap_hit is True
    assert text.research_cap_hit is True
    assert len(researcher.queries) == config.RESEARCH_LOOKUP_CAP * 2


def test_research_run_updates_manifest_with_cache_hits_usage_and_stage(tmp_path):
    run_dir = tmp_path / "run"
    layout = paths.Layout(tmp_path)
    paths.write_model(paths.manifest_file(run_dir), manifest())
    for path_kind in ("image", "text"):
        paths.write_model(
            paths.page_note(run_dir, path_kind, 1),
            note(1, [concept("RAG", schemas.ConceptStatus.named_only)]),
        )
    researcher = FakeResearcher()

    research.research_run(
        run_dir,
        layout=layout,
        researcher=researcher,
        now=datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc),
    )

    after = schemas.Manifest.model_validate(paths.read_json(paths.manifest_file(run_dir)))
    image = next(stat for stat in after.paths if stat.path == schemas.PathKind.image)
    text = next(stat for stat in after.paths if stat.path == schemas.PathKind.text)
    usage = next(item for item in after.stage_usage if item.stage == "research")
    assert image.research_lookups == 1
    assert text.research_cache_hits == 1
    assert all("research" in stat.completed_stages for stat in after.paths)
    assert usage.calls == 1
    assert usage.web_searches == 1
    assert after.total_cost_usd == 0.1
