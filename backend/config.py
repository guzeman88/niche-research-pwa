"""
Centralized configuration loader for the Niche Research PWA backend.
Loads settings.yaml, merges environment variables, and provides
consistent path resolution for all modules.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Load .env from project root (niche-research-pwa/)
_ENV_PATH = Path(__file__).parent.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)
else:
    load_dotenv()  # fallback: search parent dirs

# Backend root directory
ROOT = Path(__file__).parent.resolve()

# Workspace for outputs (reports, database, logs)
WORKSPACE = ROOT / "workspace"
WORKSPACE.mkdir(parents=True, exist_ok=True)

# Config directory
CONFIG_DIR = ROOT / "config"

# Settings YAML cache
_settings_cache: dict | None = None


def load_settings() -> dict:
    """Load and cache settings.yaml, resolving ${ENV_VAR} placeholders."""
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache

    path = CONFIG_DIR / "settings.yaml"
    if not path.exists():
        _settings_cache = {}
        return _settings_cache

    raw = path.read_text(encoding="utf-8")

    # Resolve ${VAR} placeholders
    import re
    def _resolve(match):
        var = match.group(1)
        return os.getenv(var, "")

    resolved = re.sub(r'\$\{(\w+)\}', _resolve, raw)
    _settings_cache = yaml.safe_load(resolved) or {}
    return _settings_cache


def get_setting(*keys: str, default=None) -> Any:
    """Deep-get a setting by key path. e.g. get_setting('niche_scoring', 'demand_weight')."""
    settings = load_settings()
    node = settings
    for k in keys:
        if isinstance(node, dict):
            node = node.get(k)
        else:
            return default
    return node if node is not None else default


def reload_settings() -> None:
    """Force reload settings.yaml from disk."""
    global _settings_cache
    _settings_cache = None
