"""
Store configuration loader.
Reads YAML files from config/stores/ and returns typed StoreConfig objects.
Store configs are auto-generated when a store suggestion is approved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class StoreNiche:
    primary: str
    secondary: list[str] = field(default_factory=list)
    target_audience: str = ""
    subreddits: list[str] = field(default_factory=list)


@dataclass
class AdapterConfig:
    llm_primary: str = "ollama"
    llm_fallback: list[str] = field(default_factory=lambda: ["gemini"])
    image_gen_primary: str = "ideogram"
    image_gen_fallback: list[str] = field(default_factory=lambda: ["dalle", "pillow"])
    pod_primary: str = "printify"
    pod_fallback: list[str] = field(default_factory=lambda: ["printful"])
    upload_primary: str = "export_folder"
    upload_fallback: list[str] = field(default_factory=list)


@dataclass
class PricingStrategy:
    strategy: str = "penetration"          # "penetration" | "premium" | "competitive"
    apparel_base_multiplier: float = 2.5   # pod_cost × multiplier = listing price
    digital_fixed_price: float = 3.99
    wall_art_base_multiplier: float = 3.0
    round_to_cent: float = 0.99            # e.g. 24.99 not 25.00


@dataclass
class BrandingConfig:
    style_keywords: list[str] = field(default_factory=list)  # injected into every image gen prompt
    color_palette: list[str] = field(default_factory=list)   # hex codes
    font_style: str = "sans-serif"         # "serif" | "sans-serif" | "handwritten"
    mood_keywords: list[str] = field(default_factory=list)   # e.g. ["cozy", "minimal"]


@dataclass
class StoreConfig:
    store_slug: str
    display_name: str
    etsy_shop_id: str = ""
    niche: StoreNiche = field(default_factory=lambda: StoreNiche(primary=""))
    adapters: AdapterConfig = field(default_factory=AdapterConfig)
    pricing: PricingStrategy = field(default_factory=PricingStrategy)
    branding: BrandingConfig = field(default_factory=BrandingConfig)
    product_types: list[str] = field(default_factory=lambda: ["digital_download"])
    airtable_store_record_id: str = ""
    listing_count_target: int = 50
    active: bool = True
    created_at: str = ""

    @property
    def all_niche_terms(self) -> list[str]:
        return [self.niche.primary] + self.niche.secondary

    @classmethod
    def from_yaml(cls, path: Path) -> "StoreConfig":
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))

        niche_raw = data.get("niche", {})
        niche = StoreNiche(
            primary=niche_raw.get("primary", ""),
            secondary=niche_raw.get("secondary", []),
            target_audience=niche_raw.get("target_audience", ""),
            subreddits=niche_raw.get("subreddits", []),
        )

        adapters_raw = data.get("adapters", {})
        llm_raw = adapters_raw.get("llm", {})
        ig_raw = adapters_raw.get("image_gen", {})
        pod_raw = adapters_raw.get("pod", {})
        upload_raw = adapters_raw.get("upload", {})
        adapters = AdapterConfig(
            llm_primary=llm_raw.get("primary", "ollama"),
            llm_fallback=llm_raw.get("fallback", ["gemini"]),
            image_gen_primary=ig_raw.get("primary", "ideogram"),
            image_gen_fallback=ig_raw.get("fallback", ["dalle", "pillow"]),
            pod_primary=pod_raw.get("primary", "printify"),
            pod_fallback=pod_raw.get("fallback", ["printful"]),
            upload_primary=upload_raw.get("primary", "export_folder"),
            upload_fallback=upload_raw.get("fallback", []),
        )

        pricing_raw = data.get("pricing", {})
        pricing = PricingStrategy(
            strategy=pricing_raw.get("strategy", "penetration"),
            apparel_base_multiplier=pricing_raw.get("apparel_base_multiplier", 2.5),
            digital_fixed_price=pricing_raw.get("digital_fixed_price", 3.99),
            wall_art_base_multiplier=pricing_raw.get("wall_art_base_multiplier", 3.0),
            round_to_cent=pricing_raw.get("round_to_cent", 0.99),
        )

        branding_raw = data.get("branding", {})
        branding = BrandingConfig(
            style_keywords=branding_raw.get("style_keywords", []),
            color_palette=branding_raw.get("color_palette", []),
            font_style=branding_raw.get("font_style", "sans-serif"),
            mood_keywords=branding_raw.get("mood_keywords", []),
        )

        return cls(
            store_slug=data.get("store_slug", path.stem),
            display_name=data.get("display_name", ""),
            etsy_shop_id=data.get("etsy_shop_id", ""),
            niche=niche,
            adapters=adapters,
            pricing=pricing,
            branding=branding,
            product_types=data.get("product_types", ["digital_download"]),
            airtable_store_record_id=data.get("airtable_store_record_id", ""),
            listing_count_target=data.get("listing_count_target", 50),
            active=data.get("active", True),
            created_at=data.get("created_at", ""),
        )

    @classmethod
    def from_suggestion(cls, suggestion: dict, store_slug: str) -> "StoreConfig":
        """Auto-generate StoreConfig from an approved store suggestion."""
        from datetime import datetime, timezone
        niche_focus = suggestion.get("niche_focus", "")
        return cls(
            store_slug=store_slug,
            display_name=suggestion.get("store_name", store_slug.replace("-", " ").title()),
            niche=StoreNiche(
                primary=niche_focus,
                target_audience=suggestion.get("target_buyer", ""),
            ),
            branding=BrandingConfig(
                mood_keywords=suggestion.get("brand_voice", "").split(", "),
            ),
            product_types=suggestion.get("product_mix", ["digital_download"]),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_yaml(self) -> str:
        data = {
            "store_slug": self.store_slug,
            "display_name": self.display_name,
            "etsy_shop_id": self.etsy_shop_id,
            "active": self.active,
            "created_at": self.created_at,
            "listing_count_target": self.listing_count_target,
            "airtable_store_record_id": self.airtable_store_record_id,
            "niche": {
                "primary": self.niche.primary,
                "secondary": self.niche.secondary,
                "target_audience": self.niche.target_audience,
                "subreddits": self.niche.subreddits,
            },
            "adapters": {
                "llm": {"primary": self.adapters.llm_primary, "fallback": self.adapters.llm_fallback},
                "image_gen": {"primary": self.adapters.image_gen_primary, "fallback": self.adapters.image_gen_fallback},
                "pod": {"primary": self.adapters.pod_primary, "fallback": self.adapters.pod_fallback},
                "upload": {"primary": self.adapters.upload_primary, "fallback": self.adapters.upload_fallback},
            },
            "pricing": {
                "strategy": self.pricing.strategy,
                "apparel_base_multiplier": self.pricing.apparel_base_multiplier,
                "digital_fixed_price": self.pricing.digital_fixed_price,
                "wall_art_base_multiplier": self.pricing.wall_art_base_multiplier,
                "round_to_cent": self.pricing.round_to_cent,
            },
            "branding": {
                "style_keywords": self.branding.style_keywords,
                "color_palette": self.branding.color_palette,
                "font_style": self.branding.font_style,
                "mood_keywords": self.branding.mood_keywords,
            },
            "product_types": self.product_types,
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True)

    def save(self, config_dir: Path | None = None) -> Path:
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "config" / "stores"
        config_dir.mkdir(parents=True, exist_ok=True)
        path = config_dir / f"{self.store_slug}.yaml"
        path.write_text(self.to_yaml(), encoding="utf-8")
        return path


def load_store(slug: str, config_dir: Path | None = None) -> StoreConfig:
    if config_dir is None:
        config_dir = Path(__file__).parent.parent / "config" / "stores"
    path = config_dir / f"{slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No store config found: {path}")
    return StoreConfig.from_yaml(path)


def list_stores(config_dir: Path | None = None) -> list[StoreConfig]:
    if config_dir is None:
        config_dir = Path(__file__).parent.parent / "config" / "stores"
    configs = []
    for f in sorted(config_dir.glob("*.yaml")):
        if f.stem == "example":
            continue
        try:
            configs.append(StoreConfig.from_yaml(f))
        except Exception:
            pass
    return configs
