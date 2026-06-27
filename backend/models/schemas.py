"""Pydantic models for API request/response schemas."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


# ── Research ────────────────────────────────────────────────────────────────

class ResearchRunRequest(BaseModel):
    keywords: list[str] = Field(..., min_length=1, max_length=20,
                                description="Seed keywords to research")
    store_slug: str = Field(default="__global__", description="Store identifier for reports")
    skip_scraper: bool = Field(default=False, description="Skip Etsy HTML scraper for faster testing")
    adapter_names: list[str] | None = Field(default=None, description="Override which adapters to use")


class ResearchRunResponse(BaseModel):
    run_id: str
    status: str = "started"
    message: str = ""


class ReportListItem(BaseModel):
    report_id: str
    store_slug: str
    seed_keywords: list[str]
    opportunity_score: float
    demand_score: float
    competition_score: float
    margin_score: float
    trend_velocity_score: float
    generated_at: str
    sources_used: list[str]


# ── Keywords ────────────────────────────────────────────────────────────────

class KeywordItem(BaseModel):
    keyword: str
    domain: str
    source: str
    priority: int
    added_at: str
    scanned: bool = False
    last_scanned_at: str | None = None
    opportunity_score: float | None = None
    gap_score: float | None = None
    trajectory: str | None = None
    breakout: bool = False


class DiscoveryRequest(BaseModel):
    seasonal: bool = True
    llm: bool = True
    google_suggest: bool = True
    autocomplete: bool = True
    etsy_trending: bool = True
    llm_count: int = Field(default=30, ge=5, le=100)


class DiscoveryResponse(BaseModel):
    total_added: int
    sources_run: list[str]
    db_stats: dict


# ── Gaps ────────────────────────────────────────────────────────────────────

class GapReportItem(BaseModel):
    keyword: str
    analyzed_at: str
    volume_gap_score: float
    quality_gap_score: float
    tag_gap_score: float
    style_gap_score: float
    price_gap_score: float
    recency_gap_score: float
    buyer_intent_score: float = 0.0
    profit_gap_score: float = 0.0
    composite_gap_score: float
    entry_angle: str
    recommended_price_min: float
    recommended_price_max: float
    listings_analyzed: int
    avg_listing_age_months: float


# ── Scheduler ───────────────────────────────────────────────────────────────

class SchedulerStatus(BaseModel):
    running: bool
    paused: bool
    mode: str
    batch_size: int
    keywords_scanned: int
    new_seeds_found: int
    current_keyword: str | None
    started_at: str | None
    interval_s: float
    errors: list[str]


class SchedulerAction(BaseModel):
    mode: str | None = None
    batch_size: int | None = None


# ── Stats ───────────────────────────────────────────────────────────────────

class StatsResponse(BaseModel):
    total_seeds: int
    scanned: int
    unscanned: int
    total_scans: int
    coverage_pct: float
    avg_opportunity: float
    avg_gap_score: float
    breakout_count: int
    expansion_edges: int
    top_gap_keyword: dict | None
    domains: list[dict]


class HealthResponse(BaseModel):
    db_path: str
    size_mb: float
    oldest_scan: str | None
    newest_scan: str | None
    orphan_seeds: int
    integrity: str
    schema_version: int


# ── Settings ────────────────────────────────────────────────────────────────

class SettingsUpdate(BaseModel):
    settings: dict | None = None
    guidelines: dict | None = None


# ── SSE ─────────────────────────────────────────────────────────────────────

class SSELogEvent(BaseModel):
    level: str = "info"        # "info" | "warn" | "error"
    message: str
    timestamp: str


class SSEProgressEvent(BaseModel):
    stage: str
    keyword: str | None = None
    percent: float = 0.0
    message: str = ""


class SSECompleteEvent(BaseModel):
    report_id: str
    opportunity_score: float = 0.0
