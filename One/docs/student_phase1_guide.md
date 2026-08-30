# Phase 1 Guide

## What this phase delivers

A minimal but correctly layered LLM routing service:

- `POST /route` accepts a query, picks a model, runs mock inference, and returns a
  structured JSON response with tokens, cost, latency, and an explainable routing block.
- `GET /health` reports router and inference health.

## How a request flows

1. `app/api/routes.py` parses the body into `QueryRequest` (validation: non-empty
   `query`, `user_tier` limited to `free` / `premium` / `enterprise`).
2. `app/services/router.py` (`QueryRouter`) applies rule-based routing:
   long queries → `long-context`, coding keywords → `coding-pro`, otherwise the
   default model from `config.yaml`.
3. `app/services/inference.py` (`InferenceEngine` + `MockProvider`) produces a
   deterministic echo response and estimates tokens (whitespace split), latency,
   and cost (per-1k-token prices from config).
4. The route handler assembles `InferenceResponse` and returns it.

## Why a mock provider

Phase 1 is about system structure, interface contracts, and module layering.
The mock provider keeps results predictable, explainable, and repeatable, while the
`MockProvider` seam leaves room to plug in real providers (OpenAI, Anthropic, vLLM)
in later phases without rewriting the API or routing layers.

## Verification checklist

- `http://localhost:8081/docs` opens
- `GET /health` returns 200 JSON
- `POST /route` returns stable fields for normal input
- Empty `query` → 422 validation error
- Invalid `user_tier` → 422 validation error
- Coding vs. general queries produce different routing results
- `./venv/bin/python -m pytest -q` passes
