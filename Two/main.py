"""FastAPI app for the phase 2 router."""

import uuid

import uvicorn
from fastapi import FastAPI

from config_loader import load_config
from inference import AllModelsFailedError, InferenceEngine
from router import QueryRouter
from schema import (
    HealthResponse,
    InferenceResponse,
    QueryRequest,
    RoutingInfo,
    TokenUsage,
)

app = FastAPI(
    title="LLM Router Phase 2",
    description="Intelligent routing, multi-provider inference, and fallback.",
    version="0.2.0",
)

_config = load_config()
_router = QueryRouter(_config.router)
_engine = InferenceEngine(_config.router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    router_healthy = _router.healthy()
    inference_healthy = _engine.healthy()
    status = "healthy" if router_healthy and inference_healthy else "degraded"
    return HealthResponse(
        status=status,
        services={
            "router": {"healthy": router_healthy, "details": _router.details()},
            "inference": {"healthy": inference_healthy, "details": _engine.details()},
        },
    )


@app.post("/route", response_model=InferenceResponse)
def route_query(request: QueryRequest) -> InferenceResponse:
    decision = _router.route(request)

    routing = RoutingInfo(
        reason=decision.routing_reason,
        confidence=decision.confidence,
        query_type=decision.query_type,
        token_count=decision.token_count,
        classification_confidence=decision.classification_confidence,
        estimated_cost=decision.estimated_cost,
        matched_rule=decision.matched_rule,
        fallback_models=decision.fallback_models,
    )

    try:
        result = _engine.run(request, decision)
    except AllModelsFailedError as exc:
        # Explainable failure instead of a 500: every model in the chain failed.
        routing.fallback_used = True
        routing.fallback_reason = "All models in the fallback chain failed."
        routing.attempted_models = exc.attempted_models
        routing.provider_errors = exc.provider_errors
        return InferenceResponse(
            query_id=str(uuid.uuid4()),
            response="",
            model_name=decision.selected_model,
            provider=decision.provider,
            tokens=TokenUsage(input=0, output=0, total=0),
            cost_usd=0.0,
            latency_ms=0,
            cached=False,
            routing=routing,
            error="All providers failed; see routing.provider_errors for details.",
        )

    routing.fallback_used = result.fallback_used
    routing.fallback_reason = result.fallback_reason
    routing.attempted_models = result.attempted_models
    routing.provider_errors = result.provider_errors

    return InferenceResponse(
        query_id=str(uuid.uuid4()),
        response=result.response_text,
        model_name=result.model_name,
        provider=result.provider,
        tokens=TokenUsage(
            input=result.token_count_input,
            output=result.token_count_output,
            total=result.token_count_input + result.token_count_output,
        ),
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        cached=result.cached,
        routing=routing,
        error=None,
    )


def run() -> None:
    config = load_config()
    uvicorn.run(app, host=config.api.host, port=config.api.port)


if __name__ == "__main__":
    run()
