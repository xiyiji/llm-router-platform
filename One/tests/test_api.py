"""Smoke tests for the Phase 1 API."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["services"]["router"]["healthy"] is True
    assert body["services"]["inference"]["healthy"] is True


def test_route_returns_200_with_required_fields():
    response = client.post(
        "/route",
        json={"query": "What is the capital of France?", "user_id": "u1", "user_tier": "free"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "model_name" in body
    assert "response" in body
    assert body["tokens"]["total"] == body["tokens"]["input"] + body["tokens"]["output"]
    assert body["cached"] is False
    assert "reason" in body["routing"]


def test_route_rejects_empty_query():
    response = client.post("/route", json={"query": "", "user_id": "u1"})
    assert response.status_code == 422


def test_route_rejects_invalid_user_tier():
    response = client.post(
        "/route", json={"query": "hello", "user_id": "u1", "user_tier": "vip"}
    )
    assert response.status_code == 422


def test_coding_query_routes_to_coding_model():
    response = client.post(
        "/route",
        json={"query": "Write a Python function to reverse a list", "user_id": "u1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model_name"] == "coding-pro"
    assert body["routing"]["query_type"] == "coding"


def test_long_query_routes_to_long_context_model():
    response = client.post(
        "/route", json={"query": "history of aviation " * 100, "user_id": "u1"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model_name"] == "long-context"


def test_general_query_routes_to_default_model():
    response = client.post(
        "/route", json={"query": "What is the capital of France?", "user_id": "u1"}
    )
    assert response.status_code == 200
    assert response.json()["model_name"] == "general-small"
