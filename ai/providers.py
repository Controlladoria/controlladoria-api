"""
Advisor Provider Layer — streaming chat completions with multi-provider failover.

Three adapters (Gemini, Amazon Nova via Bedrock, OpenAI) behind one interface,
fronted by a manager that rotates keys through the shared `KeyPool` and falls
through to the next provider when one is exhausted.

Concurrency note: the Gemini and Bedrock SDKs are synchronous. Calling them
directly from an async handler blocks the event loop, which stalls *every*
in-flight request on that worker — fatal for SSE, where connections are held
open for the whole answer. Gemini is driven through its native async client
(`client.aio`); Bedrock has no async client, so every blocking call is pushed
to a thread via `run_in_executor`.
"""

import asyncio
import logging
import os
import threading
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional, Tuple

from ai_key_pool import APIKeyState, KeyPool
from config import settings

logger = logging.getLogger(__name__)

# Roles that adapters understand. "system" is handled out-of-band by providers
# that take a dedicated system parameter (Gemini, Nova).
ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"


def _split_system(messages: List[Dict]) -> Tuple[Optional[str], List[Dict]]:
    """Split leading system messages from the conversation turns."""
    system_parts = [m["content"] for m in messages if m.get("role") == ROLE_SYSTEM]
    turns = [m for m in messages if m.get("role") != ROLE_SYSTEM]
    system = "\n\n".join(p for p in system_parts if p) or None
    return system, turns


def _is_rate_limit(exc: Exception) -> bool:
    """Best-effort rate-limit detection across three different SDKs."""
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "toomanyrequests" in name or "throttl" in name:
        return True
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "quota" in text or "throttl" in text


# ─── ADAPTERS ──────────────────────────────────────────────────────────────────


