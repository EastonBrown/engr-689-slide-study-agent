"""Every schema in CONTEXT.md round-trips a valid fixture and rejects an invalid one.

The fixtures are hand-written rather than generated, so a schema that drifts
from CONTEXT.md fails here instead of failing at the first model call.
"""

from __future__ import annotations

import inspect
import json

import pytest
from pydantic import ValidationError

from study_agent import schemas
from study_agent.schemas import Strict


def round_trip(model_cls, payload: dict):
    """Validate, dump, and re-validate. Returns the second instance."""

    first = model_cls.model_validate(payload)
    dumped = json.loads(first.model_dump_json())
    second = model_cls.model_validate(dumped)
    assert second == first
    return second


# --- Fixtures, written by hand against CONTEXT.md ---------------------------

VISUAL = {
    "kind": "diagram",
    "description": "A three-box pipeline with arrows left to right.",
    "assertion": "Retrieval precedes generation.",
    "relates_to_slides": [56],
}

CONCEPT = {
    "name": "retrieval-augmented generation",
    "status": "named_only",
    "why_it_matters": "The deck names it and never explains it.",
}

SLIDE_NOTE = {
    "slide_number": 55,
    "page_role": "content",
    "title": "The retrieval step",
    "reading": "The page introduces retrieval as the first half of the pipeline.",
    "visuals": [VISUAL],
    "concepts": [CONCEPT],
    "verbatim_spans": ["Retrieval-Augmented Generation"],
    "reader_note": None,
}

OUTLINE = {
    "deck_slug": "day3-principle",
    "path": "image",
    "topics": [
        {
            "name": "Retrieval",
            "slides": [55, 56],
            "is_new": True,
            "created_reason": "No existing topic covers retrieval.",
            "degraded_slides": [],
        }
    ],
    "skipped": [{"slide_number": 1, "page_role": "title"}],
    "superseded": [],
    "unassigned": [],
    "bridged_facts": [
        {
            "slides": [55, 56],
            "statement": "The pipeline retrieves before it generates.",
            "from_visuals": [[55, 0], [56, 0]],
            "candidate_signal": "relates_to_slides",
        }
    ],
    "candidates_proposed": 4,
    "candidate_cap": 30,
    "topic_cap_exceeded": False,
    "question_budget": [["Retrieval", 10]],
    "repair_attempted": False,
}

QUESTION = {
    "question_id": "day3-principle-q01",
    "stem": "What must happen before generation in the pipeline shown?",
    "options": ["Retrieval", "Fine-tuning", "Quantization", "Distillation"],
    "correct_index": 0,
    "explanation": "The diagram orders retrieval ahead of generation.",
    "distractor_rationale": [
        None,
        "Not in the deck.",
        "Not in the deck.",
        "Not in the deck.",
    ],
    "slide_citations": [55],
    "topic": "Retrieval",
    "source": "visual",
}

QUIZ = {
    "quiz_id": "day3-principle-2026-08-20T12-00-00Z",
    "subject_slug": "engr-689",
    "deck_slug": "day3-principle",
    "run_timestamp": "2026-08-20T12-00-00Z",
    "kind": "first_pass",
    "generated_at": "2026-08-20T12-00-00Z",
    "covered_slide_count": 61,
    "questions": [QUESTION],
    "dropped_count": 0,
}

ATTEMPT = {
    "attempt_id": "2026-08-20T12-05-00Z-a1b2c3",
    "subject_slug": "engr-689",
    "deck_slug": "day3-principle",
    "run_timestamp": "2026-08-20T12-00-00Z",
    "quiz_sha256": "f" * 64,
    "kind": "first_pass",
    "taken_at": "2026-08-20T12-05-00Z",
    "responses": [
        {
            "question_id": "day3-principle-q01",
            "topic": "Retrieval",
            "chosen_index": 0,
            "correct": True,
        }
    ],
}

TOPIC_RECORD = {
    "name": "Retrieval",
    "first_seen_deck": "day3-principle",
    "decks": ["day3-principle"],
    "slide_citations": [["day3-principle", 55]],
    "exposure": 2,
    "created_reason": "No existing topic covers retrieval.",
}

PROFILE = {
    "schema_version": 1,
    "subject_slug": "engr-689",
    "topics": [TOPIC_RECORD],
}

SUBJECTS_REGISTRY = {
    "subjects": [
        {
            "slug": "engr-689",
            "display_name": "ENGR 689",
            "created_at": "2026-08-19T00-00-00Z",
        }
    ]
}

