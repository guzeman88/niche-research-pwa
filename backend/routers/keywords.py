"""Keywords router — seed management, discovery, search."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from models.schemas import KeywordItem, DiscoveryRequest, DiscoveryResponse

router = APIRouter(prefix="/api/keywords", tags=["keywords"])


def _ensure_db():
    from pipeline import keyword_database as kdb
    kdb.init_db()
    kdb.load_seeds_from_library()


@router.get("", response_model=list[KeywordItem])
def list_keywords(
    domain: str | None = Query(default=None),
    limit: int = Query(default=2000, le=5000),
):
    """List all seed keywords with scan status."""
    _ensure_db()
    from pipeline import keyword_database as kdb
    rows = kdb.get_all_seeds_with_status(limit=limit)
    results = []
    for r in rows:
        if domain and r.get("domain") != domain:
            continue
        results.append(KeywordItem(
            keyword=r["keyword"],
            domain=r.get("domain", "unknown"),
            source=r.get("source", "library"),
            priority=r.get("priority", 5),
            added_at=r.get("added_at", ""),
            scanned=r.get("scanned_at") is not None,
            last_scanned_at=r.get("scanned_at"),
            opportunity_score=r.get("opportunity_score"),
            gap_score=r.get("gap_score"),
            trajectory=r.get("trajectory"),
            breakout=False,
        ))
    return results[:limit]


@router.get("/search", response_model=list[KeywordItem])
def search_keywords(q: str = Query(..., min_length=2), limit: int = Query(default=100, le=500)):
    """Search keywords by partial match."""
    _ensure_db()
    from pipeline import keyword_database as kdb
    rows = kdb.search_keywords(q, limit=limit)
    return [KeywordItem(
        keyword=r["keyword"],
        domain=r.get("domain", "unknown"),
        source=r.get("source", "library"),
        priority=0,
        added_at=r.get("added_at", ""),
        scanned=r.get("scanned_at") is not None,
        last_scanned_at=r.get("scanned_at"),
        opportunity_score=r.get("opportunity_score"),
        gap_score=r.get("gap_score"),
        trajectory=r.get("trajectory"),
        breakout=False,
    ) for r in rows]


@router.get("/opportunities")
def top_opportunities(domain: str | None = None, limit: int = Query(default=100, le=500)):
    """Get top opportunities ranked by opportunity score."""
    _ensure_db()
    from pipeline import keyword_database as kdb
    return kdb.get_top_opportunities(limit=limit, domain=domain)


@router.get("/breakouts")
def breakouts(limit: int = Query(default=20, le=100)):
    """Get keywords flagged as breakouts (rapidly improving gap scores)."""
    _ensure_db()
    from pipeline import keyword_database as kdb
    keywords = kdb.get_breakouts(limit=limit)
    return [{"keyword": kw, "breakout": True} for kw in keywords]


@router.get("/domains")
def domains():
    """List all keyword domains."""
    _ensure_db()
    from pipeline import keyword_database as kdb
    return kdb.get_domains()


@router.post("/discover", response_model=DiscoveryResponse)
def run_discovery(req: DiscoveryRequest = DiscoveryRequest()):
    """Run seed keyword discovery from multiple sources."""
    _ensure_db()
    from pipeline.stages.keyword_scanner import SeedDiscovery

    disc = SeedDiscovery()
    result = disc.run_all(
        seasonal=req.seasonal,
        llm=req.llm,
        autocomplete=req.autocomplete,
        etsy_trending=req.etsy_trending,
        llm_count=req.llm_count,
    )
    return DiscoveryResponse(**result)


@router.post("/generate-compounds")
def generate_compounds(max_per_pair: int = 20):
    """Generate compound keywords by cross-pollinating domains."""
    _ensure_db()
    from pipeline.stages.keyword_scanner import generate_compound_keywords
    added = generate_compound_keywords(max_per_pair=max_per_pair)
    return {"added": added}


@router.get("/coverage")
def coverage():
    """Get keyword database coverage summary."""
    _ensure_db()
    from pipeline import keyword_database as kdb
    return kdb.get_stats()
