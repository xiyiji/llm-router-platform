# Deploy

## 1. Backend API — Render (free)

1. Sign in at <https://dashboard.render.com> with GitHub.
2. **New → Blueprint** → select `xiyiji/llm-router-platform` → Apply.
   (`render.yaml` builds `Three/` and starts `uvicorn main:app`.)
3. Copy the service URL, e.g. `https://llm-router-api.onrender.com`.
   Verify: `https://<url>/health` and `https://<url>/docs`.

## 2. Dashboard — Streamlit Community Cloud (free)

1. Sign in at <https://share.streamlit.io> with GitHub.
2. **Create app** → repo `xiyiji/llm-router-platform` → branch `main` →
   main file `Three/dashboard.py`.
3. **Advanced settings → Secrets/Environment**: set
   `ROUTER_API = https://<your-render-url>` (no trailing slash).
4. Deploy. The dashboard URL is public and shareable.

## Notes

- Free tiers sleep when idle; first request takes ~30s to wake.
- Every `git push` to `main` redeploys both services automatically.
- No secrets required: external providers are key-gated simulations.
