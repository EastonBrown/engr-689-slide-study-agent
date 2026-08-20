"""Anthropic boundary for structured model calls."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from . import config, paths, schemas


T = TypeVar("T", bound=BaseModel)


class MissingApiKey(RuntimeError):
    """No Anthropic credential was available."""


class StructuredCallError(RuntimeError):
    """The model call did not yield a valid structured object."""

    def __init__(self, message: str, usage: schemas.StageUsage) -> None:
        super().__init__(message)
        self.usage = usage


@dataclass(frozen=True)
class StructuredResult(Generic[T]):
    output: T
    usage: schemas.StageUsage


def load_api_key(root: Path | None = None) -> str:
    """Read `ANTHROPIC_API_KEY` from the environment or a repo-local `.env`."""

    from_env = os.environ.get("ANTHROPIC_API_KEY")
    if from_env:
        return from_env

    dotenv = (root or paths.repo_root()) / ".env"
    if dotenv.is_file():
        for raw in dotenv.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "ANTHROPIC_API_KEY" and value.strip():
                return value.strip().strip("\"'")

    raise MissingApiKey(
        "ANTHROPIC_API_KEY is required in the environment or a gitignored .env"
    )


def create_client(root: Path | None = None) -> Any:
    import anthropic

    return anthropic.Anthropic(api_key=load_api_key(root))


def _is_retryable(error: Exception) -> bool:
    """Whether trying the same request again could plausibly succeed.

    A schema violation or unparseable JSON is retryable because the model may
    simply do better; a transport fault or a 5xx is retryable because the
    server may. Everything else is not: a bad credential, a malformed request,
    and a `TypeError` in request construction all fail identically on attempt
    two, so retrying them only spends round trips and delays the real error.
    """

    if isinstance(error, (ValidationError, json.JSONDecodeError)):
        return True

    import anthropic

    if isinstance(
        error,
        (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.RateLimitError),
    ):
        return True
    if isinstance(error, anthropic.APIStatusError):
        # 5xx is the server's problem and may pass; 4xx is the request's and
        # will not. `getattr` because the error may be constructed without one.
        return int(getattr(error, "status_code", 0) or 0) >= 500
    return False


def _is_request_fault(error: Exception) -> bool:
    """Whether this failure is about one request rather than the whole run.

    The distinction the stages need, and not the same question as whether to
    retry. An oversized or corrupt page image comes back as a 400: retrying it
    is pointless, but so is killing a 66-slide run over one bad page, so it is
    reported as a `StructuredCallError` and the caller degrades that slide
    through `reader_note`.

    A bad credential or a revoked key is the opposite: every remaining call
    fails the same way, and turning that into 132 notes each carrying the same
    authentication message would bill nothing but bury the real problem. Those
    propagate, as does anything that is not an API error at all, so a
    programming error still crashes where it happened.
    """

    import anthropic

    if isinstance(error, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return False
    return isinstance(error, anthropic.APIStatusError)


def _text_from_message(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    pieces: list[str] = []
    for block in content:
        if isinstance(block, str):
            pieces.append(block)
            continue
        if isinstance(block, dict) and block.get("type") == "text":
            pieces.append(str(block.get("text", "")))
            continue
        text = getattr(block, "text", None)
        if text is not None:
            pieces.append(str(text))
    return "\n".join(piece for piece in pieces if piece)


def _usage_from_message(message: Any, stage: str, calls: int) -> schemas.StageUsage:
    usage = getattr(message, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cache_read_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    # Server tool counts live one level down, under `server_tool_use`. Read
    # straight off `usage` this was always 0, which priced every web search at
    # nothing and reported search spend as free rather than as unmeasured.
    server_tools = getattr(usage, "server_tool_use", None)
    web_searches = int(getattr(server_tools, "web_search_requests", 0) or 0)
    cost = (
        input_tokens * config.USD_PER_MTOK_INPUT
        + output_tokens * config.USD_PER_MTOK_OUTPUT
    ) / 1_000_000
    cost += web_searches * config.USD_PER_1K_WEB_SEARCHES / 1_000
    return schemas.StageUsage(
        stage=stage,
        calls=calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        web_searches=web_searches,
        cost_usd=cost,
    )


def _add_usage(first: schemas.StageUsage, second: schemas.StageUsage) -> schemas.StageUsage:
    return schemas.StageUsage(
        stage=first.stage,
        calls=first.calls + second.calls,
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        cache_read_tokens=first.cache_read_tokens + second.cache_read_tokens,
        web_searches=first.web_searches + second.web_searches,
        cost_usd=first.cost_usd + second.cost_usd,
    )


def structured_call(
    client: Any,
    *,
    response_model: type[T],
    messages: list[dict[str, Any]],
    max_tokens: int,
    effort: str | None,
    stage: str,
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> StructuredResult[T]:
    """Call Anthropic and validate a structured JSON response."""

    output_config: dict[str, Any] = {
        "format": {
            "type": "json_schema",
            "name": response_model.__name__,
            "schema": schemas.strict_schema(response_model),
        }
    }
    if effort is not None:
        output_config["effort"] = effort

    accumulated = schemas.StageUsage(stage=stage)
    last_error: Exception | None = None
    for attempt in range(config.LLM_ATTEMPTS):
        if attempt:
            time.sleep(config.LLM_RETRY_BACKOFF_S * 2 ** (attempt - 1))
        try:
            kwargs: dict[str, Any] = {
                "model": config.MODEL_ID,
                "max_tokens": max_tokens,
                "messages": messages,
                "thinking": {"type": "adaptive"},
                "output_config": output_config,
            }
            if system is not None:
                kwargs["system"] = system
            if tools is not None:
                kwargs["tools"] = tools
            message = client.messages.create(**kwargs)
            usage = _usage_from_message(message, stage=stage, calls=1)
            accumulated = _add_usage(accumulated, usage)
            payload = json.loads(_text_from_message(message))
            return StructuredResult(
                output=response_model.model_validate(payload),
                usage=accumulated,
            )
        except Exception as error:
            if not _is_retryable(error):
                if _is_request_fault(error):
                    # Not retried, but still the stage's failure rather than the
                    # run's. `accumulated` goes with it: an earlier attempt in
                    # this loop may already have been billed, and dropping those
                    # tokens would under-report the run's cost.
                    raise StructuredCallError(str(error), accumulated) from error
                raise
            last_error = error
    raise StructuredCallError(
        str(last_error) if last_error else "structured call failed",
        accumulated,
    )
