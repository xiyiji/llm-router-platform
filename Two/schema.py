"""Data contracts for LLM Router Phase 2."""

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
# Configuration models
# ---------------------------------------------------------------------------

class ApiConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8082


class ModelConfig(BaseModel):
    provider: str
    provider_model: str
    max_tokens: int
    cost_per_1k_input: float
    cost_per_1k_output: float
    priority: int
    capabilities: List[str] = Field(default_factory=list)
    supported_tiers: List[str] = Field(default_factory=lambda: ["free", "premium", "enterprise"])
    fallback_model: Optional[str] = None
    api_key_env: Optional[str] = None
    avg_latency_ms: int = 100
    success_rate: float = Field(default=0.99, ge=0.0, le=1.0)


class RoutingRuleConfig(BaseModel):
    name: str
    condition: str
    candidates: List[str]
    fallback: Optional[str] = None
    reason: str = ""


class RouterConfig(BaseModel):
    default_model: str
    strategy: str = "intelligent"
    models: Dict[str, ModelConfig]
    routing_rules: List[RoutingRuleConfig] = Field(default_factory=list)
    tier_cost_limits: Dict[str, float] = Field(default_factory=dict)


class AppConfig(BaseModel):
    api: ApiConfig
    router: RouterConfig


# ---------------------------------------------------------------------------
# Routing models
# ---------------------------------------------------------------------------

class RoutingDecision(BaseModel):
    selected_model: str
    provider: str
    routing_reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    query_type: str = "general"
    token_count: int = 0
    classification_confidence: float = 0.0
    estimated_cost: float = 0.0
    matched_rule: Optional[str] = None
    fallback_models: List[str] = Field(default_factory=list)


class RoutingInfo(BaseModel):
    reason: str
    confidence: float
    query_type: str
    token_count: int
    classification_confidence: float
    estimated_cost: float
    matched_rule: Optional[str] = None
    fallback_models: List[str] = Field(default_factory=list)
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    attempted_models: List[str] = Field(default_factory=list)
    provider_errors: Dict[str, str] = Field(default_factory=dict)


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
    provider: str
    token_count_input: int
    token_count_output: int
    latency_ms: int
    cost_usd: float
    cached: bool = False
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    attempted_models: List[str] = Field(default_factory=list)
    provider_errors: Dict[str, str] = Field(default_factory=dict)


class InferenceResponse(BaseModel):
    query_id: str
    response: str
    model_name: str
    provider: str
    tokens: TokenUsage
    cost_usd: float
    latency_ms: int
    cached: bool
    routing: RoutingInfo
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Health models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    services: Dict[str, dict]
