# Phase 3

Adds monitoring on top of the phase 2 router: the backend records every
`/route` call and exposes aggregate endpoints, and a Streamlit dashboard
shows them.

## Run

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# terminal 1, backend on :8080
./venv/bin/python main.py

# terminal 2, dashboard on :8501
./venv/bin/python -m streamlit run dashboard.py
```

## Endpoints

- `POST /route` - same as phase 2, now also records metrics
- `GET /health` - service and provider health
- `GET /status` - mode, uptime, adapters, SLO config
- `GET /analytics` - totals plus per-model / per-tier / per-type breakdowns
- `GET /quality/dashboard` - success rate, error rate, avg/P95 latency, hotspots, alerts
- `POST /feedback` - stores a rating for a query
- `GET /logs` - recent log lines

## Dashboard

Seven pages: Overview, Models, Performance, Users, Costs, Alerts, Logs
(plus a feedback form on the Logs page). All numbers come from the endpoints
above. If the backend is down the pages say so instead of showing anything.

To see it move: fire a few `POST /route` calls and refresh.

Tests: `./venv/bin/python -m pytest -q`