DECK_CONTRIBUTION = {
    "subject_slug": "engr-689",
    "deck_slug": "day3-principle",
    "deck_sha256": "a" * 64,
    "run_timestamp": "2026-08-20T12-00-00Z",
    "contributed_at": "2026-08-20T12-10-00Z",
    "topics": [
        {
            "name": "Retrieval",
            "slides": [55, 56],
            "is_new": True,
            "created_reason": "New.",
        }
    ],
}

CACHE_ENTRY = {
    "query": "What is retrieval-augmented generation?",
    "normalized_query": "what is retrieval-augmented generation",
    "asked_at": "2026-08-20T12-00-00Z",
    "model": "claude-opus-5",
    "prompt_version": "2026-08-20.1",
    "concept": "retrieval-augmented generation",
    "answer": "Retrieval-augmented generation grounds output in fetched documents.",
    "citations": [{"title": "RAG overview", "url": "https://example.invalid/rag"}],
}

PREFLIGHT = {
    "readable": True,
    "page_count": 66,
    "text_native_pages": 64,
    "text_native_fraction": 0.97,
    "image_only": False,
    "page_width_px": 2000,
    "page_height_px": 1125,
    "downscaled": False,
    "buildup_detection_ran": True,
    "superseded_count": 0,
    "superseded": [],
    "long_deck": False,
}

MANIFEST = {
    "schema_version": 1,
    "subject_slug": "engr-689",
    "deck_slug": "day3-principle",
    "deck_sha256": "a" * 64,
    "deck_filename": "Day3 Principle.pdf",
    "run_timestamp": "2026-08-20T12-00-00Z",
    "started_at": "2026-08-20T12-00-00Z",
    "ended_at": "2026-08-20T12-30-00Z",
    "model": "claude-opus-5",
    "prompt_version": "2026-08-20.1",
    "dpi": 150,
    "preflight": PREFLIGHT,
    "paths": [
        {
            "path": "image",
            "slides_attempted": 66,
            "slides_succeeded": 66,
            "reader_notes": 1,
            "research_lookups": 12,
            "research_cache_hits": 3,
            "completed_stages": ["render", "page_reader"],
        }
    ],
    "stage_usage": [
        {
            "stage": "page_reader",
            "calls": 66,
            "input_tokens": 100,
            "output_tokens": 200,
            "cache_read_tokens": 0,
            "web_searches": 0,
            "cost_usd": 0.01,
        }
    ],
    "total_cost_usd": 0.01,
    "quiz_questions": 10,
    "quiz_dropped": 0,
    "topic_cap_exceeded": False,
    "error": None,
}

VALID_FIXTURES = [
    (schemas.Visual, VISUAL),
    (schemas.Concept, CONCEPT),
    (schemas.SlideNote, SLIDE_NOTE),
    (schemas.Outline, OUTLINE),
    (schemas.Question, QUESTION),
    (schemas.Quiz, QUIZ),
    (schemas.Attempt, ATTEMPT),
    (schemas.TopicRecord, TOPIC_RECORD),
    (schemas.Profile, PROFILE),
    (schemas.SubjectsRegistry, SUBJECTS_REGISTRY),
    (schemas.DeckContribution, DECK_CONTRIBUTION),
    (schemas.CacheEntry, CACHE_ENTRY),
    (schemas.Preflight, PREFLIGHT),
    (schemas.Manifest, MANIFEST),
]

FIXTURE_IDS = [model.__name__ for model, _ in VALID_FIXTURES]


@pytest.mark.parametrize("model_cls,payload", VALID_FIXTURES, ids=FIXTURE_IDS)
def test_a_valid_fixture_round_trips(model_cls, payload):
    round_trip(model_cls, payload)


@pytest.mark.parametrize("model_cls,payload", VALID_FIXTURES, ids=FIXTURE_IDS)
def test_an_unknown_field_is_a_failure_not_a_silent_drop(model_cls, payload):
    with pytest.raises(ValidationError):
        model_cls.model_validate({**payload, "surprise": "extra"})


@pytest.mark.parametrize("model_cls,payload", VALID_FIXTURES, ids=FIXTURE_IDS)
def test_a_missing_required_field_is_a_failure(model_cls, payload):
    required = [
        name
        for name, field in model_cls.model_fields.items()
        if field.is_required() and name in payload
    ]
    if not required:
        pytest.skip("every field on this model has a default")
    short = {k: v for k, v in payload.items() if k != required[0]}
    with pytest.raises(ValidationError):
        model_cls.model_validate(short)


