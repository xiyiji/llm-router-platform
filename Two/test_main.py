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


def test_free_user_never_gets_external_models(no_external_keys):
    config = load_config()
    router = QueryRouter(config.router)
    decision = router.route(
        QueryRequest(query="analyze tradeoffs of caching vs compression", user_tier="free")
    )
    assert decision.selected_model in LOCAL_MODELS


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


def test_simulated_external_provider_used_when_key_present(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
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
