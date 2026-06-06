"""
Product Guidelines loader.
Reads config/product_guidelines.json and exposes principle values to all pipeline stages.

Usage:
    from pipeline.guidelines import get, is_enabled, reload

    max_title_chars = get("seo", "title_max_chars", default=140)
    if is_enabled("pricing", "round_to_cent"):
        ...
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
_GUIDELINES_PATH = ROOT / "config" / "product_guidelines.json"

_cache: dict | None = None


def _load_raw() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    if _GUIDELINES_PATH.exists():
        try:
            _cache = json.loads(_GUIDELINES_PATH.read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
    else:
        _cache = {}
    return _cache


def reload() -> None:
    """Force reload from disk (call after saving from UI)."""
    global _cache
    _cache = None


def get(category: str, principle_id: str, default=None):
    """
    Return the value of an enabled principle.
    Returns `default` if the principle is disabled or not found.
    """
    data = _load_raw()
    cat = data.get("categories", {}).get(category, {})
    for p in cat.get("principles", []):
        if p["id"] == principle_id:
            if not p.get("enabled", True):
                return default
            return p.get("value", default)
    return default


def is_enabled(category: str, principle_id: str) -> bool:
    """Return True if a principle exists and is enabled."""
    data = _load_raw()
    cat = data.get("categories", {}).get(category, {})
    for p in cat.get("principles", []):
        if p["id"] == principle_id:
            return bool(p.get("enabled", True))
    return False


def get_category(category: str) -> dict:
    """Return the full category dict (label, icon, principles list)."""
    return _load_raw().get("categories", {}).get(category, {})


def all_categories() -> dict:
    """Return all categories."""
    return _load_raw().get("categories", {})


def save(data: dict) -> None:
    """Persist updated guidelines data to disk and reload cache."""
    _GUIDELINES_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    reload()
