# LLM Router — Phase 3

Backend observability endpoints + Streamlit dashboard on live data.

## Run

```bash
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt

# terminal 1 — backend API on :8080
./venv/bin/python main.py

# terminal 2 — dashboard on :8501
./venv/bin/python -m streamlit run dashboard.py
```

## Endpoints

| Endpoint | Serves |
|---|---|
| `POST /route` | routing + inference (records metrics) |
| `GET /health` | service + provider health |
| `GET /status` | system snapshot: mode, uptime, adapters, SLO config |
| `GET /analytics` | totals, by-model / by-tier / by-type aggregates, per-minute series |
| `GET /quality/dashboard` | success rate, error rate, avg/P95 latency, hotspots, SLO, alerts |
| `POST /feedback` | store user feedback |
| `GET /logs` | recent request/system logs |

## Dashboard pages

Overview · Models · Performance · Users · Costs · Alerts · Logs (+ feedback form).
All pages read the backend endpoints above; when the backend is down they show
"backend unreachable" — never fabricated numbers. Call `POST /route` a few times
and refresh to watch every page change.

## Tests

```bash
./venv/bin/python -m pytest -q
```
