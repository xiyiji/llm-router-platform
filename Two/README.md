# Phase 2

Second version of the router. Same `/route` interface as phase 1, but the
routing actually makes decisions now:

- queries get classified (general / coding / analysis / reasoning) and
  token-counted
- routing rules live in config.yaml as boolean expressions, e.g.
  `user_tier in ['premium', 'enterprise']`. They are parsed with an AST
  whitelist so a broken or malicious rule gets skipped instead of executed
- candidates are filtered by tier, capability, context size and cost limit,
  then scored (success rate, cost, latency, priority)
- three provider types: local (echo), openai and anthropic. The external two
  are only "available" when their API key env var is set, and currently
  return placeholder text instead of calling the real API
- if a provider fails, the engine walks the fallback chain and the response
  reports attempted_models / provider_errors instead of returning a 500

## Run

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python main.py
```

Docs at http://localhost:8082/docs

Useful test: send a premium query without OPENAI_API_KEY set. The router
picks gpt-4o-mini, the provider reports the missing key, and the request
falls back to local-general with `fallback_used: true` in the response.

Tests: `./venv/bin/python -m pytest -q`
