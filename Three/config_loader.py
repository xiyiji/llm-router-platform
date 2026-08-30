"""Unified configuration loading for LLM Router Phase 2."""

from functools import lru_cache
from pathlib import Path

import yaml

from schema import AppConfig

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    """Load config.yaml from the project root and validate it as AppConfig."""
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return AppConfig.model_validate(raw)
