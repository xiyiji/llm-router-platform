# Phase 3 Guide

## Data flow

`POST /route` records every request into `metrics.py::MetricsStore` (in-memory,
thread-safe): model, provider, tier, query type, tokens, cost, latency, success,
fallback. The observability endpoints aggregate that store on demand:

- `/analytics` — totals plus by-model, by-tier, by-query-type breakdowns and a
  30-minute per-minute request series.
- `/quality/dashboard` — success/error rate, avg and P95 latency, hotspot
  models, SLO compliance (error rate ≤ 5%, P95 ≤ 2000 ms), and derived alerts
  (SLO breaches, high fallback ratio).
- `/status` — service snapshot: router mode, uptime, provider adapters, SLO config.
- `/feedback` — stores ratings; count surfaces in `/quality/dashboard`.
- `/logs` — ring buffer of request and system log lines.

## Frontend

`dashboard.py` is a Streamlit app with seven pages, each backed by the real
endpoints (page → endpoint mapping follows the spec). The `require()` helper
stops any page with an explicit "backend unreachable" error when a fetch fails,
so the dashboard never renders fabricated data.

## Verifying the loop

1. Start the backend, open the dashboard — Overview shows zeros.
2. Fire several `POST /route` calls (mixed tiers/queries).
3. Refresh Overview / Models / Performance — request counts, latency, costs,
   hotspots, and tier distribution all change.
4. Stop the backend, refresh — every page reports "backend unreachable".