class ProviderAdapter(ABC):
    """One AI provider, normalized to an OpenAI-style message list."""

    provider: str = ""
    model: str = ""

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Dict],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        """Yield response text incrementally."""
        raise NotImplementedError

    async def chat(
        self,
        messages: List[Dict],
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Non-streaming convenience wrapper (used for summarization)."""
        chunks = []
        async for chunk in self.chat_stream(messages, max_tokens, temperature):
            chunks.append(chunk)
        return "".join(chunks)


class OpenAIAdapter(ProviderAdapter):
    """OpenAI (and any OpenAI-compatible endpoint). Natively async."""

    provider = "openai"

    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None):
        import openai

        self.model = model
        kwargs = {"api_key": api_key, "timeout": settings.advisor_stream_timeout}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = openai.AsyncOpenAI(**kwargs)

    async def chat_stream(self, messages, max_tokens, temperature):
        # `temperature` is deliberately not forwarded: the gpt-5 family rejects
        # any value other than the default, and `structured_processor` omits it
        # for the same reason. Determinism comes from the prompt instead.
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_completion_tokens=max_tokens,
            stream=True,
            store=False,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None)
            if text:
                yield text


class GeminiAdapter(ProviderAdapter):
    """Google Gemini via google-genai, using its native async client."""

    provider = "gemini"

    def __init__(self, api_key: str, model: str):
        from google import genai

        self.model = model
        self.client = genai.Client(api_key=api_key)

    def _to_contents(self, turns: List[Dict]):
        from google.genai import types as genai_types

        contents = []
        for m in turns:
            # Gemini calls the assistant role "model"
            role = "model" if m.get("role") == ROLE_ASSISTANT else "user"
            contents.append(
                genai_types.Content(
                    role=role,
                    parts=[genai_types.Part.from_text(text=m.get("content") or "")],
                )
            )
        return contents

    async def chat_stream(self, messages, max_tokens, temperature):
        from google.genai import types as genai_types

        system, turns = _split_system(messages)
        config = genai_types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
            system_instruction=system,
        )

        stream = await self.client.aio.models.generate_content_stream(
            model=self.model,
            contents=self._to_contents(turns),
            config=config,
        )
        async for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                yield text


class NovaAdapter(ProviderAdapter):
    """
    Amazon Nova via Bedrock `converse_stream`.

    boto3 has no async client and its EventStream must be iterated
    synchronously, so both the initial call and every `next()` on the stream
    are dispatched to the default thread pool.
    """

    provider = "nova"

    def __init__(self, model: str, region: Optional[str] = None):
        self.model = model
        self.region = region or settings.nova_region
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def _format(self, turns: List[Dict]) -> List[Dict]:
        formatted = []
        for m in turns:
            role = "assistant" if m.get("role") == ROLE_ASSISTANT else "user"
            formatted.append({"role": role, "content": [{"text": m.get("content") or ""}]})
        return formatted

    async def chat_stream(self, messages, max_tokens, temperature):
        loop = asyncio.get_running_loop()
        system, turns = _split_system(messages)

        kwargs = {
            "modelId": self.model,
            "messages": self._format(turns),
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
        }
        if system:
            kwargs["system"] = [{"text": system}]

        def _open_stream():
            return self.client.converse_stream(**kwargs)["stream"]

        stream = await loop.run_in_executor(None, _open_stream)
        iterator = iter(stream)

        _SENTINEL = object()

        def _next_event():
            try:
                return next(iterator)
            except StopIteration:
                return _SENTINEL

        while True:
            event = await loop.run_in_executor(None, _next_event)
            if event is _SENTINEL:
                break
            delta = event.get("contentBlockDelta", {}).get("delta", {})
            text = delta.get("text")
            if text:
                yield text


# ─── MANAGER ───────────────────────────────────────────────────────────────────


class AdvisorProviderManager:
    """
    Picks a provider + key per request and streams the answer, falling through
    to the next provider on failure.

    Failover has one honest limitation: once bytes have been streamed to the
    client, switching providers mid-answer would splice two different responses
    together. So fallback only applies *before* the first chunk. A failure after
    that surfaces as an error event, and the user retries.
    """

    def __init__(self):
        self.key_pool = KeyPool(
            unhealthy_threshold=settings.ai_key_unhealthy_threshold,
            recovery_seconds=settings.ai_key_recovery_seconds,
        )
        self._models = {
            "gemini": settings.advisor_gemini_model or settings.gemini_model,
            "nova": settings.advisor_nova_model or settings.nova_model,
            "openai": settings.advisor_openai_model or settings.openai_model,
        }
        self._adapters: Dict[str, ProviderAdapter] = {}
        self._register_keys()
        self._order = self._build_order()
        logger.info(
            "AdvisorProviderManager ready — provider order: %s",
            " → ".join(self._order) or "(none configured)",
        )

    # -- setup ---------------------------------------------------------------

    @staticmethod
    def _parse_keys(csv_value: str, single_value: str) -> List[str]:
        keys = [k.strip() for k in (csv_value or "").split(",") if k.strip()]
        if not keys and single_value:
            keys = [single_value.strip()]
        return keys

    @staticmethod
    def _has_bedrock_credentials() -> bool:
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            return True
        # Also honour instance/task roles, which expose no static keys
        return bool(
            os.getenv("AWS_ACCESS_KEY_ID")
            or os.getenv("AWS_ROLE_ARN")
            or os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")
        )

    def _register_keys(self) -> None:
        gemini_keys = self._parse_keys(settings.gemini_api_keys, settings.gemini_api_key)
        if gemini_keys:
            self.key_pool.register_keys("gemini", gemini_keys, self._models["gemini"])

        openai_keys = self._parse_keys(settings.openai_api_keys, settings.openai_api_key)
        if openai_keys:
            self.key_pool.register_keys("openai", openai_keys, self._models["openai"])

        if self._has_bedrock_credentials():
            # Nova authenticates with IAM, not an API key — the sentinel keeps it
            # inside the same health-tracking machinery as the others.
            self.key_pool.register_keys("nova", ["iam-credentials"], self._models["nova"])

    def _build_order(self) -> List[str]:
        """Configured providers first, then any others holding credentials."""
        raw = settings.advisor_provider or settings.ai_provider or "gemini"
        preferred = [p.strip().lower() for p in raw.split(",") if p.strip()]

        order = [p for p in preferred if self.key_pool.has_provider(p)]
        if settings.ai_failover_enabled:
            for provider in ("gemini", "nova", "openai"):
                if provider not in order and self.key_pool.has_provider(provider):
                    order.append(provider)
        return order

    @property
    def available(self) -> bool:
        return bool(self._order)

    def _adapter_for(self, provider: str, key_state: APIKeyState) -> ProviderAdapter:
        """Adapters are cached per key so HTTP connection pools are reused."""
        cache_key = f"{provider}:{key_state.key[-8:]}"
        adapter = self._adapters.get(cache_key)
        if adapter is not None:
            return adapter

        model = self._models[provider]
        if provider == "openai":
            adapter = OpenAIAdapter(key_state.key, model)
        elif provider == "gemini":
            adapter = GeminiAdapter(key_state.key, model)
        elif provider == "nova":
            adapter = NovaAdapter(model)
        else:
            raise ValueError(f"Unknown provider: {provider}")

        self._adapters[cache_key] = adapter
        return adapter

    # -- streaming -----------------------------------------------------------

    async def stream(
        self,
        messages: List[Dict],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[Tuple[str, str, str]]:
        """
        Yield `(chunk, provider, model)` until the answer is complete.

        Raises RuntimeError if every provider fails before producing output.
        """
        if not self._order:
            raise RuntimeError("Nenhum provedor de IA configurado.")

        max_tokens = max_tokens or settings.advisor_max_tokens
        temperature = (
            settings.advisor_temperature if temperature is None else temperature
        )

        last_error: Optional[Exception] = None

        for provider in self._order:
            key_state = self.key_pool.get_next_key(provider)
            if key_state is None:
                logger.warning("Advisor: no available keys for %s, skipping", provider)
                continue

            emitted = False
            try:
                adapter = self._adapter_for(provider, key_state)
                stream = adapter.chat_stream(messages, max_tokens, temperature)

                async for chunk in stream:
                    emitted = True
                    yield chunk, provider, adapter.model

                self.key_pool.report_success(key_state)
                return

            except asyncio.CancelledError:
                # Client hung up. Not a provider fault — don't poison the key.
                raise
            except Exception as exc:
                self.key_pool.report_error(key_state, is_rate_limit=_is_rate_limit(exc))
                last_error = exc

                if emitted:
                    # Partial answer already on the wire; a retry elsewhere would
                    # concatenate two different responses. Surface it instead.
                    logger.error(
                        "Advisor: %s failed mid-stream, cannot fail over: %s",
                        provider,
                        exc,
                    )
                    raise RuntimeError("stream_interrupted") from exc

                logger.warning(
                    "Advisor: %s failed before output (%s), trying next provider",
                    provider,
                    exc,
                )
                continue

        raise RuntimeError(
            f"Todos os provedores de IA falharam. Último erro: {last_error}"
        )

    async def complete(
        self,
        messages: List[Dict],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Collect a full non-streamed answer (used for history summarization)."""
        parts = []
        async for chunk, _provider, _model in self.stream(
            messages, max_tokens=max_tokens, temperature=temperature
        ):
            parts.append(chunk)
        return "".join(parts)

    def get_status(self) -> Dict:
        return {
            "available": self.available,
            "provider_order": self._order,
            "models": self._models,
            "keys": self.key_pool.get_stats(),
        }


# Module-level singleton — the key pool's round-robin and health state only make
# sense if every request shares one instance.
_manager: Optional[AdvisorProviderManager] = None
_manager_lock = threading.Lock()


def get_provider_manager() -> AdvisorProviderManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = AdvisorProviderManager()
    return _manager
