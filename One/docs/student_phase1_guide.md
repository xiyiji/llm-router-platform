# Phase 1 notes

How a request flows:

1. `app/api/routes.py` parses the body into QueryRequest. Validation:
   query can't be empty, user_tier must be free/premium/enterprise.
2. `app/services/router.py` picks a model. Long query goes to long-context,
   coding keywords go to coding-pro, everything else gets the default model
   from config.yaml.
3. `app/services/inference.py` runs the mock provider (it just echoes the
   query back). Tokens are estimated by splitting on whitespace, cost comes
   from the per-1k prices in the config.
4. The handler assembles the final JSON (query_id, response, tokens, cost,
   latency, routing info) and returns it.

The provider is mocked on purpose. This phase is about getting the structure
and the API contract right; real provider calls come later, and the
MockProvider class is where they would plug in.

Checklist before submitting:

- /docs opens
- GET /health returns 200
- POST /route returns stable fields
- empty query returns 422
- bad user_tier returns 422
- a coding query and a general query route to different models
- pytest passes
