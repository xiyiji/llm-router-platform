# LLM Router & Execution Platform

A cost- and capability-aware routing layer for LLM traffic: it takes a user
query, decides which model should serve it, executes the call with automatic
fallback, and exposes the whole decision trail plus live operational metrics.
Built in three phases, each a standalone FastAPI app; phase 3 adds a Streamlit
dashboard on top.

```
             POST /route
                  |
        +---------v---------+
        |  classify query   |  keyword scoring -> coding / analysis /
        |  estimate tokens  |  reasoning / general, ~4 chars per token
        +---------+---------+
                  |
        +---------v---------+
        |  match rules      |  boolean expressions from config.yaml,
        |                   |  parsed through an AST whitelist
        +---------+---------+
                  |
        +---------v---------+
        |  filter + score   |  tier, capability, context window, cost cap;
        |                   |  weighted score picks the winner
        +---------+---------+
                  |
        +---------v---------+     provider dead? walk the fallback chain,
        |  execute          | --> record every attempt and error,
        |                   |     never surface a bare 500
        +---------+---------+
                  |
        +---------v---------+
        |  record metrics   |  feeds /analytics, /quality/dashboard,
        +-------------------+  and the Streamlit UI
```

## Technical highlights

**Sandboxed rule engine.** Routing rules live in `config.yaml` as Python-style
boolean expressions (`query_type == 'coding'`,
`user_tier in ['premium', 'enterprise']`). Instead of raw `eval`, each
condition is parsed with `ast.parse` and every node is checked against a
whitelist (comparisons, `and`/`or`/`not`, names, constants, lists). Function
calls, attribute access and imports are rejected at parse time, and evaluation
runs with empty builtins on the whitelisted tree. A malformed or malicious
rule logs a warning and is skipped; the rest of the rule set keeps working.
There are tests that feed `__import__('os').system(...)` and lambda
expressions into the engine and assert they never execute.

**Multi-factor model selection.** After a rule (or the full model list)
produces candidates, they are filtered on four hard constraints: user tier
allowed, required capability present, context window large enough, estimated
cost under the tier's budget. Survivors are ranked by a weighted score:

    0.35 * success_rate
  + 0.25 * relative_cost      (cheapest candidate = 1.0, others min/cost)
  + 0.20 * latency_score      (1 - avg_latency / 2s)
  + 0.10 * priority
  + 0.10 * context_fit

Cost is scored relative to the candidate set rather than in absolute dollars,
so micro-cost differences between local models still matter while a 24x price
gap between external models is not flattened by a fixed denominator.

**Fallback with full accounting.** Each model config can name a
`fallback_model`; the router follows those links (cycle-safe, depth-capped),
then appends the matched rule's fallback and the global default. The inference
engine walks that chain on provider failure and the response carries the
evidence: `attempted_models`, per-model `provider_errors`, `fallback_used` and
the human-readable reason. A premium request with no `OPENAI_API_KEY` set
returns 200 from the local model with the OpenAI failure documented inline,
which makes provider outages debuggable from the response body alone.

**Provider abstraction.** `local`, `openai` and `anthropic` providers share a
`BaseProvider` interface with a separate availability check (external
providers gate on their API key env var). All of them emit one unified
`InferenceResult`, so the API and routing layers are provider-agnostic. In
phase 3 the external providers (`openai`, `anthropic`, `deepseek`) make real
API calls when their key env var is set; without keys they report unavailable
and requests degrade to the local models, so the service runs free and
leak-proof by default. DeepSeek is cheap enough that the free tier is allowed
to route to it.

**Observability without a database.** Phase 3 records every routed request
into a lock-guarded in-memory store and aggregates on read: per-model /
per-tier / per-query-type breakdowns, cost totals, a 30-minute request
series, P95 latency (nearest-rank), hotspot models, and SLO evaluation
(error rate <= 5%, P95 <= 2000ms) with derived alerts, including a
high-fallback-ratio warning that in practice means "your API keys are
missing". Logs sit in a fixed-size ring buffer. Aggregation is O(n) over a
snapshot taken under the lock, so readers never block writers for long.

**Response caching.** Successful non-fallback inference results go through
an LRU+TTL cache keyed on (model, tier, max_tokens, query); the `cached` flag
and the hit/miss counters on `/status` are real, and temperature-0 requests
make repeats genuine hits.

**A frontend that refuses to lie.** The Streamlit dashboard (Overview,
Models, Performance, Users, Costs, Alerts, Logs) renders only what the
backend returns. Every fetch has a 3s timeout, and any failure stops the
page with an explicit "backend unreachable" error instead of stale or
placeholder numbers.

## Phases

| Phase | Folder | Adds |
|---|---|---|
| 1 | `One/` | Minimal API -> router -> inference pipeline, mock provider, port 8081 |
| 2 | `Two/` | Rule engine, classification, scoring, multi-provider, fallback, port 8082 |
| 3 | `Three/` | Metrics store, /status /analytics /quality/dashboard /feedback /logs, Streamlit UI, ports 8080/8501 |

Original specs (Chinese) are under `project2/project2/`.

## API surface (phase 3)

| Endpoint | Purpose |
|---|---|
| `POST /route` | route + execute a query, returns the full decision trail |
| `GET /health` | router and per-provider health with failure reasons |
| `GET /status` | mode, uptime, adapter snapshot, SLO config |
| `GET /analytics` | totals and per-model / per-tier / per-type aggregates |
| `GET /quality/dashboard` | success/error rate, avg + P95 latency, hotspots, SLO, alerts |
| `POST /feedback` | store a 1-5 rating against a query_id |
| `GET /logs` | recent log lines |

## Run

```bash
cd Three
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python main.py                          # API on :8080
./venv/bin/python -m streamlit run dashboard.py    # UI on :8501
```

Fire a few requests at `POST /route` (see `/docs`) and refresh the dashboard
to watch every page move. Kill the backend and refresh to see the explicit
failure state.

## Testing

37 tests across the three phases (`./venv/bin/python -m pytest -q` in each
folder), covering the contract (validation, stable response shape), behavior
(rule matching, tier-based selection, key-gated provider flips), resilience
(fallback instead of 500s, broken rules skipped) and the phase 3 aggregation
endpoints. The rule-engine security tests are the ones worth reading first.

## Benchmarks

`scripts/load_test.py` against `POST /route` on a single uvicorn worker
(M-series MacBook, rules path, unique queries so the cache does not help):

| concurrency | requests | RPS | P50 | P95 | P99 | errors |
|---|---|---|---|---|---|---|
| 10 | 1000 | 831 | 7 ms | 31 ms | 82 ms | 0 |
| 50 | 2000 | 435 | 69 ms | 317 ms | 495 ms | 0 |

The gap between the two rows is queueing on one worker, not work per request;
scaling out means more workers plus a shared metrics store.

## Known limits

Metrics are in-memory and reset on restart; multi-worker deployments would
need a shared store (Redis/Postgres) behind `MetricsStore`. Real provider
calls exist in phase 3 only (`Two/` keeps the phase 2 stubs as a snapshot)
and need API keys to activate. `/route` trusts the caller's `user_tier`, so
real deployments need authentication in front.

Deployment notes: see `DEPLOY.md` (Render for the API, Streamlit Community
Cloud for the dashboard).
