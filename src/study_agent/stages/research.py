"""Research named-but-unexplained concepts through a shared disk cache."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .. import config, llm, paths
from ..prompts import research as research_prompts
from ..schemas import (
    CacheEntry,
    ConceptStatus,
    Manifest,
    PathKind,
    PathStats,
    ResearchDraft,
    SlideNote,
    StageUsage,
)


RESEARCH_STAGE = "research"


class Researcher(Protocol):
    usage: StageUsage

    def lookup(self, concept: str) -> CacheEntry:
        """Look up one concept and return a complete cache entry."""


class AnthropicResearcher:
    """The model-backed half of research; cache IO stays deterministic below."""

    def __init__(self, client: Any | None = None) -> None:
        self.client = client or llm.create_client()
        self.usage = StageUsage(stage=RESEARCH_STAGE)

    def lookup(self, concept: str) -> CacheEntry:
        query = f"What is {concept}?"
        result = llm.structured_call(
            self.client,
            response_model=ResearchDraft,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": research_prompts.LOOKUP_CONCEPT},
                        {"type": "text", "text": query},
                    ],
                }
            ],
            max_tokens=config.MAX_TOKENS_RESEARCH,
            effort=config.EFFORT_RESEARCH,
            stage=RESEARCH_STAGE,
            tools=[
                {
                    "type": config.WEB_SEARCH_TOOL_TYPE,
                    "name": config.WEB_SEARCH_TOOL_NAME,
                    "max_uses": config.WEB_SEARCH_MAX_USES,
                }
            ],
        )
        self.usage = _add_usage(self.usage, result.usage)
        return CacheEntry(
            query=query,
            normalized_query=paths.normalize_query(query),
            asked_at=paths.utc_iso(),
            model=config.MODEL_ID,
            prompt_version=config.PROMPT_VERSION,
            concept=concept,
            answer=result.output.answer,
            citations=result.output.citations,
        )


def _add_usage(first: StageUsage, second: StageUsage) -> StageUsage:
    return StageUsage(
        stage=RESEARCH_STAGE,
        calls=first.calls + second.calls,
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        cache_read_tokens=first.cache_read_tokens + second.cache_read_tokens,
        web_searches=first.web_searches + second.web_searches,
        cost_usd=first.cost_usd + second.cost_usd,
    )


def _named_concepts(notes: list[SlideNote]) -> list[str]:
    """Return ordered, de-duplicated research triggers for one path."""

    found: list[str] = []
    seen: set[str] = set()
    for note in notes:
        for concept in note.concepts:
            if concept.status != ConceptStatus.named_only or concept.name in seen:
                continue
            seen.add(concept.name)
            found.append(concept.name)
    return found


def _cached_entry(layout: paths.Layout, query: str) -> CacheEntry | None:
    payload = paths.read_json(layout.research_cache_file(query))
    return CacheEntry.model_validate(payload) if payload is not None else None


def _copy_to_run(run_dir: Path, entry: CacheEntry) -> None:
    filename = paths.sha256_text(entry.normalized_query) + ".json"
    paths.write_model(paths.run_research_dir(run_dir) / filename, entry)


def _load_notes(run_dir: Path, path_kind: PathKind) -> list[SlideNote]:
    notes: list[SlideNote] = []
    for source in sorted(paths.notes_dir(run_dir, path_kind.value).glob("*.json")):
        payload = paths.read_json(source)
        if payload is not None:
            notes.append(SlideNote.model_validate(payload))
    return notes


def _update_manifest(
    run_dir: Path,
    counts: dict[PathKind, tuple[int, int, bool]],
    usage: StageUsage,
) -> None:
    payload = paths.read_json(paths.manifest_file(run_dir))
    if payload is None:
        return
    manifest = Manifest.model_validate(payload)
    stats_by_path = {stat.path: stat for stat in manifest.paths}
    for path_kind, (lookups, hits, capped) in counts.items():
        stat = stats_by_path.get(path_kind, PathStats(path=path_kind))
        stages = list(stat.completed_stages)
        if RESEARCH_STAGE not in stages:
            stages.append(RESEARCH_STAGE)
        stats_by_path[path_kind] = stat.model_copy(update={
            "research_lookups": lookups,
            "research_cache_hits": hits,
            "research_cap_exceeded": capped,
            "completed_stages": stages,
        })
    # Same shape as the page-reader fix for issue #31: a zero-call invocation
    # (every concept this time was already cached) must not erase a row an
    # earlier invocation paid for, and a non-zero invocation adds to that row
    # rather than replacing it — research lookups are cached per concept
    # across the whole subject, so a later resume often pays for only a few
    # new concepts on top of ones an earlier invocation already bought.
    previous = next((item for item in manifest.stage_usage if item.stage == RESEARCH_STAGE), None)
    stage_usage = [item for item in manifest.stage_usage if item.stage != RESEARCH_STAGE]
    if usage.calls:
        stage_usage.append(_add_usage(previous, usage) if previous is not None else usage)
    elif previous is not None:
        stage_usage.append(previous)
    paths.write_model(paths.manifest_file(run_dir), manifest.model_copy(update={
        "paths": list(stats_by_path.values()),
        "stage_usage": stage_usage,
        "total_cost_usd": sum(item.cost_usd for item in stage_usage),
    }))


def research_run(
    run_dir: Path,
    *,
    layout: paths.Layout | None = None,
    notes_by_path: dict[PathKind, list[SlideNote]] | None = None,
    researcher: Researcher | None = None,
) -> None:
    """Research both paths, persist cache hits, and account for this invocation."""

    run_dir = Path(run_dir)
    layout = layout or paths.Layout()
    researcher = researcher or AnthropicResearcher()
    provided = notes_by_path or {}
    counts: dict[PathKind, tuple[int, int, bool]] = {}
    for path_kind in (PathKind.image, PathKind.text):
        concepts = _named_concepts(provided.get(path_kind, _load_notes(run_dir, path_kind)))
        lookups = hits = 0
        capped = len(concepts) > config.RESEARCH_LOOKUP_CAP
        for concept in concepts[: config.RESEARCH_LOOKUP_CAP]:
            query = f"What is {concept}?"
            entry = _cached_entry(layout, query)
            if entry is None:
                entry = researcher.lookup(concept)
                paths.write_model(layout.research_cache_file(query), entry)
                lookups += 1
            else:
                hits += 1
            _copy_to_run(run_dir, entry)
        counts[path_kind] = (lookups, hits, capped)
    _update_manifest(run_dir, counts, getattr(researcher, "usage", StageUsage(stage=RESEARCH_STAGE)))
