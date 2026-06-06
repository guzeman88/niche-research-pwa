"""Settings router — read/update configuration."""
from __future__ import annotations

from fastapi import APIRouter
from models.schemas import SettingsUpdate
from config import load_settings, reload_settings, get_setting, CONFIG_DIR
from pipeline.guidelines import all_categories, save as save_guidelines

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings():
    """Get all current settings."""
    return {
        "settings": load_settings(),
        "guidelines": all_categories(),
    }


@router.put("")
def update_settings(req: SettingsUpdate):
    """Update settings and/or guidelines."""
    import yaml

    if req.settings is not None:
        path = CONFIG_DIR / "settings.yaml"
        path.write_text(
            yaml.dump(req.settings, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
        reload_settings()

    if req.guidelines is not None:
        save_guidelines({"categories": req.guidelines})

    return {"status": "saved"}


@router.get("/adapters")
def adapter_status():
    """Check which adapters are configured and healthy."""
    results = {}

    # LLM adapters
    for name in ("ollama", "gemini", "claude"):
        try:
            from adapters.registry import get_llm_adapter
            adapter = get_llm_adapter(name)
            results[f"llm_{name}"] = {
                "available": True,
                "healthy": adapter.health_check(),
            }
        except Exception as e:
            results[f"llm_{name}"] = {"available": False, "error": str(e)}

    # Research adapters
    research_adapters = {
        "etsy_autocomplete": "EtsyAutocompleteAdapter",
        "google_trends": "GoogleTrendsAdapter",
        "reddit_etsy": "RedditEtsyAdapter",
    }
    for key, cls_name in research_adapters.items():
        try:
            if key == "etsy_autocomplete":
                from adapters.research.etsy_autocomplete import EtsyAutocompleteAdapter
                a = EtsyAutocompleteAdapter()
            elif key == "google_trends":
                from adapters.research.google_trends import GoogleTrendsAdapter
                a = GoogleTrendsAdapter()
            elif key == "reddit_etsy":
                from adapters.research.reddit_etsy import RedditEtsyAdapter
                a = RedditEtsyAdapter()
            else:
                continue
            results[key] = {"available": True, "healthy": a.is_configured()}
        except Exception as e:
            results[key] = {"available": False, "error": str(e)}

    return results
