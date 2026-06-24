"""Stores router — list store configs with stats."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/stores", tags=["stores"])


@router.get("")
def list_stores():
    """List all active store configs with their stats."""
    try:
        from pipeline.store_config import list_stores as _list
        stores = _list()
        results = []
        for s in stores:
            results.append({
                "slug": s.store_slug,
                "name": s.display_name,
                "niche": s.niche.primary if s.niche else "",
                "niche_secondary": s.niche.secondary if s.niche else [],
                "target_audience": s.niche.target_audience if s.niche else "",
                "product_types": s.product_types,
                "active": s.active,
                "created_at": s.created_at,
                "listing_target": s.listing_count_target,
                "brand_voice": ", ".join(s.branding.mood_keywords) if s.branding and s.branding.mood_keywords else "",
                "aesthetic": ", ".join(s.branding.style_keywords) if s.branding and s.branding.style_keywords else "",
                "pricing_strategy": s.pricing.strategy if s.pricing else "competitive",
            })
        return results
    except Exception:
        return []
