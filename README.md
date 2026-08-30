# LLM Router & Execution Platform

Course project, built in three phases. Each phase folder is a standalone app
with its own venv, config and tests.

- `One/` - phase 1, minimal FastAPI service that routes a query to a mock model (port 8081)
- `Two/` - phase 2, smarter routing with multiple providers and fallback (port 8082)
- `Three/` - phase 3, adds analytics endpoints and a Streamlit dashboard (API on 8080, UI on 8501)

The original specs are under `project2/project2/` (Phase 1.md to Phase 3.md, in Chinese).

To run a phase:

```bash
cd Three
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python main.py
```

Tests: `./venv/bin/python -m pytest -q`

See DEPLOY.md for putting phase 3 online.
