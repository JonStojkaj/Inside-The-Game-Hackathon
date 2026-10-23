"""Microsoft Agent Framework runtime for our agents (AGENT_RUNTIME=framework, the default when installed).

Every agent (Analyst, Critic, Producer, Narrator, Recap) is an `agent_framework.Agent` backed by Azure OpenAI
(chat completions on the `fast` deployment, keyless via DefaultAzureCredential) with a pydantic schema as
structured output. The explain team's orchestration is a framework Workflow (app.agents.workflow).

Same guarantees as the plain-SDK path (app.agents.llm):
  * LLM_PROVIDER=fake   a deterministic FakeChatClient answers from the FakeLLM handlers (no network), and it
                        even calls the tools the agent is offered, so tests exercise the real tool loop
  * LLM_CACHE           every *model call* is cached by a chat middleware (readwrite | replay | off); tools are
                        our own deterministic code and simply run again on replay
  * FrameworkLLM implements LLMClient, so the production team runs unchanged on framework agents.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from pathlib import Path
from typing import Any, TypeVar

from agent_framework import (
    Agent,
    BaseChatClient,
    ChatContext,
    ChatMiddleware,
    ChatMiddlewareLayer,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    Message,
)
from pydantic import BaseModel

from app.agents.llm import CACHE_DIR, FakeLLM, cache_path, request_timeout

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")

# the Analyst may call tools; bound the loop (our run_experiment tool has its own probe budget on top)
FUNCTION_LOOP = {"max_iterations": 4, "max_function_calls": 8}


# --- one background event loop: sync callers (pipeline scripts, tests) can use the async framework ----------

class _LoopThread:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, name="agent-framework-loop", daemon=True).start()

    def run(self, coro: Coroutine[Any, Any, R]) -> R:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()


_LOOP: _LoopThread | None = None
_LOOP_LOCK = threading.Lock()


def run_sync(coro: Coroutine[Any, Any, R]) -> R:
    """Run a coroutine on the shared framework loop (works from sync code and from inside other loops)."""
    global _LOOP
    with _LOOP_LOCK:
        if _LOOP is None:
            _LOOP = _LoopThread()
    return _LOOP.run(coro)


# --- cache: a chat middleware around every model call ------------------------------------------------------

def _canon_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    keep = ("type", "text", "call_id", "name", "arguments", "result")
    out = []
    for m in messages:
        contents = [{k: v for k, v in c.to_dict().items() if k in keep} for c in m.contents]
        out.append({"role": str(m.role), "contents": contents})
    return out


class LLMCacheMiddleware(ChatMiddleware):
    """Read-through cache around every model call. 'replay' never calls the model (a miss raises, like CachedLLM).

    Single-turn calls (Critic, Producer, Narrator, Recap: instructions + one user prompt, no tools) use exactly
    CachedLLM's key and file format, so both runtimes share and replay the same answers. Tool-loop calls (the
    Analyst) are keyed by the whole conversation incl. tool results and stored under <cache>/af/."""

    def __init__(self, model: str, agent: str, mode: str, cache_dir: Path, stats: dict[str, int]) -> None:
        self.model, self.agent, self.mode, self.cache_dir, self.stats = model, agent, mode, cache_dir, stats

    @staticmethod
    def _schema(context: ChatContext) -> type[BaseModel] | None:
        fmt = (context.options or {}).get("response_format")
        return fmt if isinstance(fmt, type) and issubclass(fmt, BaseModel) else None

    def _single_turn(self, context: ChatContext) -> Path | None:
        schema, options, msgs = self._schema(context), context.options or {}, context.messages
        if schema is None or options.get("tools") or len(msgs) != 1 or str(msgs[0].role) != "user":
            return None
        if any(c.type != "text" for c in msgs[0].contents):
            return None
        return cache_path(self.cache_dir, self.model, self.agent, schema, str(options.get("instructions") or ""), msgs[0].text)

    def _conversation(self, context: ChatContext) -> Path:
        schema = self._schema(context)
        key = json.dumps({
            "model": self.model, "agent": self.agent,
            "schema": json.dumps(schema.model_json_schema(), sort_keys=True) if schema else "",
            "instructions": (context.options or {}).get("instructions"),
            "messages": _canon_messages(context.messages),
        }, sort_keys=True, ensure_ascii=False, default=str)
        return self.cache_dir / "af" / self.agent / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.json"

    async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        if context.stream:
            raise RuntimeError("streaming is not used by our agents")
        single = self._single_turn(context)
        path = single or self._conversation(context)
        if self.mode != "off" and path.exists():
            self.stats["hits"] += 1
            if single:  # the parsed answer, as CachedLLM stores it
                context.result = ChatResponse(messages=[Message(role="assistant", contents=[path.read_text()])], finish_reason="stop")
            else:
                context.result = ChatResponse.from_dict(json.loads(path.read_text()))
            return
        if self.mode == "replay":
            raise LookupError(f"no cached answer for {self.agent} ({path.name}); run once with LLM_CACHE=readwrite")
        self.stats["misses"] += 1
        await call_next()
        if self.mode == "off" or not isinstance(context.result, ChatResponse):
            return
        if single:
            schema = self._schema(context)
            assert schema is not None
            try:
                parsed = schema.model_validate_json(context.result.text)
            except ValueError:
                return  # not cacheable; the caller reports the bad output
            text = json.dumps(parsed.model_dump(), indent=2, ensure_ascii=False)
        else:
            text = json.dumps({"type": "chat_response", "messages": [m.to_dict() for m in context.result.messages],
                               "finish_reason": context.result.finish_reason}, indent=1, ensure_ascii=False, default=str)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


# --- fake chat client: deterministic, offline, but drives the real framework tool loop ----------------------

def _first_user_text(messages: Sequence[Message]) -> str:
    return next((m.text for m in messages if str(m.role) == "user"), "")


class FakeChatClient(FunctionInvocationLayer[Any], ChatMiddlewareLayer[Any], BaseChatClient[Any]):
    """Answers with handler(user prompt) as JSON. If the agent is offered tools and has not used them yet, it
    first calls get_match_stats and run_experiment for every experiment_id its answer is going to name."""

    OTEL_PROVIDER_NAME = "fake"

    def __init__(self, handler: Callable[[str], BaseModel] | None, agent: str = "") -> None:
        super().__init__()
        self.handler = handler
        self.agent = agent

    async def _inner_get_response(self, *, messages: Sequence[Message], stream: bool, options: Any, **kwargs: Any) -> ChatResponse:
        if stream:
            raise RuntimeError("FakeChatClient does not stream")
        if self.handler is None:
            raise KeyError(f"FakeLLM has no handler for agent '{self.agent}'")
        answer = self.handler(_first_user_text(messages))
        tools = {getattr(t, "name", "") for t in (options or {}).get("tools") or []}
        used_tools = any(c.type == "function_result" for m in messages for c in m.contents)
        if tools and not used_tools:
            calls: list[tuple[str, dict[str, Any]]] = [("get_match_stats", {})] if "get_match_stats" in tools else []
            if "run_experiment" in tools:
                calls += [("run_experiment", {"experiment_id": h.experiment_id}) for h in getattr(answer, "hypotheses", [])]
            if calls:
                contents = [Content.from_function_call(call_id=f"fake-{i}", name=n, arguments=a) for i, (n, a) in enumerate(calls)]
                return ChatResponse(messages=[Message(role="assistant", contents=contents)], finish_reason="tool_calls")
        return ChatResponse(messages=[Message(role="assistant", contents=[answer.model_dump_json()])], finish_reason="stop")


# --- the runtime -----------------------------------------------------------------------------------------

def _azure_client() -> Any:
    """Azure OpenAI v1 surface (https://<resource>.openai.azure.com/openai/v1), keyless: an Entra ID token from
    DefaultAzureCredential (az login locally, managed identity in Azure) is the bearer key, like AzureLLM."""
    from agent_framework.openai import OpenAIChatCompletionClient
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from openai import AsyncOpenAI

    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    if not endpoint.endswith("/openai/v1"):
        endpoint += "/openai/v1"
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_FAST", "fast")
    sync_token = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")

    async def token() -> str:  # the sync credential caches and refreshes; keep its I/O off the event loop
        return await asyncio.to_thread(sync_token)

    # an explicit client: the framework's own Azure settings loader rejects AZURE_OPENAI_ENDPOINT + base_url together
    return OpenAIChatCompletionClient(model=deployment, async_client=AsyncOpenAI(base_url=endpoint, api_key=token, timeout=request_timeout()))


class FrameworkLLM:
    """Runs each named agent as a Microsoft Agent Framework Agent. Implements LLMClient.complete()."""

    def __init__(self, provider: str = "fake", cache_mode: str = "off", fake: FakeLLM | None = None,
                 cache_dir: Path = CACHE_DIR, reasoning_effort: str = "low") -> None:
        self.provider = provider
        self.cache_mode = cache_mode
        self.cache_dir = cache_dir
        self.fake = fake or FakeLLM()
        self.reasoning_effort = reasoning_effort
        self.stats = {"hits": 0, "misses": 0}
        self._azure: Any = None
        self._agents: dict[tuple[str, str], Agent[Any]] = {}
        if provider == "azure":
            self._azure = _azure_client()
            self.model = f"azure:{self._azure.model}"
        else:
            self.model = "fake"
        self.name = f"agent-framework:{self.model}"

    @property
    def hits(self) -> int:
        return self.stats["hits"]

    @property
    def misses(self) -> int:
        return self.stats["misses"]

    def _client(self, agent: str) -> Any:
        if self._azure is not None:
            client = self._azure
        else:
            client = FakeChatClient(self.fake.handlers.get(agent), agent)
        client.function_invocation_configuration.update(FUNCTION_LOOP)
        return client

    def agent(self, name: str, instructions: str) -> Agent[Any]:
        """One framework Agent per (role, instructions); the model call is wrapped by the cache middleware."""
        key = (name, instructions)
        if key not in self._agents:
            options: dict[str, Any] = {"reasoning_effort": self.reasoning_effort} if self._azure is not None else {}
            self._agents[key] = Agent(
                client=self._client(name), name=name, instructions=instructions, default_options=options,  # type: ignore[arg-type]
                middleware=[LLMCacheMiddleware(self.model, name, self.cache_mode, self.cache_dir, self.stats)],
            )
        return self._agents[key]

    async def arun(self, agent: str, instructions: str, prompt: str, schema: type[T], tools: Sequence[Any] | None = None) -> T:
        response = await self.agent(agent, instructions).run(prompt, tools=list(tools) if tools else None,
                                                             options={"response_format": schema})
        value = response.value
        if isinstance(value, schema):
            return value
        if value is None:
            try:
                return schema.model_validate_json(response.text)
            except ValueError as e:
                raise RuntimeError(f"{agent}: model returned no structured output") from e
        return schema.model_validate(value if isinstance(value, dict) else value.model_dump())

    def complete(self, system: str, user: str, schema: type[T], agent: str) -> T:
        return run_sync(self.arun(agent, system, user, schema))


def framework_llm_from_env(fake: FakeLLM | None = None) -> FrameworkLLM:
    return FrameworkLLM(provider=os.environ.get("LLM_PROVIDER", "fake"), cache_mode=os.environ.get("LLM_CACHE", "readwrite"),
                        fake=fake)
