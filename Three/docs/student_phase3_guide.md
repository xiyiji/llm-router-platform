# Phase 3 notes

## Data flow

Every POST /route stores one record in MetricsStore (metrics.py, in-memory,
behind a lock): model, provider, tier, query type, tokens, cost, latency,
success, fallback. The read endpoints aggregate on demand:

- /analytics: totals, per-model / per-tier / per-type breakdowns, and a
  30-minute request series
- /quality/dashboard: success and error rate, avg and P95 latency, hotspot
  models, SLO check (error rate <= 5%, P95 <= 2000ms) and derived alerts
- /status: router mode, uptime, provider adapters, SLO config
- /feedback: stores ratings, the count shows up in /quality/dashboard
- /logs: ring buffer with the last ~300 log lines

Everything resets on restart since it's in memory. Good enough for this
phase; a real deployment would persist to a database.

## Dashboard

dashboard.py, one file, page picked with a sidebar radio. Each page fetches
from the endpoints above with a 3s timeout. If a fetch fails the page shows
"backend unreachable" and stops, so there's never made-up data on screen.

## Checking the loop works

1. Start the backend, open the dashboard: everything is at zero.
2. Send some /route calls with different tiers and query types.
3. Refresh: Overview, Models, Performance, Users and Costs all change.
4. Stop the backend and refresh: every page reports it can't reach the API.
