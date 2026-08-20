"""Every schema in CONTEXT.md, as strict Pydantic models.

The models divide into three groups:

* **Artifact models** -- what is written to disk. These are the locked shapes.
* **Draft models** -- what a model call is asked to return. A draft omits the
  fields the code owns (slide numbers, ids), so the model cannot get them
  wrong, and the pipeline assembles the artifact model from the draft.
* **Registry and memory models** -- the contents of `memory/`.

`strict_schema()` turns any of them into the JSON Schema the Messages API
wants for `output_config.format`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    """Reject anything the schema does not name. Every model here inherits it."""

    model_config = ConfigDict(extra="forbid")


# --- Enums ------------------------------------------------------------------


class PageRole(str, Enum):
    # `title` shadows str.title, which mypy reports as an incompatible
    # assignment. The member name is the value CONTEXT.md locks for page_role,
    # so the name stays and the report is silenced here rather than worked
    # around with an alias nothing else would use.
    title = "title"  # type: ignore[assignment]
    agenda = "agenda"
    section_break = "section_break"
    content = "content"
    references = "references"
    blank = "blank"


class VisualKind(str, Enum):
    diagram = "diagram"
    chart = "chart"
    table = "table"
    equation = "equation"
    comparison = "comparison"
    screenshot = "screenshot"
    photo = "photo"
    decorative = "decorative"


class ConceptStatus(str, Enum):
    explained_here = "explained_here"
    named_only = "named_only"
    assumed_prior = "assumed_prior"


class PathKind(str, Enum):
    image = "image"
    text = "text"


class Source(str, Enum):
    prose = "prose"
    visual = "visual"


class AttemptKind(str, Enum):
    first_pass = "first_pass"
    retake = "retake"


# --- The slide note, ADR 0002 -----------------------------------------------


class Visual(Strict):
    kind: VisualKind
    description: str
    assertion: str | None = Field(
        description="What the figure claims. Null when the visual is decorative."
    )
    relates_to_slides: list[int] = Field(
        description="Other slides this figure refers to. Advisory, possibly empty."
    )


class Concept(Strict):
    name: str
    status: ConceptStatus
    why_it_matters: str


class SlideNoteDraft(Strict):
    """What the page reader returns. The code owns `slide_number`."""

    page_role: PageRole
    title: str | None = Field(description="Null when the page shows no title.")
    reading: str = Field(
        description="The page as a whole, in prose. May name a figure without unpacking it."
    )
    visuals: list[Visual]
    concepts: list[Concept]
    verbatim_spans: list[str] = Field(
        description="At most 3 exact strings visible on the page."
    )
    reader_note: str | None = Field(
        description="Set only when the read failed or degraded. Null otherwise."
    )


class SlideNote(SlideNoteDraft):
    slide_number: int = Field(description="1-based, equals the PDF page number.")


# --- The outline, ADR 0007 --------------------------------------------------


class OutlineTopic(Strict):
    name: str
    slides: list[int]
    is_new: bool
    created_reason: str | None = None
    degraded_slides: list[int] = Field(default_factory=list)


class SkippedSlide(Strict):
    slide_number: int
    page_role: PageRole


class BridgedFact(Strict):
    slides: list[int] = Field(min_length=2)
    statement: str
    from_visuals: list[tuple[int, int]] = Field(
        default_factory=list,
        description="Pairs of slide number and index into that slide's visuals.",
    )
    candidate_signal: str


class Outline(Strict):
    deck_slug: str
    path: PathKind
    topics: list[OutlineTopic]
    skipped: list[SkippedSlide]
    superseded: list[int] = Field(default_factory=list)
    unassigned: list[int] = Field(default_factory=list)
    bridged_facts: list[BridgedFact] = Field(default_factory=list)
    candidates_proposed: int = 0
    candidate_cap: int = 0
    topic_cap_exceeded: bool = False
    question_budget: list[tuple[str, int]] = Field(default_factory=list)
    untested_topics: list[str] = Field(default_factory=list)
    repair_attempted: bool = False


class TopicAssignmentDraft(Strict):
    """One topic as call A returns it."""

    name: str
    slides: list[int]
    is_new: bool
    created_reason: str | None = Field(
        description="Why this topic is new. Null when reusing an existing topic name."
    )


class GroupingDraft(Strict):
    """Call A: grouping and topic assignment over the compacted notes."""

    topics: list[TopicAssignmentDraft]


class BridgeConfirmationDraft(Strict):
    candidate_index: int = Field(description="Index into the candidate list as offered.")
    confirmed: bool
    statement: str | None = Field(
        description="The joined fact. Null when the candidate is rejected."
    )
    from_visuals: list[tuple[int, int]] = Field(
        description="Slide number and index into that slide's visuals. May be empty."
    )


class BridgeDraft(Strict):
    """Call B: confirmation or rejection of each proposed candidate."""

    confirmations: list[BridgeConfirmationDraft]


# --- The quiz, ADR 0005 -----------------------------------------------------


class QuestionDraft(Strict):
    stem: str
    options: list[str]
    correct_index: int
    explanation: str
    distractor_rationale: list[str | None]
    slide_citations: list[int]
    topic: str
    source: Source


class QuizDraft(Strict):
    questions: list[QuestionDraft]


class Question(QuestionDraft):
    question_id: str


class Quiz(Strict):
    quiz_id: str
    subject_slug: str
    deck_slug: str | None = None
    run_timestamp: str | None = None
    kind: AttemptKind = AttemptKind.first_pass
    generated_at: str
    covered_slide_count: int = Field(
        description="Covered slides the quiz was drawn from, stated in the header."
    )
    questions: list[Question]
    dropped_count: int = 0


class Response(Strict):
    question_id: str
    topic: str
    chosen_index: int
    correct: bool


class Attempt(Strict):
    attempt_id: str
    subject_slug: str
    deck_slug: str | None
    run_timestamp: str | None
    quiz_sha256: str
    kind: AttemptKind
    taken_at: str
    responses: list[Response]


class GradedQuestion(Strict):
    """One row of what the grader hands back. Not written to disk on its own."""

    question_id: str
    topic: str
    stem: str
    chosen_index: int
    correct_index: int
    correct: bool
    explanation: str
    chosen_rationale: str | None
    slide_citations: list[int]
    source: Source


class TopicRollup(Strict):
    topic: str
    correct: int
    seen: int


class GradeResult(Strict):
    attempt: Attempt
    questions: list[GradedQuestion]
    rollup: list[TopicRollup]
    correct: int
    total: int


# --- Memory, ADR 0003 and ADR 0004 ------------------------------------------


class SubjectEntry(Strict):
    slug: str
    display_name: str
    created_at: str


class SubjectsRegistry(Strict):
    """`memory/subjects.json`, the authority on which subjects exist.

    No `schema_version`: ADR 0004 puts that field on `manifest.json` and
    `profile.json` and nowhere else.
    """

    subjects: list[SubjectEntry] = Field(default_factory=list)


class TopicRecord(Strict):
    name: str
    first_seen_deck: str
    decks: list[str] = Field(default_factory=list)
    slide_citations: list[tuple[str, int]] = Field(default_factory=list)
    exposure: int = 0
    created_reason: str | None = None


class Profile(Strict):
    schema_version: int
    subject_slug: str
    topics: list[TopicRecord] = Field(default_factory=list)


class TopicContribution(Strict):
    name: str
    slides: list[int]
    is_new: bool
    created_reason: str | None = None


class DeckContribution(Strict):
    subject_slug: str
    deck_slug: str
    deck_sha256: str
    run_timestamp: str
    contributed_at: str
    topics: list[TopicContribution]


class TopicPerformance(Strict):
    """Derived from attempts, never stored. Reported as a pair, never a score."""

    topic: str
    correct: int
    seen: int
    insufficient_evidence: bool


# --- Research ---------------------------------------------------------------


class Citation(Strict):
    title: str
    url: str


class CacheEntry(Strict):
    query: str
    normalized_query: str
    asked_at: str
    model: str
    prompt_version: str
    concept: str
    answer: str
    citations: list[Citation] = Field(min_length=1)


class ResearchDraft(Strict):
    answer: str = Field(description="A short synthesis, three sentences at most.")
    citations: list[Citation] = Field(min_length=1)


# --- The manifest, ADR 0004 -------------------------------------------------


class Preflight(Strict):
    readable: bool
    page_count: int
    text_native_pages: int
    text_native_fraction: float
    image_only: bool
    page_width_px: int
    page_height_px: int
    downscaled: bool
    buildup_detection_ran: bool
    superseded_count: int
    superseded: list[int] = Field(default_factory=list)
    long_deck: bool = False


class StageUsage(Strict):
    stage: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    web_searches: int = 0
    cost_usd: float = 0.0


class PathStats(Strict):
    path: PathKind
    slides_attempted: int = 0
    slides_succeeded: int = 0
    reader_notes: int = Field(default=0, description="Count of non-null reader_note.")
    research_lookups: int = 0
    research_cache_hits: int = 0
    research_cap_hit: bool = False
    review_calls: int = 0
    review_input_tokens: int = 0
    review_output_tokens: int = 0
    review_cost_usd: float = 0.0
    completed_stages: list[str] = Field(default_factory=list)


class Manifest(Strict):
    schema_version: int
    subject_slug: str
    deck_slug: str
    deck_sha256: str
    deck_filename: str
    run_timestamp: str
    started_at: str
    ended_at: str | None = None
    model: str
    prompt_version: str
    dpi: int
    preflight: Preflight
    paths: list[PathStats] = Field(default_factory=list)
    stage_usage: list[StageUsage] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    quiz_questions: int = 0
    quiz_dropped: int = 0
    topic_cap_exceeded: bool = False
    error: str | None = None


# --- JSON Schema for the API ------------------------------------------------


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """A JSON Schema the Messages API accepts for `output_config.format`.

    Pydantic emits `$defs` and leaves objects open. The API wants every object
    closed and every property required, so a nullable field is expressed as a
    union with null rather than as a key the model may omit.
    """

    schema = model.model_json_schema()
    _close(schema)
    schema.pop("title", None)
    return schema


# Keywords whose value is a *mapping* of name to subschema, and whose values
# therefore have to be walked one at a time rather than treated as a schema.
_SCHEMA_MAPS = ("$defs", "definitions", "properties", "patternProperties")
# Keywords whose value is a list of subschemas.
_SCHEMA_LISTS = ("anyOf", "allOf", "oneOf", "prefixItems")
# Keywords whose value is a single subschema.
_SCHEMA_NODES = ("items", "additionalItems", "not", "contains")


def _close(node: Any) -> None:
    """Close one schema node and everything nested under it.

    The mapping keywords matter: `{"$defs": {"Visual": {...}}}` is a dict whose
    keys are model names, not schema keywords, so recursing into the container
    itself reaches nothing. Every nested model has to be walked by value or a
    defaulted field on it stays optional at the API boundary.
    """

    if not isinstance(node, dict):
        return

    for key in _SCHEMA_MAPS:
        for child in node.get(key, {}).values():
            _close(child)
    for key in _SCHEMA_LISTS:
        for child in node.get(key, []):
            _close(child)
    for key in _SCHEMA_NODES:
        if key in node:
            _close(node[key])

    if node.get("type") == "object" or "properties" in node:
        node["additionalProperties"] = False
        node["required"] = list(node.get("properties", {}).keys())
    node.pop("default", None)
