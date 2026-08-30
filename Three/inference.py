"""Multi-provider inference with fallback for Phase 2.

Providers do not call real external APIs in this phase — the structure and
the fallback flow are the deliverable. Each provider keeps a single seam
(`_generate_text`) where a real API call can be plugged in later without
touching the API or routing layers.
"""

import os
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from schema import (
    InferenceResult,
    ModelConfig,
    QueryRequest,
    RouterConfig,
    RoutingDecision,
)


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
        """Produce the response text. Replace with a real API call later."""


class LocalProvider(BaseProvider):
    name = "local"

    def availability(self) -> Tuple[bool, Optional[str]]:
        return True, None

    def _generate_text(self, request: QueryRequest, model_name: str, config: ModelConfig) -> str:
        return f"Echo from {model_name}: {request.query[:200]}"


class _ExternalKeyedProvider(BaseProvider):
    """External provider gated on an API key env var; simulated call for now."""

    key_env: str

    def availability(self) -> Tuple[bool, Optional[str]]:
        if not os.environ.get(self.key_env):
            return False, f"{self.key_env} not configured"
        return True, None

    def _generate_text(self, request: QueryRequest, model_name: str, config: ModelConfig) -> str:
        # Extension point: replace with a real SDK call to this provider.
        return (
            f"[simulated {self.name}:{config.provider_model}] "
            f"response to: {request.query[:150]}"
        )


class OpenAIProvider(_ExternalKeyedProvider):
    name = "openai"
    key_env = "OPENAI_API_KEY"


class AnthropicProvider(_ExternalKeyedProvider):
    name = "anthropic"
    key_env = "ANTHROPIC_API_KEY"


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
            p.name: p for p in (LocalProvider(), OpenAIProvider(), AnthropicProvider())
        }

    def run(self, request: QueryRequest, decision: RoutingDecision) -> InferenceResult:
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
            return InferenceResult(
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
