"""Anthropic boundary for structured model calls."""

from __future__ import annotations

import json
import os
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
    citations: list[schemas.Citation] | None = None


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
    web_searches = int(getattr(usage, "web_searches", 0) or 0)
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


def _citations_from_message(message: Any) -> list[schemas.Citation]:
    content = getattr(message, "content", message)
    citations: list[schemas.Citation] = []
    for block in content if not isinstance(content, str) else []:
        for item in getattr(block, "citations", []) or []:
            title = getattr(item, "title", None)
            url = getattr(item, "url", None)
            if title and url:
                citations.append(schemas.Citation(title=str(title), url=str(url)))
        for item in getattr(block, "annotations", []) or []:
            title = getattr(item, "title", None)
            url = getattr(item, "url", None)
            if title and url:
                citations.append(schemas.Citation(title=str(title), url=str(url)))
    seen: set[tuple[str, str]] = set()
    deduped: list[schemas.Citation] = []
    for citation in citations:
        key = (citation.title, citation.url)
        if key not in seen:
            seen.add(key)
            deduped.append(citation)
    return deduped


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
    for _ in range(config.LLM_ATTEMPTS + 1):
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
                citations=_citations_from_message(message),
            )
        except (ValidationError, json.JSONDecodeError) as error:
            last_error = error
        except Exception as error:
            last_error = error
    raise StructuredCallError(
        str(last_error) if last_error else "structured call failed",
        accumulated,
    )
