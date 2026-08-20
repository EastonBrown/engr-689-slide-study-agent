"""Research stage: named-only concept lookups and the global cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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


@dataclass(frozen=True)
class ResearchLookupResult:
    answer: ResearchDraft
    usage: StageUsage


@dataclass(frozen=True)
class ResearchPathStats:
    lookups: int
    cache_hits: int
    cap_hit: bool
    usage: StageUsage


@dataclass(frozen=True)
class ResearchQuery:
    query: str
    concept_name: str


class Researcher(Protocol):
    def lookup(self, query: str, concept_name: str) -> ResearchLookupResult:
        """Look up one concept and return a cited answer."""


class AnthropicResearcher:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or llm.create_client()

    def lookup(self, query: str, concept_name: str) -> ResearchLookupResult:
        result = llm.structured_call(
            self.client,
            response_model=ResearchDraft,
            messages=[
                {
                    "role": "user",
                    "content": research_prompts.LOOKUP.format(concept=concept_name),
                }
            ],
            max_tokens=config.MAX_TOKENS_RESEARCH,
            effort=config.EFFORT_RESEARCH,
            stage=RESEARCH_STAGE,
            system=research_prompts.SYSTEM,
            tools=[
                {
                    "type": config.WEB_SEARCH_TOOL_TYPE,
                    "max_uses": config.WEB_SEARCH_MAX_USES,
                }
            ],
        )
        citations = list(result.output.citations)
        for citation in result.citations or []:
            if citation not in citations:
                citations.append(citation)
        return ResearchLookupResult(
            answer=result.output.model_copy(update={"citations": citations}),
            usage=result.usage,
        )


def _add_usage(first: StageUsage, second: StageUsage) -> StageUsage:
    return StageUsage(
        stage=first.stage,
        calls=first.calls + second.calls,
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        cache_read_tokens=first.cache_read_tokens + second.cache_read_tokens,
        web_searches=first.web_searches + second.web_searches,
        cost_usd=first.cost_usd + second.cost_usd,
    )


def _stamp(moment: datetime | None = None) -> str:
    value = moment or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_notes(run_dir: Path, path_kind: PathKind) -> list[SlideNote]:
    notes: list[SlideNote] = []
    for target in sorted(paths.notes_dir(run_dir, path_kind.value).glob("*.json")):
        payload = paths.read_json(target)
        if payload is not None:
            notes.append(SlideNote.model_validate(payload))
    return notes


def _named_only_queries(notes: list[SlideNote]) -> list[ResearchQuery]:
    queries: list[ResearchQuery] = []
    seen: set[str] = set()
    for note in notes:
        for concept in note.concepts:
            if concept.status != ConceptStatus.named_only:
                continue
            normalized = paths.normalize_query(concept.name)
            if normalized in seen:
                continue
            seen.add(normalized)
            queries.append(ResearchQuery(query=concept.name, concept_name=concept.name))
    return queries


def _copy_to_run(run_dir: Path, cache_file: Path) -> None:
    payload = paths.read_json(cache_file)
    if payload is not None:
        paths.write_json(paths.run_research_dir(run_dir) / cache_file.name, payload)


def _cache_entry(
    *,
    query: str,
    concept_name: str,
    answer: ResearchDraft,
    now: datetime | None,
) -> CacheEntry:
    return CacheEntry(
        query=query,
        normalized_query=paths.normalize_query(query),
        asked_at=_stamp(now),
        model=config.MODEL_ID,
        prompt_version=config.PROMPT_VERSION,
        concept=concept_name,
        answer=answer.answer,
        citations=answer.citations,
    )


def research_path(
    run_dir: Path,
    *,
    layout: paths.Layout,
    path_kind: PathKind,
    researcher: Researcher | None = None,
    now: datetime | None = None,
    cap: int = config.RESEARCH_LOOKUP_CAP,
) -> tuple[list[CacheEntry], ResearchPathStats]:
    """Research one path's named-only concepts, using and populating cache."""

    run_dir = Path(run_dir)
    researcher = researcher or AnthropicResearcher()
    all_queries = _named_only_queries(_load_notes(run_dir, path_kind))
    selected_queries = all_queries[:cap]
    entries: list[CacheEntry] = []
    stats = ResearchPathStats(
        lookups=0,
        cache_hits=0,
        cap_hit=len(all_queries) > cap,
        usage=StageUsage(stage=RESEARCH_STAGE),
    )

    for item in selected_queries:
        cache_file = layout.research_cache_file(item.query)
        cached = paths.read_json(cache_file)
        if cached is not None:
            entry = CacheEntry.model_validate(cached)
            _copy_to_run(run_dir, cache_file)
            entries.append(entry)
            stats = ResearchPathStats(
                lookups=stats.lookups,
                cache_hits=stats.cache_hits + 1,
                cap_hit=stats.cap_hit,
                usage=stats.usage,
            )
            continue

        result = researcher.lookup(item.query, item.concept_name)
        entry = _cache_entry(
            query=item.query,
            concept_name=item.concept_name,
            answer=result.answer,
            now=now,
        )
        paths.write_model(cache_file, entry)
        _copy_to_run(run_dir, cache_file)
        entries.append(entry)
        stats = ResearchPathStats(
            lookups=stats.lookups + 1,
            cache_hits=stats.cache_hits,
            cap_hit=stats.cap_hit,
            usage=_add_usage(stats.usage, result.usage),
        )

    return entries, stats


def _load_manifest(run_dir: Path) -> Manifest | None:
    payload = paths.read_json(paths.manifest_file(run_dir))
    return Manifest.model_validate(payload) if payload is not None else None


def _update_manifest(
    run_dir: Path,
    manifest: Manifest | None,
    stats: dict[PathKind, ResearchPathStats],
) -> None:
    if manifest is None:
        return

    stats_by_path = {stat.path: stat for stat in manifest.paths}
    usage = StageUsage(stage=RESEARCH_STAGE)
    for path_kind, path_stats in stats.items():
        existing = stats_by_path.get(path_kind, PathStats(path=path_kind))
        stages = list(existing.completed_stages)
        if RESEARCH_STAGE not in stages:
            stages.append(RESEARCH_STAGE)
        stats_by_path[path_kind] = existing.model_copy(
            update={
                "research_lookups": path_stats.lookups,
                "research_cache_hits": path_stats.cache_hits,
                "research_cap_hit": path_stats.cap_hit,
                "completed_stages": stages,
            }
        )
        usage = _add_usage(usage, path_stats.usage)

    stage_usage = [item for item in manifest.stage_usage if item.stage != RESEARCH_STAGE]
    if usage.calls:
        stage_usage.append(usage)
    manifest = manifest.model_copy(
        update={
            "paths": list(stats_by_path.values()),
            "stage_usage": stage_usage,
            "total_cost_usd": sum(item.cost_usd for item in stage_usage),
        }
    )
    paths.write_model(paths.manifest_file(run_dir), manifest)


def research_run(
    run_dir: Path,
    *,
    layout: paths.Layout | None = None,
    researcher: Researcher | None = None,
    now: datetime | None = None,
) -> None:
    """Run research on both paths and update the run manifest."""

    run_dir = Path(run_dir)
    layout = layout or paths.Layout()
    path_stats: dict[PathKind, ResearchPathStats] = {}
    for path_kind in (PathKind.image, PathKind.text):
        _, stats = research_path(
            run_dir,
            layout=layout,
            path_kind=path_kind,
            researcher=researcher,
            now=now,
        )
        path_stats[path_kind] = stats
    _update_manifest(run_dir, _load_manifest(run_dir), path_stats)