class TestStrictness:
    def test_every_model_in_the_module_forbids_extras(self):
        for _, obj in inspect.getmembers(schemas, inspect.isclass):
            if issubclass(obj, Strict) and obj is not Strict:
                assert obj.model_config.get("extra") == "forbid", obj.__name__

    def test_an_unknown_enum_member_is_rejected(self):
        with pytest.raises(ValidationError):
            schemas.Visual.model_validate({**VISUAL, "kind": "mechanism"})

    def test_a_page_role_outside_the_six_is_rejected(self):
        with pytest.raises(ValidationError):
            schemas.SlideNote.model_validate({**SLIDE_NOTE, "page_role": "appendix"})

    def test_a_bridged_fact_needs_at_least_two_slides(self):
        with pytest.raises(ValidationError):
            schemas.BridgedFact.model_validate(
                {
                    "slides": [55],
                    "statement": "Half a bridge.",
                    "from_visuals": [],
                    "candidate_signal": "relates_to_slides",
                }
            )


class TestTheLockedShapes:
    def test_visual_kind_includes_table_and_photo(self):
        """Amendment 3 in docs/spec.md."""

        kinds = {k.value for k in schemas.VisualKind}
        assert {"table", "photo"} <= kinds
        assert kinds == {
            "diagram",
            "chart",
            "table",
            "equation",
            "comparison",
            "screenshot",
            "photo",
            "decorative",
        }

    def test_a_decorative_visual_carries_a_null_assertion(self):
        visual = schemas.Visual.model_validate(
            {
                "kind": "decorative",
                "description": "A stock photo of a laptop.",
                "assertion": None,
                "relates_to_slides": [],
            }
        )
        assert visual.assertion is None

    def test_an_empty_concepts_list_is_valid_and_survives_the_round_trip(self):
        note = round_trip(schemas.SlideNote, {**SLIDE_NOTE, "concepts": []})
        assert note.concepts == []

    def test_a_degraded_read_keeps_its_reader_note(self):
        note = round_trip(
            schemas.SlideNote, {**SLIDE_NOTE, "reader_note": "Page rendered blank."}
        )
        assert note.reader_note == "Page rendered blank."

    def test_the_reader_draft_does_not_carry_a_slide_number(self):
        """The code owns the slide number, so the model cannot get it wrong."""

        assert "slide_number" not in schemas.SlideNoteDraft.model_fields
        assert "slide_number" in schemas.SlideNote.model_fields

    def test_schema_version_is_on_the_manifest_and_profile_and_nowhere_else(self):
        carriers = {
            name
            for name, obj in inspect.getmembers(schemas, inspect.isclass)
            if issubclass(obj, Strict) and "schema_version" in obj.model_fields
        }
        assert carriers == {"Manifest", "Profile"}


class TestStrictSchemaForTheApi:
    DRAFTS = [
        schemas.SlideNoteDraft,
        schemas.GroupingDraft,
        schemas.BridgeDraft,
        schemas.QuizDraft,
        schemas.ResearchDraft,
    ]

    @staticmethod
    def every_node(node, seen=None):
        """Every dict anywhere in the schema, found without assuming its shape.

        Deliberately not the traversal `strict_schema` uses. An earlier version
        of both walked `$defs` and `properties` as containers rather than by
        value, so the test agreed with the bug and passed on a schema whose
        nested models were never closed.
        """

        if isinstance(node, dict):
            yield node
            children = node.values()
        elif isinstance(node, list):
            children = node
        else:
            return
        for child in children:
            yield from TestStrictSchemaForTheApi.every_node(child)

    @pytest.mark.parametrize("model_cls", DRAFTS, ids=lambda m: m.__name__)
    def test_every_object_is_closed_and_every_property_required(self, model_cls):
        schema = schemas.strict_schema(model_cls)
        objects = 0
        for node in self.every_node(schema):
            assert "default" not in node
            if node.get("type") == "object" or "properties" in node:
                objects += 1
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node.get("properties", {}))
        assert objects, "found no object to check"

    def test_a_defaulted_field_on_a_nested_model_is_still_required(self):
        """The API wants every property required, however deep it sits."""

        class Inner(schemas.Strict):
            a: str
            b: int = 7

        class Outer(schemas.Strict):
            inner: Inner
            c: str = "x"

        schema = schemas.strict_schema(Outer)
        inner = schema["$defs"]["Inner"]
        assert set(inner["required"]) == {"a", "b"}
        assert inner["additionalProperties"] is False
        assert "default" not in inner["properties"]["b"]

    def test_a_nullable_field_is_a_union_with_null_not_an_optional_key(self):
        schema = schemas.strict_schema(schemas.SlideNoteDraft)
        title = schema["properties"]["title"]
        assert {"type": "null"} in title["anyOf"]
        assert "title" in schema["required"]
