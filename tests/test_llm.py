"""Structured LLM boundary tests."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from study_agent import config, llm, schemas


class Usage:
    input_tokens = 10
    output_tokens = 4
    cache_read_input_tokens = 2


class TextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class Message:
    usage = Usage()

    def __init__(self, text: str) -> None:
        self.content = [TextBlock(text)]


class Messages:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return Message(self.responses.pop(0))


class Client:
    def __init__(self, responses: list[str]) -> None:
        self.messages = Messages(responses)


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


def test_a_schema_violation_is_retried_once_for_two_attempts_in_total(no_backoff):
    """`LLM_ATTEMPTS` counts attempts, not retries after the first."""

    client = Client(["{}", VALID_NOTE])

    result = llm.structured_call(
        client,
        response_model=schemas.SlideNoteDraft,
        messages=[{"role": "user", "content": "read"}],
        max_tokens=config.MAX_TOKENS_PAGE_READER,
        effort=config.EFFORT_PAGE_READER,
        stage="page_reader",
    )

    assert result.output.page_role == schemas.PageRole.content
    assert len(client.messages.calls) == config.LLM_ATTEMPTS == 2
    assert result.usage.calls == 2


def test_structured_call_failure_keeps_usage_from_invalid_responses(no_backoff):
    client = Client(["{}", "{}"])

    with pytest.raises(llm.StructuredCallError) as error:
        llm.structured_call(
            client,
            response_model=schemas.SlideNoteDraft,
            messages=[{"role": "user", "content": "read"}],
            max_tokens=config.MAX_TOKENS_PAGE_READER,
            effort=config.EFFORT_PAGE_READER,
            stage="page_reader",
        )

    assert error.value.usage.calls == 2
    assert error.value.usage.input_tokens == 20


@pytest.fixture
def no_backoff(monkeypatch):
    """Keep the retry wait out of the test suite's wall clock."""

    monkeypatch.setattr(config, "LLM_RETRY_BACKOFF_S", 0.0)


class RaisingMessages:
    """Raises a prepared error per call, so a retry policy can be observed."""

    def __init__(self, errors: list[Exception]) -> None:
        self.errors = errors
        self.calls = 0

    def create(self, **kwargs):
        del kwargs
        self.calls += 1
        raise self.errors.pop(0)


class RaisingClient:
    def __init__(self, errors: list[Exception]) -> None:
        self.messages = RaisingMessages(errors)


def anthropic_error(name: str, *, status_code: int | None = None) -> Exception:
    """Build a real SDK error without going near the network."""

    import anthropic

    cls = getattr(anthropic, name)
    # `__new__` rather than the constructor: every SDK error wants an httpx
    # request or response object, and none of that changes how the retry policy
    # classifies it.
    error = cls.__new__(cls)
    Exception.__init__(error, name)
    if status_code is not None:
        error.status_code = status_code
    return cast(Exception, error)


def call(client, stage: str = "page_reader"):
    return llm.structured_call(
        client,
        response_model=schemas.SlideNoteDraft,
        messages=[{"role": "user", "content": "read"}],
        max_tokens=config.MAX_TOKENS_PAGE_READER,
        effort=config.EFFORT_PAGE_READER,
        stage=stage,
    )


