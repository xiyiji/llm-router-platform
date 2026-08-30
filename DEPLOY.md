# Deploy

## Backend (Render)

1. Log into dashboard.render.com with GitHub
2. New -> Blueprint -> pick this repo -> Apply. render.yaml builds `Three/`
   and starts uvicorn.
3. Check `https://<service>.onrender.com/docs` once it's up.

## Dashboard (Streamlit Community Cloud)

1. Log into share.streamlit.io with GitHub
2. Create app -> this repo, branch main, main file `Three/dashboard.py`
3. In advanced settings add `ROUTER_API=https://<your-render-url>`
   (no trailing slash)
4. Deploy

Notes: free tiers sleep when idle, so the first request after a while takes
about 30s. Pushing to main redeploys both. No API keys are needed since the
external providers are stubbed.
