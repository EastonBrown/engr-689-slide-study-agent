"""Structured LLM boundary tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from study_agent import config, llm, schemas


class Usage:
    input_tokens = 10
    output_tokens = 4
    cache_read_input_tokens = 2


class TextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class Citation:
    title = "Anthropic docs"
    url = "https://docs.anthropic.com/search"


class CitedTextBlock(TextBlock):
    citations = [Citation()]


class Message:
    usage = Usage()

    def __init__(self, text: str) -> None:
        self.content = [TextBlock(text)]


class CitedMessage(Message):
    def __init__(self, text: str) -> None:
        self.content = [CitedTextBlock(text)]


class Messages:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return Message(self.responses.pop(0))


class CitedMessages(Messages):
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return CitedMessage(self.responses.pop(0))


class Client:
    def __init__(self, responses: list[str]) -> None:
        self.messages = Messages(responses)


class CitedClient:
    def __init__(self, responses: list[str]) -> None:
        self.messages = CitedMessages(responses)


VALID_NOTE = """
{
  "page_role": "content",
  "title": "Retrieval",
  "reading": "The slide explains retrieval.",
  "visuals": [],
  "concepts": [],
  "verbatim_spans": ["Retrieval"],
  "reader_note": null
}
"""


def test_api_key_prefers_environment_over_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")

    assert llm.load_api_key(tmp_path) == "from-env"


def test_api_key_can_come_from_gitignored_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "OTHER=value\nANTHROPIC_API_KEY=from-file\n", encoding="utf-8"
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert llm.load_api_key(tmp_path) == "from-file"


def test_missing_api_key_refuses_with_a_message(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(llm.MissingApiKey, match="ANTHROPIC_API_KEY"):
        llm.load_api_key(tmp_path)


def test_structured_call_uses_schema_effort_thinking_and_costs():
    client = Client([VALID_NOTE])

    result = llm.structured_call(
        client,
        response_model=schemas.SlideNoteDraft,
        messages=[{"role": "user", "content": "read"}],
        max_tokens=config.MAX_TOKENS_PAGE_READER,
        effort=config.EFFORT_PAGE_READER,
        stage="page_reader",
    )

    call = client.messages.calls[0]
    assert call["model"] == config.MODEL_ID
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"]["effort"] == "low"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert result.output.title == "Retrieval"
    assert result.usage.stage == "page_reader"
    assert result.usage.calls == 1
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 4
    assert result.usage.cache_read_tokens == 2
    assert result.usage.cost_usd == pytest.approx(0.00015)


def test_structured_call_harvests_response_citations():
    client = CitedClient(
        [
            """
            {
              "answer": "Search result answer.",
              "citations": [{"title": "Model citation", "url": "https://example.com"}]
            }
            """
        ]
    )

    result = llm.structured_call(
        client,
        response_model=schemas.ResearchDraft,
        messages=[{"role": "user", "content": "look up"}],
        max_tokens=config.MAX_TOKENS_RESEARCH,
        effort=config.EFFORT_RESEARCH,
        stage="research",
    )

    assert result.citations == [
        schemas.Citation(
            title="Anthropic docs", url="https://docs.anthropic.com/search"
        )
    ]


def test_structured_call_retries_schema_violations_twice():
    client = Client(["{}", "{}", VALID_NOTE])

    result = llm.structured_call(
        client,
        response_model=schemas.SlideNoteDraft,
        messages=[{"role": "user", "content": "read"}],
        max_tokens=config.MAX_TOKENS_PAGE_READER,
        effort=config.EFFORT_PAGE_READER,
        stage="page_reader",
    )

    assert result.output.page_role == schemas.PageRole.content
    assert len(client.messages.calls) == 3
    assert result.usage.calls == 3


def test_structured_call_failure_keeps_usage_from_invalid_responses():
    client = Client(["{}", "{}", "{}"])

    with pytest.raises(llm.StructuredCallError) as error:
        llm.structured_call(
            client,
            response_model=schemas.SlideNoteDraft,
            messages=[{"role": "user", "content": "read"}],
            max_tokens=config.MAX_TOKENS_PAGE_READER,
            effort=config.EFFORT_PAGE_READER,
            stage="page_reader",
        )

    assert error.value.usage.calls == 3
    assert error.value.usage.input_tokens == 30
