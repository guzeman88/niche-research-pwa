"""Settings router — read/update configuration."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from security import redact_settings
from models.schemas import SettingsUpdate
from config import load_settings, reload_settings, get_setting, CONFIG_DIR
from pipeline.guidelines import all_categories, save as save_guidelines

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings():
    """Get all current settings."""
    return {
        "settings": redact_settings(load_settings()),
        "guidelines": all_categories(),
    }


@router.put("")
def update_settings(req: SettingsUpdate):
    """Update settings and/or guidelines."""
    import yaml

    if req.settings is not None:
        if redact_settings(req.settings) != req.settings:
            raise HTTPException(400, "Store credentials in environment variables, not settings.")
        if "[configured]" in str(req.settings):
            raise HTTPException(400, "Remove redacted credential fields before saving settings.")
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
    """Report provider readiness without exposing credentials or inventing evidence."""
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

    research_adapters = {
        "google_suggest": {
            "loader": lambda: __import__("adapters.research.google_suggest", fromlist=["GoogleSuggestAdapter"]).GoogleSuggestAdapter(),
            "requires_credentials": False,
            "evidence": ["source phrases"],
        },
        "etsy_autocomplete": {
            "loader": lambda: __import__("adapters.research.etsy_autocomplete", fromlist=["EtsyAutocompleteAdapter"]).EtsyAutocompleteAdapter(),
            "requires_credentials": False,
            "requires_configuration": True,
            "evidence": ["source phrases"],
        },
        "etsy_open_api": {
            "loader": lambda: __import__("adapters.research.etsy_open_api", fromlist=["EtsyOpenAPIAdapter"]).EtsyOpenAPIAdapter(),
            "requires_credentials": True,
            "evidence": ["listing count", "sampled prices", "listing sample"],
        },
        "erank": {
            "loader": lambda: __import__("adapters.research.erank", fromlist=["ERankAdapter"]).ERankAdapter(),
            "requires_credentials": True,
            "integration_mode": "import_or_private_api",
            "status_reason": "No generally available public API is documented; use an export unless eRank grants a private endpoint.",
            "evidence": ["provider search volume", "provider competition", "provider trend"],
        },
        "marmalead": {
            "loader": lambda: __import__("adapters.research.marmalead", fromlist=["MarmaleadAdapter"]).MarmaleadAdapter(),
            "requires_credentials": True,
            "integration_mode": "import_or_private_api",
            "status_reason": "No generally available public API is documented; use an export unless Marmalead grants a private endpoint.",
            "evidence": ["provider search volume", "provider competition", "provider trend"],
        },
        "google_trends": {
            "loader": lambda: __import__("adapters.research.google_trends", fromlist=["GoogleTrendsAdapter"]).GoogleTrendsAdapter(),
            "requires_credentials": False,
            "evidence": ["relative trend interest"],
        },
        "pinterest_trends": {
            "loader": lambda: __import__("adapters.research.pinterest_trends", fromlist=["PinterestTrendsAdapter"]).PinterestTrendsAdapter(),
            "requires_credentials": True,
            "approval_required": True,
            "integration_mode": "approved_api",
            "status_reason": "Requires a Pinterest business app approved for Trends API access.",
            "evidence": ["relative trend interest"],
        },
        "reddit_etsy": {
            "loader": lambda: __import__("adapters.research.reddit_etsy", fromlist=["RedditEtsyAdapter"]).RedditEtsyAdapter(),
            "requires_credentials": True,
            "approval_required": True,
            "integration_mode": "approved_api",
            "status_reason": "Commercial Data API collection requires Reddit approval in addition to credentials.",
            "evidence": ["dated matching posts", "post scores", "comment counts", "source records"],
        },
    }
    for key, definition in research_adapters.items():
        try:
            adapter = definition["loader"]()
            results[key] = {
                "available": True,
                "configured": bool(adapter.is_configured()),
                "requires_credentials": definition["requires_credentials"],
                "requires_configuration": definition.get("requires_configuration", False),
                "approval_required": definition.get("approval_required", False),
                "integration_mode": definition.get("integration_mode", "automatic"),
                "status_reason": definition.get("status_reason"),
                "evidence": definition["evidence"],
            }
        except Exception as e:
            results[key] = {
                "available": False,
                "configured": False,
                "requires_credentials": definition["requires_credentials"],
                "requires_configuration": definition.get("requires_configuration", False),
                "approval_required": definition.get("approval_required", False),
                "integration_mode": definition.get("integration_mode", "automatic"),
                "status_reason": definition.get("status_reason"),
                "evidence": definition["evidence"],
                "error": str(e),
            }

    return results
