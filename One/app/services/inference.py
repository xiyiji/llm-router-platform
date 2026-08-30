"""Mock inference execution (Phase 1)."""

import time

from app.schemas import (
    InferenceResult,
    QueryRequest,
    RouterConfig,
    RoutingDecision,
)


class MockProvider:
    """Deterministic echo provider used in Phase 1 instead of real LLM calls."""

    def generate(self, query: str, model_name: str) -> str:
        return f"Echo from {model_name}: {query[:200]}"


class InferenceEngine:
    """Executes a routed query against its provider and reports usage metrics."""

    def __init__(self, config: RouterConfig):
        self._config = config
        self._provider = MockProvider()

    def run(self, request: QueryRequest, decision: RoutingDecision) -> InferenceResult:
        model_name = decision.selected_model
        model_config = self._config.models[model_name]

        start = time.time()
        response_text = self._provider.generate(request.query, model_name)
        latency_ms = int((time.time() - start) * 1000)

        input_tokens = len(request.query.split())
        output_tokens = len(response_text.split())
        cost_usd = (
            input_tokens / 1000 * model_config.cost_per_1k_input
            + output_tokens / 1000 * model_config.cost_per_1k_output
        )

        return InferenceResult(
            response_text=response_text,
            model_name=model_name,
            token_count_input=input_tokens,
            token_count_output=output_tokens,
            latency_ms=latency_ms,
            cost_usd=round(cost_usd, 8),
            cached=False,
        )

    def healthy(self) -> bool:
        return self._provider is not None
