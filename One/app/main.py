"""FastAPI application factory and server entry point."""

import uvicorn
from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_config

app = FastAPI(
    title="LLM Router & Execution Platform",
    description="Phase 1: minimal API -> router -> inference pipeline.",
    version="0.1.0",
)
app.include_router(router)


def run() -> None:
    config = get_config()
    uvicorn.run(app, host=config.api.host, port=config.api.port)
