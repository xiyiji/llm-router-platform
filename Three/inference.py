"""Providers and the inference engine. Provider failures trigger fallback.

External providers make real API calls when their key env var is set
(OpenAI-compatible chat completions for openai/deepseek, the messages API for
anthropic). Successful non-fallback results go through an LRU+TTL response
cache; the `cached` flag in responses is real.
"""

import os
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import httpx

from schema import (
    InferenceResult,
    ModelConfig,
    QueryRequest,
    RouterConfig,
    RoutingDecision,
)

CACHE_MAX_ENTRIES = 256
CACHE_TTL_SECONDS = 600


class ProviderUnavailableError(Exception):
    """Raised when a provider cannot serve a request; triggers fallback."""


class BaseProvider(ABC):
    name: str

    @abstractmethod
    def availability(self) -> Tuple[bool, Optional[str]]:
        """Return (available, unavailable_reason)."""

    def generate(self, request: QueryRequest, model_name: str, config: ModelConfig) -> str:
        available, reason = self.availability()
        if not available:
            raise ProviderUnavailableError(reason or f"{self.name} unavailable")
        return self._generate_text(request, model_name, config)

    @abstractmethod
    def _generate_text(self, request: QueryRequest, model_name: str, config: ModelConfig) -> str:
        """Produce the response text."""


class LocalProvider(BaseProvider):
    name = "local"

    def availability(self) -> Tuple[bool, Optional[str]]:
        return True, None

    def _generate_text(self, request: QueryRequest, model_name: str, config: ModelConfig) -> str:
        return f"Echo from {model_name}: {request.query[:200]}"


class _ExternalKeyedProvider(BaseProvider):
    """External provider gated on an API key env var."""

    key_env: str

    def availability(self) -> Tuple[bool, Optional[str]]:
        if not os.environ.get(self.key_env):
            return False, f"{self.key_env} not configured"
        return True, None

    def _generate_text(self, request: QueryRequest, model_name: str, config: ModelConfig) -> str:
        return self._call_api(request, config)

    def _call_api(self, request: QueryRequest, config: ModelConfig) -> str:
        raise NotImplementedError


class OpenAICompatibleProvider(_ExternalKeyedProvider):
    base_url: str

    def _call_api(self, request: QueryRequest, config: ModelConfig) -> str:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ[self.key_env]}"},
            json={
                "model": config.provider_model,
                "messages": [{"role": "user", "content": request.query}],
                "max_tokens": min(request.max_tokens or 512, config.max_tokens),
                "temperature": request.temperature,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"
    key_env = "OPENAI_API_KEY"
    base_url = "https://api.openai.com/v1"


class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"
    key_env = "DEEPSEEK_API_KEY"
    base_url = "https://api.deepseek.com"


class AnthropicProvider(_ExternalKeyedProvider):
    name = "anthropic"
    key_env = "ANTHROPIC_API_KEY"

    def _call_api(self, request: QueryRequest, config: ModelConfig) -> str:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": os.environ[self.key_env],
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": config.provider_model,
                "max_tokens": min(request.max_tokens or 512, config.max_tokens),
                "messages": [{"role": "user", "content": request.query}],
            },
            timeout=30,
        )
        response.raise_for_status()
        blocks = response.json().get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


class ResponseCache:
    """LRU + TTL cache for successful inference results."""

    def __init__(self, max_entries: int = CACHE_MAX_ENTRIES, ttl_seconds: int = CACHE_TTL_SECONDS):
        self._store: "OrderedDict[str, Tuple[float, dict]]" = OrderedDict()
        self._lock = threading.Lock()
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            stored_at, payload = entry
            if time.time() - stored_at > self.ttl_seconds:
                del self._store[key]
                self.misses += 1
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return dict(payload)

    def put(self, key: str, payload: dict) -> None:
        with self._lock:
            self._store[key] = (time.time(), payload)
            self._store.move_to_end(key)
            while len(self._store) > self.max_entries:
                self._store.popitem(last=False)

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 4) if total else 0.0,
            }


class AllModelsFailedError(Exception):
    def __init__(self, attempted_models: List[str], provider_errors: Dict[str, str]):
        self.attempted_models = attempted_models
        self.provider_errors = provider_errors
        super().__init__(f"All models failed: {attempted_models}")


class InferenceEngine:
    """Executes routed queries, walking the fallback chain on provider failure."""

    def __init__(self, config: RouterConfig):
        self._config = config
        self._providers: Dict[str, BaseProvider] = {
            p.name: p
            for p in (LocalProvider(), OpenAIProvider(), AnthropicProvider(), DeepSeekProvider())
        }
        self._cache = ResponseCache()

    def cache_stats(self) -> dict:
        return self._cache.stats()

    @staticmethod
    def _cache_key(request: QueryRequest, model_name: str) -> str:
        return f"{model_name}|{request.user_tier}|{request.max_tokens}|{request.query}"

    def run(self, request: QueryRequest, decision: RoutingDecision) -> InferenceResult:
        cache_key = self._cache_key(request, decision.selected_model)
        hit = self._cache.get(cache_key)
        if hit is not None:
            hit.update({"cached": True, "latency_ms": 0})
            return InferenceResult.model_validate(hit)

        chain = [decision.selected_model] + decision.fallback_models
        attempted: List[str] = []
        errors: Dict[str, str] = {}

        for model_name in chain:
            model_config = self._config.models[model_name]
            provider = self._providers.get(model_config.provider)
            attempted.append(model_name)

            if provider is None:
                errors[model_name] = f"Unknown provider '{model_config.provider}'"
                continue

            start = time.time()
            try:
                response_text = provider.generate(request, model_name, model_config)
            except ProviderUnavailableError as exc:
                errors[model_name] = str(exc)
                continue
            except Exception as exc:  # unexpected provider failure -> keep falling back
                errors[model_name] = f"{type(exc).__name__}: {exc}"
                continue

            latency_ms = int((time.time() - start) * 1000)
            input_tokens = len(request.query.split())
            output_tokens = len(response_text.split())
            cost_usd = round(
                input_tokens / 1000 * model_config.cost_per_1k_input
                + output_tokens / 1000 * model_config.cost_per_1k_output,
                8,
            )
            fallback_used = model_name != decision.selected_model
            result = InferenceResult(
                response_text=response_text,
                model_name=model_name,
                provider=model_config.provider,
                token_count_input=input_tokens,
                token_count_output=output_tokens,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                cached=False,
                fallback_used=fallback_used,
                fallback_reason=(
                    f"{decision.selected_model} failed: {errors[decision.selected_model]}"
                    if fallback_used and decision.selected_model in errors
                    else None
                ),
                attempted_models=attempted,
                provider_errors=errors,
            )
            if not fallback_used:
                self._cache.put(cache_key, result.model_dump())
            return result

        raise AllModelsFailedError(attempted, errors)

    def healthy(self) -> bool:
        return any(p.availability()[0] for p in self._providers.values())

    def details(self) -> dict:
        providers: Dict[str, dict] = {}
        for name, provider in self._providers.items():
            available, reason = provider.availability()
            models = [
                model_name
                for model_name, cfg in self._config.models.items()
                if cfg.provider == name
            ]
            entry: dict = {"healthy": available, "models": models}
            if not available:
                entry["reason"] = reason
            providers[name] = entry
        return {"providers": providers}
