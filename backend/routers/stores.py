"""Stores router - list and create store configs."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/stores", tags=["stores"])


class StoreCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    niche: str = Field(min_length=2, max_length=160)
    niche_secondary: list[str] = Field(default_factory=list)
    target_audience: str = ""
    product_types: list[str] = Field(default_factory=list)
    brand_voice: str = ""
    aesthetic: str = ""
    pricing_strategy: str = "competitive"
    listing_target: int = Field(default=50, ge=1, le=1000)


def _store_response(store):
    return {
        "slug": store.store_slug,
        "name": store.display_name,
        "niche": store.niche.primary if store.niche else "",
        "niche_secondary": store.niche.secondary if store.niche else [],
        "target_audience": store.niche.target_audience if store.niche else "",
        "product_types": store.product_types,
        "active": store.active,
        "created_at": store.created_at,
        "listing_target": store.listing_count_target,
        "brand_voice": ", ".join(store.branding.mood_keywords) if store.branding and store.branding.mood_keywords else "",
        "aesthetic": ", ".join(store.branding.style_keywords) if store.branding and store.branding.style_keywords else "",
        "pricing_strategy": store.pricing.strategy if store.pricing else "competitive",
    }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:60].strip("-") or "store"


def _split_terms(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


@router.get("")
def list_stores():
    """List all active store configs with their stats."""
    try:
        from pipeline.store_config import list_stores as _list

        return [_store_response(store) for store in _list()]
    except Exception:
        return []


@router.post("", status_code=201)
def create_store(req: StoreCreateRequest):
    """Create a store config from a generated store idea."""
    try:
        from pipeline.store_config import (
            BrandingConfig,
            PricingStrategy,
            StoreConfig,
            StoreNiche,
            list_stores as _list,
        )

        existing_slugs = {store.store_slug for store in _list()}
        base_slug = _slugify(req.name)
        slug = base_slug
        suffix = 2
        while slug in existing_slugs:
            slug = f"{base_slug[:56]}-{suffix}"
            suffix += 1

        products = [item.strip() for item in req.product_types if item.strip()]
        if not products:
            products = ["digital_download"]

        store = StoreConfig(
            store_slug=slug,
            display_name=req.name.strip(),
            active=True,
            created_at=datetime.now(timezone.utc).isoformat(),
            listing_count_target=req.listing_target,
            niche=StoreNiche(
                primary=req.niche.strip(),
                secondary=[item.strip() for item in req.niche_secondary if item.strip()][:12],
                target_audience=req.target_audience.strip(),
            ),
            branding=BrandingConfig(
                style_keywords=_split_terms(req.aesthetic),
                mood_keywords=_split_terms(req.brand_voice),
            ),
            pricing=PricingStrategy(strategy=req.pricing_strategy),
            product_types=products[:12],
        )
        store.save()
        return _store_response(store)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not create store: {exc}") from exc
