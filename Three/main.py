"""FastAPI app for the phase 3 router, plus the monitoring endpoints."""

import uuid

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from config_loader import load_config
from inference import AllModelsFailedError, InferenceEngine
from metrics import MetricsStore
from router import QueryRouter
from schema import (
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    InferenceResponse,
    QueryRequest,
    RoutingInfo,
    TokenUsage,
)

app = FastAPI(
    title="LLM Router Phase 3",
    description="Routing API with analytics, quality monitoring, and feedback.",
    version="0.3.0",
)

_config = load_config()
_router = QueryRouter(_config.router)
_engine = InferenceEngine(_config.router)
_metrics = MetricsStore()
_metrics.log("info", "service started")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> str:
    return """<!doctype html><html><head><meta charset="utf-8">
<title>LLM Router</title>
<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:60px auto;padding:0 20px;line-height:1.7;color:#222}
a{color:#0b6e6d}li{margin:6px 0}</style></head><body>
<h1>LLM Router</h1>
<p>This service picks the best AI model for each question (by cost, capability
and user tier) and falls back automatically when a model is unavailable.</p>
<ul>
<li><a href="/docs">Try the API</a> (interactive docs; use POST /route)</li>
<li><a href="/health">Health</a> &middot; <a href="/analytics">Analytics</a> &middot; <a href="/status">Status</a></li>
<li>Source: <a href="https://github.com/xiyiji/llm-router-platform">github.com/xiyiji/llm-router-platform</a></li>
</ul>
<p>Sister project: <b>Delivery Exception Handler</b>, an AI service for failed
package deliveries: <a href="https://github.com/xiyiji/llm-project">github.com/xiyiji/llm-project</a></p>
</body></html>"""


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


@app.get("/status")
def status() -> dict:
    return {
        "service": "llm-router",
        "status": "running",
        "uptime_seconds": _metrics.uptime_seconds(),
        "router_mode": _config.router.strategy,
        "default_model": _config.router.default_model,
        "model_count": len(_config.router.models),
        "quality": {
            "enabled": True,
            "slo": {
                "error_rate_target": _metrics.slo_error_rate,
                "p95_latency_target_ms": _metrics.slo_p95_ms,
            },
        },
        "adapters": _engine.details()["providers"],
        "cache": _engine.cache_stats(),
        "optimization": {"enabled": False},
    }


@app.get("/analytics")
def analytics() -> dict:
    return _metrics.analytics()


@app.get("/quality/dashboard")
def quality_dashboard() -> dict:
    return _metrics.quality_dashboard()


@app.post("/feedback", response_model=FeedbackResponse)
def feedback(request: FeedbackRequest) -> FeedbackResponse:
    count = _metrics.record_feedback(request.model_dump())
    _metrics.log("info", f"feedback received for {request.query_id}: rating {request.rating}")
    return FeedbackResponse(status="ok", feedback_count=count)


@app.post("/route", response_model=InferenceResponse)
def route_query(request: QueryRequest) -> InferenceResponse:
    decision = _router.route(request)
    query_id = str(uuid.uuid4())

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
        routing.fallback_used = True
        routing.fallback_reason = "All models in the fallback chain failed."
        routing.attempted_models = exc.attempted_models
        routing.provider_errors = exc.provider_errors
        _metrics.record_request(
            query_id=query_id, model=decision.selected_model, provider=decision.provider,
            user_id=request.user_id, user_tier=request.user_tier,
            query_type=decision.query_type, tokens_total=0, cost_usd=0.0,
            latency_ms=0, success=False, fallback_used=True, cached=False,
        )
        _metrics.log("error", f"all models failed for {query_id}: {exc.provider_errors}")
        return InferenceResponse(
            query_id=query_id, response="", model_name=decision.selected_model,
            provider=decision.provider, tokens=TokenUsage(input=0, output=0, total=0),
            cost_usd=0.0, latency_ms=0, cached=False, routing=routing,
            error="All providers failed; see routing.provider_errors for details.",
        )

    routing.fallback_used = result.fallback_used
    routing.fallback_reason = result.fallback_reason
    routing.attempted_models = result.attempted_models
    routing.provider_errors = result.provider_errors

    _metrics.record_request(
        query_id=query_id, model=result.model_name, provider=result.provider,
        user_id=request.user_id, user_tier=request.user_tier,
        query_type=decision.query_type,
        tokens_total=result.token_count_input + result.token_count_output,
        cost_usd=result.cost_usd, latency_ms=result.latency_ms,
        success=True, fallback_used=result.fallback_used, cached=result.cached,
    )
    _metrics.log(
        "warning" if result.fallback_used else "info",
        f"{query_id} -> {result.model_name} ({result.provider})"
        + (f", fallback: {result.fallback_reason}" if result.fallback_used else ""),
    )

    return InferenceResponse(
        query_id=query_id,
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


@app.get("/logs")
def logs(limit: int = 100) -> dict:
    return {"logs": _metrics.recent_logs(limit)}


def run() -> None:
    config = load_config()
    uvicorn.run(app, host=config.api.host, port=config.api.port)


if __name__ == "__main__":
    run()
