# LLM Router & Execution Platform

A three-phase course project building an LLM routing and execution platform.

| Phase | Directory | Status | Focus |
|-------|-----------|--------|-------|
| 1 | [`One/`](One/) | ✅ Done | Minimal `API -> Router -> Inference` pipeline (FastAPI, mock provider, port 8081) |
| 2 | [`Two/`](Two/) | ✅ Done | Intelligent routing, multi-provider abstraction, fallback/degradation (port 8082) |
| 3 | — | Pending | Observability endpoints + Streamlit dashboard |

Specs (in Chinese) live in [`project2/project2/`](project2/project2/) — `Phase 1.md` through `Phase 3.md`.

Each phase directory is self-contained with its own `requirements.txt`, `config.yaml`, and tests:

```bash
cd One
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
./venv/bin/python -m pytest -q
./venv/bin/python main.py
```
