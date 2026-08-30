# Phase 2 Guide

## Routing pipeline

`router.py::QueryRouter.route` runs seven steps:

1. **Classify** — keyword evidence types the query (`coding`, `analysis`,
   `reasoning`, default `general`) with a confidence score.
2. **Count tokens** — ~4 characters per token.
3. **Match rules** — the first rule in `config.yaml` whose condition evaluates
   true narrows the candidate pool. Conditions are Python-style boolean
   expressions parsed with `ast` and checked against a node whitelist
   (comparisons, boolean ops, names, constants, lists only). Anything else —
   syntax errors, function calls, imports — makes the rule skip safely.
4. **Filter** — drop candidates that don't support the user tier, lack the
   required capability, have too small a context window, or exceed the tier's
   cost limit. If nothing survives, the capability requirement is relaxed.
5. **Score** — weighted mix of success rate (0.35), relative cost (0.25),
   latency (0.20), priority (0.10), and context fit (0.10).
6. **Build fallback chain** — follow `fallback_model` links from the selected
   model, then the rule's fallback, then the default model.
7. **Return** an explainable `RoutingDecision`.

## Provider layer

`inference.py` defines `BaseProvider` with three implementations:

- `LocalProvider` — always available, deterministic echo.
- `OpenAIProvider` / `AnthropicProvider` — available only when their
  `*_API_KEY` env var is set; currently return clearly-marked simulated text.
  The `_generate_text` method is the single extension point for real API calls.

`InferenceEngine.run` walks `[selected] + fallback_models`, recording every
attempt and error. Success returns a unified `InferenceResult` (with
`fallback_used` / `fallback_reason` when the selected model wasn't the one that
answered). If the whole chain fails, `main.py` returns an explainable JSON
response with a populated `error` field — never a bare 500.

## Demonstrating fallback

Run without `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` and send a premium request:
the router selects an external model, the provider reports "key not configured",
and the engine falls back to `local-general`, all visible in
`routing.attempted_models` and `routing.provider_errors`.
