"""Smoke tests and Phase 2 core-behavior tests."""

import pytest
from fastapi.testclient import TestClient

from config_loader import load_config
from main import app
from router import QueryRouter, evaluate_rule
from schema import QueryRequest

client = TestClient(app)

LOCAL_MODELS = {"local-general", "local-coding"}
EXTERNAL_MODELS = {"gpt-4o-mini", "claude-sonnet"}


@pytest.fixture
def no_external_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


# -- smoke tests ------------------------------------------------------------

def test_health_returns_200_with_provider_details():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["services"]["router"]["healthy"] is True
    providers = body["services"]["inference"]["details"]["providers"]
    assert {"local", "openai", "anthropic"} <= set(providers)
    assert providers["local"]["healthy"] is True


def test_route_returns_200_with_required_fields(no_external_keys):
    response = client.post(
        "/route",
        json={"query": "hello, what is a cache hit rate?", "user_id": "u1", "user_tier": "free"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "model_name" in body
    assert "response" in body
    assert "provider" in body
    assert body["error"] is None
    routing = body["routing"]
    for field in (
        "reason", "confidence", "query_type", "token_count",
        "classification_confidence", "estimated_cost", "fallback_models",
    ):
        assert field in routing


def test_route_rejects_empty_query():
    assert client.post("/route", json={"query": "", "user_id": "u1"}).status_code == 422


def test_route_rejects_invalid_user_tier():
    response = client.post(
        "/route", json={"query": "hello", "user_id": "u1", "user_tier": "vip"}
    )
    assert response.status_code == 422


# -- routing behavior -------------------------------------------------------

def test_coding_query_hits_coding_rule(no_external_keys):
    response = client.post(
        "/route",
        json={"query": "write a python function to parse json", "user_id": "u2", "user_tier": "free"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["routing"]["matched_rule"] == "coding_rule"
    assert body["routing"]["query_type"] == "coding"
    assert body["model_name"] == "local-coding"


def test_premium_user_selects_higher_priority_model():
    config = load_config()
    router = QueryRouter(config.router)
    decision = router.route(
        QueryRequest(
            query="analyze tradeoffs of caching vs compression",
            user_id="u3",
            user_tier="premium",
        )
    )
    assert decision.matched_rule == "premium_rule"
    assert decision.selected_model in EXTERNAL_MODELS
    local_max_priority = max(
        config.router.models[m].priority for m in LOCAL_MODELS
    )
    assert config.router.models[decision.selected_model].priority > local_max_priority


def test_free_user_never_gets_premium_providers(no_external_keys):
    config = load_config()
    router = QueryRouter(config.router)
    decision = router.route(
        QueryRequest(query="analyze tradeoffs of caching vs compression", user_tier="free")
    )
    # deepseek-chat is cheap enough for the free tier; gpt/claude are not
    assert decision.selected_model in LOCAL_MODELS | {"deepseek-chat"}
    assert decision.selected_model not in EXTERNAL_MODELS


# -- fallback behavior ------------------------------------------------------

def test_missing_keys_trigger_fallback_not_500(no_external_keys):
    response = client.post(
        "/route",
        json={
            "query": "analyze tradeoffs of caching vs compression",
            "user_id": "u3",
            "user_tier": "premium",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["routing"]["fallback_used"] is True
    assert body["model_name"] in LOCAL_MODELS
    assert body["provider"] == "local"
    assert len(body["routing"]["attempted_models"]) >= 2
    assert body["routing"]["provider_errors"]


def test_external_provider_used_when_key_present(monkeypatch):
    from inference import OpenAICompatibleProvider

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        OpenAICompatibleProvider, "_call_api",
        lambda self, request, config: f"stubbed {self.name} answer", raising=True,
    )
    response = client.post(
        "/route",
        json={
            "query": "analyze tradeoffs of caching vs compression",
            "user_id": "u3",
            "user_tier": "premium",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "openai"
    assert body["model_name"] == "gpt-4o-mini"


# -- rule expression safety -------------------------------------------------

def test_valid_rule_expressions_evaluate():
    context = {"query_type": "coding", "token_count": 100, "user_tier": "premium"}
    assert evaluate_rule("query_type == 'coding'", context) is True
    assert evaluate_rule("query_type == 'analysis' and token_count > 80", context) is False
    assert evaluate_rule("user_tier in ['premium', 'enterprise']", context) is True


def test_broken_rule_is_skipped_not_crashing():
    context = {"query_type": "coding", "token_count": 100, "user_tier": "free"}
    assert evaluate_rule("analysis AND token_count > 50000", context) is None
    assert evaluate_rule("query_type ==", context) is None


def test_dangerous_rule_is_rejected():
    context = {"query_type": "coding", "token_count": 1, "user_tier": "free"}
    assert evaluate_rule("__import__('os').system('true')", context) is None
    assert evaluate_rule("(lambda: True)()", context) is None
    assert evaluate_rule("open('/etc/passwd')", context) is None


# -- Phase 3 observability endpoints ----------------------------------------

def test_status_endpoint():
    response = client.get("/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["router_mode"] == "intelligent"
    assert {"local", "openai", "anthropic"} <= set(body["adapters"])


def test_analytics_reflects_route_calls(no_external_keys):
    before = client.get("/analytics").json()["total_requests"]
    client.post("/route", json={"query": "hello dashboard", "user_id": "d1", "user_tier": "free"})
    after = client.get("/analytics").json()
    assert after["total_requests"] == before + 1
    assert after["success_rate"] is not None
    assert "local-general" in after["by_model"] or "local-coding" in after["by_model"]
    assert after["by_tier"]["free"]["requests"] >= 1


def test_quality_dashboard_updates(no_external_keys):
    client.post("/route", json={"query": "quality check", "user_id": "d2", "user_tier": "free"})
    body = client.get("/quality/dashboard").json()
    assert body["requests_total"] >= 1
    assert body["success_rate"] is not None
    assert body["p95_latency_ms"] is not None
    assert body["hotspots"]
    assert body["slo"]["compliant"] is not None


def test_feedback_roundtrip():
    response = client.post(
        "/feedback", json={"query_id": "q-123", "rating": 5, "comment": "great answer"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["feedback_count"] >= 1
    assert client.get("/quality/dashboard").json()["feedback_count"] >= 1


def test_feedback_rejects_bad_rating():
    assert client.post("/feedback", json={"query_id": "q", "rating": 9}).status_code == 422


def test_logs_endpoint_records_requests(no_external_keys):
    client.post("/route", json={"query": "log me", "user_id": "d3", "user_tier": "free"})
    body = client.get("/logs").json()
    assert body["logs"]
    assert any("->" in entry["message"] for entry in body["logs"])


# -- real response cache ----------------------------------------------------

def test_identical_request_hits_cache(no_external_keys):
    payload = {"query": "what is a totally unique cache probe question?", "user_id": "c1", "user_tier": "free"}
    first = client.post("/route", json=payload).json()
    second = client.post("/route", json=payload).json()
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["latency_ms"] == 0
    assert second["response"] == first["response"]


def test_cache_stats_exposed_in_status():
    body = client.get("/status").json()
    assert "cache" in body and "hit_rate" in body["cache"]


def test_deepseek_adapter_listed(no_external_keys):
    providers = client.get("/health").json()["services"]["inference"]["details"]["providers"]
    assert "deepseek" in providers
    assert providers["deepseek"]["healthy"] is False
