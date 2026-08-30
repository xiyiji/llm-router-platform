"""HTTP endpoints: request/response orchestration only."""

import uuid

from fastapi import APIRouter

from app.core.config import get_config
from app.schemas import (
    HealthResponse,
    InferenceResponse,
    QueryRequest,
    RoutingInfo,
    ServiceHealth,
    TokenUsage,
)
from app.services.inference import InferenceEngine
from app.services.router import QueryRouter

router = APIRouter()

_config = get_config()
_query_router = QueryRouter(_config.router)
_engine = InferenceEngine(_config.router)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    router_healthy = _query_router.healthy()
    inference_healthy = _engine.healthy()
    status = "healthy" if router_healthy and inference_healthy else "degraded"
    return HealthResponse(
        status=status,
        services={
            "router": ServiceHealth(healthy=router_healthy),
            "inference": ServiceHealth(healthy=inference_healthy),
        },
    )


@router.post("/route", response_model=InferenceResponse)
def route_query(request: QueryRequest) -> InferenceResponse:
    decision = _query_router.route(request)
    result = _engine.run(request, decision)

    return InferenceResponse(
        query_id=str(uuid.uuid4()),
        response=result.response_text,
        model_name=result.model_name,
        tokens=TokenUsage(
            input=result.token_count_input,
            output=result.token_count_output,
            total=result.token_count_input + result.token_count_output,
        ),
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        cached=result.cached,
        routing=RoutingInfo(
            reason=decision.routing_reason,
            confidence=decision.confidence,
            query_type=decision.query_type,
        ),
    )
