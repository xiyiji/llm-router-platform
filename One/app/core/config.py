"""Configuration loading for the LLM Router & Execution Platform."""

from functools import lru_cache
from pathlib import Path

import yaml

from app.schemas import AppConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Load config.yaml from the project root and validate it as AppConfig."""
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return AppConfig.model_validate(raw)