class TestOnlyRetryableFailuresAreRetried:
    """A retry that cannot succeed is a bill, not a recovery.

    The SDK already retries 429 and 5xx with backoff underneath this loop, and
    `READER_CONCURRENCY` multiplies whatever this does by eight. Retrying a bad
    credential or a malformed request buys nothing and costs a round trip each.
    """

    def test_an_authentication_error_fails_on_the_first_attempt(self, no_backoff):
        client = RaisingClient([anthropic_error("AuthenticationError")])

        with pytest.raises(Exception) as error:
            call(client)

        assert not isinstance(error.value, llm.StructuredCallError)
        assert client.messages.calls == 1

    def test_a_bad_request_fails_on_the_first_attempt(self, no_backoff):
        client = RaisingClient([anthropic_error("BadRequestError")])

        with pytest.raises(llm.StructuredCallError):
            call(client)

        assert client.messages.calls == 1

    def test_a_bad_request_stays_the_stages_failure_not_the_runs(self, no_backoff):
        """A 400 is usually one oversized page image, not a broken run.

        Reported as a `StructuredCallError`, the page reader turns it into one
        slide's `reader_note` and keeps going. Raised raw it escapes the
        worker and takes the other 65 slides with it.
        """

        client = RaisingClient([anthropic_error("BadRequestError")])

        with pytest.raises(llm.StructuredCallError):
            call(client)

    def test_an_account_level_error_is_not_disguised_as_a_slide_failure(
        self, no_backoff
    ):
        """Every remaining call fails identically, so degrading buries it."""

        for name in ("AuthenticationError", "PermissionDeniedError"):
            client = RaisingClient([anthropic_error(name)])

            with pytest.raises(Exception) as error:
                call(client)

            assert not isinstance(error.value, llm.StructuredCallError)

    def test_a_non_retryable_failure_keeps_the_tokens_already_billed(self, no_backoff):
        """Attempt one was charged for even though attempt two refused."""

        class Mixed:
            def __init__(self):
                self.calls = 0

            def create(self, **kwargs):
                del kwargs
                self.calls += 1
                if self.calls == 1:
                    return Message("{ not json")
                raise anthropic_error("BadRequestError")

        client = Client([])
        client.messages = Mixed()

        with pytest.raises(llm.StructuredCallError) as error:
            call(client)

        assert error.value.usage.calls == 1
        assert error.value.usage.input_tokens == 10

    def test_a_programming_error_is_not_retried_and_not_reported_as_a_call_failure(
        self, no_backoff
    ):
        client = RaisingClient([TypeError("wrong argument")])

        with pytest.raises(TypeError):
            call(client)

        assert client.messages.calls == 1

    def test_a_transport_error_is_retried(self, no_backoff):
        client = RaisingClient(
            [
                anthropic_error("APIConnectionError"),
                anthropic_error("APIConnectionError"),
            ]
        )

        with pytest.raises(llm.StructuredCallError):
            call(client)

        assert client.messages.calls == 2

    def test_a_server_side_status_error_is_retried_but_a_client_side_one_is_not(
        self, no_backoff
    ):
        server = RaisingClient(
            [
                anthropic_error("APIStatusError", status_code=503),
                anthropic_error("APIStatusError", status_code=503),
            ]
        )
        with pytest.raises(llm.StructuredCallError):
            call(server)
        assert server.messages.calls == 2

        client_side = RaisingClient([anthropic_error("APIStatusError", status_code=404)])
        with pytest.raises(Exception):
            call(client_side)
        assert client_side.messages.calls == 1

    def test_the_retry_waits_before_trying_again(self, monkeypatch):
        waits: list[float] = []
        monkeypatch.setattr(llm.time, "sleep", waits.append)
        monkeypatch.setattr(config, "LLM_RETRY_BACKOFF_S", 0.5)

        client = Client(["{}", VALID_NOTE])
        call(client)

        assert waits == [0.5]


class TestWebSearchSpendIsCounted:
    """A silent zero here is worse than a wrong number: it reads as free."""

    def test_web_search_requests_are_read_from_server_tool_use_and_priced(self):
        class ServerToolUse:
            web_search_requests = 3

        class SearchUsage(Usage):
            server_tool_use = ServerToolUse()

        class SearchMessage(Message):
            usage = SearchUsage()

        class SearchMessages(Messages):
            def create(self, **kwargs):
                self.calls.append(kwargs)
                return SearchMessage(self.responses.pop(0))

        client = Client([VALID_NOTE])
        client.messages = SearchMessages([VALID_NOTE])

        result = call(client, stage="research")

        assert result.usage.web_searches == 3
        assert result.usage.cost_usd == pytest.approx(
            0.00015 + 3 * config.USD_PER_1K_WEB_SEARCHES / 1_000
        )

    def test_a_response_with_no_server_tool_use_reports_no_searches(self):
        result = call(Client([VALID_NOTE]))

        assert result.usage.web_searches == 0
