"""Data contracts for the LLM Router & Execution Platform (Phase 1)."""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    user_id: str = "anonymous"
    user_tier: Literal["free", "premium", "enterprise"] = "free"
    max_tokens: Optional[int] = Field(default=None, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value


# ---------------------------------------------------------------------------
# Routing models
# ---------------------------------------------------------------------------

class RoutingDecision(BaseModel):
    selected_model: str
    routing_reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    query_type: str = "general"


class RoutingInfo(BaseModel):
    reason: str
    confidence: float
    query_type: str


# ---------------------------------------------------------------------------
# Inference models
# ---------------------------------------------------------------------------

class TokenUsage(BaseModel):
    input: int
    output: int
    total: int


class InferenceResult(BaseModel):
    response_text: str
    model_name: str
    token_count_input: int
    token_count_output: int
    latency_ms: int
    cost_usd: float
    cached: bool = False


class InferenceResponse(BaseModel):
    query_id: str
    response: str
    model_name: str
    tokens: TokenUsage
    cost_usd: float
    latency_ms: int
    cached: bool
    routing: RoutingInfo


# ---------------------------------------------------------------------------
# Health models
# ---------------------------------------------------------------------------

class ServiceHealth(BaseModel):
    healthy: bool


class HealthResponse(BaseModel):
    status: str
    services: Dict[str, ServiceHealth]


# ---------------------------------------------------------------------------
# Configuration models
# ---------------------------------------------------------------------------

class ApiConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8081


class ModelConfig(BaseModel):
    provider: str
    max_tokens: int
    cost_per_1k_input: float
    cost_per_1k_output: float
    priority: int
    capabilities: List[str] = Field(default_factory=list)


class RouterConfig(BaseModel):
    default_model: str
    models: Dict[str, ModelConfig]


class AppConfig(BaseModel):
    api: ApiConfig
    router: RouterConfig
