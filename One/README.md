# Phase 1

Minimal version of the router. A FastAPI service with a mock provider:
`POST /route` picks a model with simple rules and returns JSON with the
response text, token counts, cost and latency.

## Run

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python main.py
```

Then open http://localhost:8081/docs

Example call:

```bash
curl -sS http://localhost:8081/route \
  -H 'Content-Type: application/json' \
  -d '{"query": "Write a Python function to reverse a list", "user_id": "u1", "user_tier": "free"}'
```

## Routing rules

- query longer than 1000 chars: long-context
- coding keywords in the query (code, function, bug, python, ...): coding-pro
- anything else: general-small (the default from config.yaml)

## Layout

- `app/api/routes.py` - the two endpoints (/health, /route)
- `app/core/config.py` - loads config.yaml
- `app/services/router.py` - model selection
- `app/services/inference.py` - mock provider, token/cost estimates
- `app/schemas.py` - request/response models
- `tests/test_api.py` - smoke tests, run with `./venv/bin/python -m pytest -q`
