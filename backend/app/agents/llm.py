"""LLM access behind one small interface: Azure OpenAI (Microsoft Foundry), a fake for tests, and a cache.

All agent calls return pydantic models (structured outputs), never free text, so numbers and
evidence can be validated by code before anything reaches the screen.

LLM_PROVIDER = azure | fake     LLM_CACHE = readwrite (default) | replay (cache only) | off
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "cache" / "llm"


class LLMClient(Protocol):
    name: str

    def complete(self, system: str, user: str, schema: type[T], agent: str) -> T: ...


class AzureLLM:
    """Azure OpenAI v1 endpoint with keyless auth (az login + RBAC role)."""

    def __init__(self, deployment: str | None = None, reasoning_effort: str = "low") -> None:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import OpenAI

        token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
        self._client = OpenAI(base_url=os.environ["AZURE_OPENAI_ENDPOINT"], api_key=token_provider)
        self.deployment = deployment or os.environ.get("AZURE_OPENAI_DEPLOYMENT_FAST", "fast")
        self.reasoning_effort = reasoning_effort
        self.name = f"azure:{self.deployment}"

    def complete(self, system: str, user: str, schema: type[T], agent: str) -> T:
        response = self._client.chat.completions.parse(
            model=self.deployment,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=schema,
            reasoning_effort=self.reasoning_effort,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError(f"{agent}: model returned no structured output ({response.choices[0].finish_reason})")
        return parsed


class FakeLLM:
    """Deterministic stand-in: each agent registers a function that builds its answer from the prompt."""

    name = "fake"

    def __init__(self, handlers: dict[str, Callable[[str], BaseModel]] | None = None) -> None:
        self.handlers = handlers or {}

    def complete(self, system: str, user: str, schema: type[T], agent: str) -> T:
        if agent not in self.handlers:
            raise KeyError(f"FakeLLM has no handler for agent '{agent}'")
        return schema.model_validate(self.handlers[agent](user).model_dump())


class CachedLLM:
    """Read-through cache keyed by (model, agent, prompts, schema). 'replay' never calls the model."""

    def __init__(self, inner: LLMClient | None, mode: str = "readwrite", cache_dir: Path = CACHE_DIR) -> None:
        self.inner = inner
        self.mode = mode
        self.cache_dir = cache_dir
        self.name = f"cached:{inner.name if inner else 'none'}"
        self.hits = 0
        self.misses = 0

    def _key(self, system: str, user: str, schema: type[BaseModel], agent: str) -> Path:
        model = self.inner.name if self.inner else "any"
        digest = hashlib.sha256("\x1f".join([model, agent, schema.__name__, system, user]).encode()).hexdigest()[:24]
        return self.cache_dir / agent / f"{digest}.json"

    def complete(self, system: str, user: str, schema: type[T], agent: str) -> T:
        path = self._key(system, user, schema, agent)
        if self.mode != "off" and path.exists():
            self.hits += 1
            return schema.model_validate_json(path.read_text())
        if self.mode == "replay" or self.inner is None:
            raise LookupError(f"no cached answer for {agent} ({path.name}); run once with LLM_CACHE=readwrite")
        self.misses += 1
        result = self.inner.complete(system, user, schema, agent)
        if self.mode != "off":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
        return result


def llm_from_env(fake: FakeLLM | None = None) -> LLMClient:
    provider = os.environ.get("LLM_PROVIDER", "fake")
    mode = os.environ.get("LLM_CACHE", "readwrite")
    inner: LLMClient = AzureLLM() if provider == "azure" else (fake or FakeLLM())
    return inner if mode == "off" else CachedLLM(inner, mode)
