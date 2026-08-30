# LLM Router & Execution Platform — Phase 1

Minimal viable LLM routing system: `API -> Router -> Inference` with a mock provider.

## Quick start

```bash
python3 -m venv venv
./venv/bin/python -m pip install -U pip
./venv/bin/python -m pip install -r requirements.txt
./venv/bin/python main.py
```

Then open the interactive API docs at <http://localhost:8081/docs>.

## Endpoints

- `GET /health` — service health snapshot (router + inference)
- `POST /route` — route a query to a model and run mock inference

Example:

```bash
curl -sS http://localhost:8081/route \
  -H 'Content-Type: application/json' \
  -d '{"query": "Write a Python function to reverse a list", "user_id": "u1", "user_tier": "free"}' | python3 -m json.tool
```

## Routing strategy (Phase 1, rule-based)

1. Query longer than 1000 characters → `long-context`
2. Query contains coding keywords (`code`, `function`, `class`, `bug`, `python`, …) → `coding-pro`
3. Otherwise → `general-small` (default from `config.yaml`)

## Project layout

```text
One/
├── app/
│   ├── api/routes.py        # HTTP request/response orchestration
│   ├── core/config.py       # config.yaml loading
│   ├── services/router.py   # model selection
│   ├── services/inference.py# mock provider + inference engine
│   ├── main.py              # FastAPI app + run()
│   └── schemas.py           # request/response/config data contracts
├── docs/student_phase1_guide.md
├── tests/test_api.py
├── config.yaml
├── main.py                  # root entry point
└── requirements.txt
```

## Tests

```bash
./venv/bin/python -m pytest -q
```
