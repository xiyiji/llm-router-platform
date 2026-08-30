# LLM Router — Phase 2

Upgrades the Phase 1 skeleton into a router that *decides*: request classification,
configuration-driven rules, multi-provider inference, and automatic fallback.

## Quick start

```bash
python3 -m venv venv
./venv/bin/python -m pip install -U pip
./venv/bin/python -m pip install -r requirements.txt
./venv/bin/python main.py
```

Docs: <http://localhost:8082/docs>

## What's new vs. Phase 1

- **Classification**: queries are typed as `general` / `coding` / `analysis` / `reasoning`,
  with a token-count estimate.
- **Rule system**: `config.yaml` holds routing rules with Python-style boolean
  conditions (`query_type == 'coding'`, `user_tier in ['premium', 'enterprise']`).
  Conditions are evaluated through an AST whitelist — broken or malicious rules are
  skipped, never executed.
- **Candidate filtering + scoring**: tier support, capability match, max_tokens, and
  tier cost limits filter the pool; survivors are scored on success rate, cost,
  priority, latency, and context fit.
- **Multi-provider**: `local`, `openai`, and `anthropic` providers behind one
  `BaseProvider` interface. External providers are gated on their API-key env vars
  and return simulated responses in this phase — the `_generate_text` seam is where
  a real SDK call plugs in later.
- **Fallback**: when a provider is unavailable, the engine walks the fallback chain
  (model `fallback_model` links → rule fallback → default model) and reports
  `fallback_used`, `attempted_models`, and `provider_errors` instead of returning 500.

## Try it

```bash
# free user, general question -> local-general
curl -sS http://localhost:8082/route -H 'Content-Type: application/json' \
  -d '{"query": "hello, what is a cache hit rate?", "user_id": "u1", "user_tier": "free"}' | python3 -m json.tool

# coding question -> hits coding_rule -> local-coding
curl -sS http://localhost:8082/route -H 'Content-Type: application/json' \
  -d '{"query": "write a python function to parse json", "user_id": "u2", "user_tier": "free"}' | python3 -m json.tool

# premium user -> external model selected; without API keys it falls back to local
curl -sS http://localhost:8082/route -H 'Content-Type: application/json' \
  -d '{"query": "analyze tradeoffs of caching vs compression", "user_id": "u3", "user_tier": "premium"}' | python3 -m json.tool
```

## Tests

```bash
./venv/bin/python -m pytest -q
```

Covers smoke tests, rule matching, tier-based selection, fallback without API keys,
and rule-expression safety (broken/dangerous rules are skipped, not executed).
