"""
Persistent SQLite database for keyword research intelligence.

Schema is versioned — migrations run automatically on init_db().
All writes are transactional; WAL mode keeps reads fast during writes.

Public API (backward-compatible):
  init_db()               — create/migrate tables
  load_seeds_from_library() — bulk-import config/seed_keywords.json
  add_seed() / add_seeds_bulk()
  save_scan(keyword, report)
  get_unscanned() / get_stale() / get_next_batch()
  get_top_opportunities() / get_top_gaps()
  get_stats() / get_health()
  search_keywords() / get_all_seeds() / get_domains()
  record_expansion(parent, children, source)
  log_scheduler_run() / update_scheduler_run()
  export_csv(path) / export_json(path)
  backup(backup_dir)
  prune_old_scans(keep_per_keyword)
  rebuild_gap_scores()
"""

import csv
import json
import math
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Paths resolved relative to the backend/ directory
import os as _os
_BACKEND_DIR = Path(_os.environ.get("BACKEND_DIR", Path(__file__).parent.parent.resolve()))
DB_PATH = _BACKEND_DIR / "workspace/_keyword_db/keywords.sqlite"
SEED_PATH = _BACKEND_DIR / "config/seed_keywords.json"
SEED_DB_PATH = _BACKEND_DIR / "seed_data/_keyword_db/keywords.sqlite"
SCHEMA_VERSION = 6


# ── Connection ────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def _db_scan_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        con = sqlite3.connect(path)
        count = con.execute("SELECT COUNT(DISTINCT keyword) FROM scans").fetchone()[0]
        con.close()
        return int(count or 0)
    except Exception:
        return 0


def ensure_seed_snapshot(min_scans: int = 1) -> bool:
    """
    Restore the tracked keyword snapshot when the workspace DB is missing or empty.

    Production hosts can start with an empty writable workspace; without this guard
    profit-ranked endpoints have no scanned keyword intelligence and return [].
    """
    if not SEED_DB_PATH.exists():
        return False
    if _db_scan_count(DB_PATH) >= min_scans:
        return False

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        target = Path(f"{DB_PATH}{suffix}")
        if target.exists():
            target.unlink()
    shutil.copy2(SEED_DB_PATH, DB_PATH)

    seed_state = SEED_DB_PATH.parent / "scheduler_state.json"
    if seed_state.exists():
        shutil.copy2(seed_state, DB_PATH.parent / "scheduler_state.json")
    return True


# ── Schema migrations ─────────────────────────────────────────────────────────

def _get_version(con: sqlite3.Connection) -> int:
    con.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    row = con.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
    return row[0] if row else 0


def _set_version(con: sqlite3.Connection, version: int) -> None:
    con.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (version,))


def _migrate_v1(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS seeds (
            keyword     TEXT PRIMARY KEY,
            domain      TEXT NOT NULL DEFAULT 'unknown',
            source      TEXT NOT NULL DEFAULT 'library',
            added_at    TEXT NOT NULL,
            priority    INTEGER NOT NULL DEFAULT 5
        );

        CREATE TABLE IF NOT EXISTS scans (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword                 TEXT NOT NULL,
            scanned_at              TEXT NOT NULL,
            opportunity_score       REAL,
            demand_score            REAL,
            competition_score       REAL,
            margin_score            REAL,
            trend_score             REAL,
            avg_price_usd           REAL,
            monthly_revenue_usd     REAL,
            competition_quality     REAL,
            listing_count           INTEGER,
            sources_used            TEXT,
            report_path             TEXT,
            peak_months             TEXT,
            keyword_clusters_json   TEXT,
            entry_strategy          TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_scans_keyword     ON scans(keyword);
        CREATE INDEX IF NOT EXISTS idx_scans_scanned_at  ON scans(scanned_at);
        CREATE INDEX IF NOT EXISTS idx_scans_opportunity ON scans(opportunity_score DESC);
    """)


def _migrate_v2(con: sqlite3.Connection) -> None:
    """Add expansion tree, gap scores, and scheduler log tables."""
    con.executescript("""
        CREATE TABLE IF NOT EXISTS expansion_tree (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_keyword  TEXT NOT NULL,
            child_keyword   TEXT NOT NULL,
            source          TEXT NOT NULL,
            depth           INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT NOT NULL,
            UNIQUE(parent_keyword, child_keyword, source)
        );

        CREATE INDEX IF NOT EXISTS idx_exp_parent ON expansion_tree(parent_keyword);
        CREATE INDEX IF NOT EXISTS idx_exp_child  ON expansion_tree(child_keyword);

        CREATE TABLE IF NOT EXISTS gap_scores (
            keyword                 TEXT PRIMARY KEY,
            gap_score               REAL,
            listing_efficiency      REAL,
            score_delta             REAL DEFAULT 0,
            previous_gap_score      REAL,
            trajectory              TEXT DEFAULT 'stable',
            breakout_flag           INTEGER DEFAULT 0,
            last_computed           TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_gap_score ON gap_scores(gap_score DESC);

        CREATE TABLE IF NOT EXISTS scheduler_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at          TEXT NOT NULL,
            completed_at        TEXT,
            keywords_scanned    INTEGER DEFAULT 0,
            new_seeds_found     INTEGER DEFAULT 0,
            mode                TEXT DEFAULT 'continuous',
            status              TEXT DEFAULT 'running',
            error_msg           TEXT
        );
    """)


def _migrate_v3(con: sqlite3.Connection) -> None:
    """Add gap_score and trajectory columns to scans for fast querying."""
    for col, typedef in [
        ("gap_score",           "REAL"),
        ("listing_efficiency",  "REAL"),
        ("score_delta",         "REAL DEFAULT 0"),
        ("trajectory",          "TEXT DEFAULT 'stable'"),
    ]:
        try:
            con.execute(f"ALTER TABLE scans ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass  # column already exists


def _migrate_v4(con: sqlite3.Connection) -> None:
    """Add gap_reports table for full 6-signal gap analysis results."""
    con.executescript("""
        CREATE TABLE IF NOT EXISTS gap_reports (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword                     TEXT NOT NULL,
            analyzed_at                 TEXT NOT NULL,
            volume_gap_score            REAL DEFAULT 0,
            quality_gap_score           REAL DEFAULT 0,
            tag_gap_score               REAL DEFAULT 0,
            style_gap_score             REAL DEFAULT 0,
            price_gap_score             REAL DEFAULT 0,
            recency_gap_score           REAL DEFAULT 0,
            composite_gap_score         REAL DEFAULT 0,
            entry_angle                 TEXT DEFAULT '',
            recommended_price_min       REAL DEFAULT 0,
            recommended_price_max       REAL DEFAULT 0,
            untagged_searches_json      TEXT DEFAULT '[]',
            dominant_competitor_tags_json TEXT DEFAULT '[]',
            recommended_tags_json       TEXT DEFAULT '[]',
            listings_analyzed           INTEGER DEFAULT 0,
            avg_listing_age_months      REAL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_gap_reports_keyword ON gap_reports(keyword);
        CREATE INDEX IF NOT EXISTS idx_gap_reports_composite ON gap_reports(composite_gap_score DESC);
    """)


def _migrate_v5(con: sqlite3.Connection) -> None:
    """Add profit and buyer-intent signals to full gap reports."""
    for col, typedef in [
        ("buyer_intent_score", "REAL DEFAULT 0"),
        ("profit_gap_score", "REAL DEFAULT 0"),
    ]:
        try:
            con.execute(f"ALTER TABLE gap_reports ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass


def _migrate_v6(con: sqlite3.Connection) -> None:
    """Add deeper profitability and market-evidence fields."""
    scan_cols = [
        ("price_min_usd", "REAL DEFAULT 0"),
        ("price_p25_usd", "REAL DEFAULT 0"),
        ("price_median_usd", "REAL DEFAULT 0"),
        ("price_p75_usd", "REAL DEFAULT 0"),
        ("price_max_usd", "REAL DEFAULT 0"),
        ("avg_favorites", "REAL DEFAULT 0"),
        ("max_favorites", "INTEGER DEFAULT 0"),
        ("pct_high_favorites", "REAL DEFAULT 0"),
        ("pct_star_sellers", "REAL DEFAULT 0"),
        ("pct_bestsellers", "REAL DEFAULT 0"),
        ("revenue_per_listing", "REAL DEFAULT 0"),
        ("market_evidence_score", "REAL DEFAULT 0"),
        ("profitability_index", "REAL DEFAULT 0"),
    ]
    gap_cols = [
        ("price_p25_usd", "REAL DEFAULT 0"),
        ("price_median_usd", "REAL DEFAULT 0"),
        ("price_p75_usd", "REAL DEFAULT 0"),
        ("avg_favorites", "REAL DEFAULT 0"),
        ("pct_high_favorites", "REAL DEFAULT 0"),
        ("pct_star_sellers", "REAL DEFAULT 0"),
        ("pct_bestsellers", "REAL DEFAULT 0"),
        ("revenue_per_listing", "REAL DEFAULT 0"),
        ("market_evidence_score", "REAL DEFAULT 0"),
    ]
    for col, typedef in scan_cols:
        try:
            con.execute(f"ALTER TABLE scans ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass
    for col, typedef in gap_cols:
        try:
            con.execute(f"ALTER TABLE gap_reports ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass
    con.execute("CREATE INDEX IF NOT EXISTS idx_scans_profitability ON scans(profitability_index DESC)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_scans_market_evidence ON scans(market_evidence_score DESC)")


def init_db() -> None:
    """Create or migrate the database. Safe to call on every startup."""
    rebuild_scores_after_migration = False
    with _conn() as con:
        version = _get_version(con)
        if version < 1:
            _migrate_v1(con)
            _set_version(con, 1)
        if version < 2:
            _migrate_v2(con)
            _set_version(con, 2)
        if version < 3:
            _migrate_v3(con)
            _set_version(con, 3)
        if version < 4:
            _migrate_v4(con)
            _set_version(con, 4)
        if version < 5:
            _migrate_v5(con)
            _set_version(con, 5)
            rebuild_scores_after_migration = True
        if version < 6:
            _migrate_v6(con)
            _set_version(con, 6)
            rebuild_scores_after_migration = True
        if version < 7:
            _migrate_v7(con)
            _set_version(con, 7)
        if version < 8:
            _migrate_v8(con)
            _set_version(con, 8)
    if rebuild_scores_after_migration:
        rebuild_gap_scores()


def _migrate_v7(con: sqlite3.Connection) -> None:
    """Remove capped placeholder profit scores from scans without market evidence."""
    con.execute("""
        UPDATE scans
        SET opportunity_score=NULL,
            demand_score=NULL,
            margin_score=NULL,
            trend_score=NULL,
            gap_score=NULL,
            listing_efficiency=NULL,
            profitability_index=NULL
        WHERE COALESCE(market_evidence_score, 0) < 20
          AND COALESCE(avg_price_usd, 0) <= 0
          AND COALESCE(monthly_revenue_usd, 0) <= 0
          AND COALESCE(listing_count, 0) <= 0
    """)


def _migrate_v8(con: sqlite3.Connection) -> None:
    """Remove remaining capped demand/trend scores from thin market scans."""
    con.execute("""
        UPDATE scans
        SET demand_score=NULL,
            trend_score=NULL
        WHERE COALESCE(market_evidence_score, 0) < 20
          AND COALESCE(avg_price_usd, 0) <= 0
          AND COALESCE(monthly_revenue_usd, 0) <= 0
          AND COALESCE(listing_count, 0) <= 0
    """)


# ── Seed management ───────────────────────────────────────────────────────────

def load_seeds_from_library() -> int:
    if not SEED_PATH.exists():
        return 0
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    now = datetime.utcnow().isoformat()
    rows = []
    for domain, keywords in data.get("domains", {}).items():
        for kw in keywords:
            rows.append((kw.strip().lower(), domain, "library", now, 5))
    with _conn() as con:
        cur = con.executemany(
            "INSERT OR IGNORE INTO seeds (keyword, domain, source, added_at, priority) VALUES (?,?,?,?,?)",
            rows,
        )
        return cur.rowcount


def add_seed(keyword: str, domain: str = "discovered", source: str = "auto",
             priority: int = 5) -> bool:
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO seeds (keyword, domain, source, added_at, priority) VALUES (?,?,?,?,?)",
            (keyword.strip().lower(), domain, source, now, priority),
        )
        return cur.rowcount > 0


def add_seeds_bulk(keywords: list[str], domain: str = "discovered", source: str = "auto",
                   priority: int = 5) -> int:
    now = datetime.utcnow().isoformat()
    rows = [(kw.strip().lower(), domain, source, now, priority)
            for kw in keywords if kw.strip()]
    if not rows:
        return 0
    with _conn() as con:
        cur = con.executemany(
            "INSERT OR IGNORE INTO seeds (keyword, domain, source, added_at, priority) VALUES (?,?,?,?,?)",
            rows,
        )
        return cur.rowcount


# ── Expansion tree ────────────────────────────────────────────────────────────

def record_expansion(parent: str, children: list[str], source: str,
                     depth: int = 1) -> int:
    """
    Record parent -> child expansion relationships.
    Also bulk-adds children as seeds.
    Returns count of new seeds added.
    """
    if not children:
        return 0
    now = datetime.utcnow().isoformat()
    parent_kw = parent.strip().lower()
    child_rows = [(parent_kw, c.strip().lower(), source, depth, now)
                  for c in children if c.strip()]
    with _conn() as con:
        con.executemany(
            "INSERT OR IGNORE INTO expansion_tree (parent_keyword, child_keyword, source, depth, created_at) VALUES (?,?,?,?,?)",
            child_rows,
        )

    # Estimate scan depth of parent to set child depth priority
    priority = max(3, 7 - depth)  # deeper expansions get lower priority
    return add_seeds_bulk([c.strip().lower() for c in children],
                          domain="discovered", source=f"expand_{source}", priority=priority)


def get_expansion_children(keyword: str) -> list[str]:
    with _conn() as con:
        rows = con.execute(
            "SELECT child_keyword FROM expansion_tree WHERE parent_keyword = ?",
            (keyword.strip().lower(),)
        ).fetchall()
        return [r[0] for r in rows]


def get_expansion_depth(keyword: str) -> int:
    """How many levels deep from a seed is this keyword? 0 = original seed."""
    with _conn() as con:
        row = con.execute(
            "SELECT MIN(depth) FROM expansion_tree WHERE child_keyword = ?",
            (keyword.strip().lower(),)
        ).fetchone()
        return row[0] if row[0] is not None else 0


# ── Scan storage ──────────────────────────────────────────────────────────────

_BUYER_INTENT_TERMS = {
    "gift": 15,
    "gifts": 15,
    "personalized": 15,
    "custom": 14,
    "printable": 12,
    "template": 11,
    "svg": 10,
    "bundle": 9,
    "set": 8,
    "for": 7,
    "appreciation": 7,
}

_PRODUCT_TERMS = {
    "shirt",
    "sweatshirt",
    "hoodie",
    "mug",
    "tumbler",
    "sticker",
    "stickers",
    "wall art",
    "poster",
    "print",
    "prints",
    "tote",
    "bag",
    "ornament",
    "planner",
    "invitation",
    "sign",
    "decor",
    "keychain",
}

_PASSION_TERMS = {
    "mom",
    "dad",
    "teacher",
    "nurse",
    "bride",
    "wedding",
    "birthday",
    "christmas",
    "halloween",
    "valentine",
    "graduation",
    "cat",
    "dog",
    "book",
    "reader",
    "coffee",
    "wine",
    "yoga",
    "hiking",
    "plant",
    "zodiac",
}

_DOMAIN_PRIORITY_BOOST = {
    "professions": 9,
    "occasions_holidays": 8,
    "relationships": 8,
    "hobbies": 7,
    "pets": 7,
    "life_stages": 7,
    "trending_micro_niches": 6,
    "compound": 8,
    "discovered": 5,
}


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def score_keyword_buyer_intent(keyword: str) -> float:
    """Estimate how close a keyword is to a buyer-ready Etsy search."""
    kw = " ".join(keyword.lower().split())
    words = kw.split()
    if not words:
        return 0.0

    score = 20.0
    score += min(25.0, sum(points for term, points in _BUYER_INTENT_TERMS.items() if term in words or term in kw))
    score += 18.0 if any(term in kw for term in _PRODUCT_TERMS) else 0.0
    score += min(16.0, sum(4.0 for term in _PASSION_TERMS if term in words or term in kw))

    word_count = len(words)
    if 2 <= word_count <= 5:
        score += 18.0
    elif word_count == 1:
        score -= 18.0
    elif word_count <= 7:
        score += 8.0
    else:
        score -= 10.0

    if any(ch.isdigit() for ch in kw):
        score += 4.0
    if kw.startswith(("cute ", "funny ", "vintage ", "retro ", "minimalist ", "personalized ")):
        score += 5.0
    if kw in {"gift", "custom", "personalized", "shirt", "mug", "sticker", "wall art"}:
        score -= 25.0

    return _clamp_score(score)


def _score_supply_gap(listing_count: int | None) -> float:
    """Lower supply is better, but zero/unknown supply should not look perfect."""
    if not listing_count or listing_count <= 0:
        return 35.0
    pressure = math.log10(max(1, listing_count)) / math.log10(750_000) * 100
    return _clamp_score(100.0 - pressure)


def _score_listing_efficiency(monthly_rev: float, listing_count: int | None) -> float:
    """Revenue density proxy: more revenue per listing means a better gap."""
    if not listing_count or listing_count <= 0 or monthly_rev <= 0:
        return 0.0
    revenue_per_listing = monthly_rev / listing_count
    return _clamp_score(math.log10(max(1.0, revenue_per_listing)) / math.log10(250.0) * 100)


def _score_seed_priority(keyword: str, domain: str | None, priority: int | None) -> float:
    """Rank unscanned seeds by likely gap quality instead of age alone."""
    base_priority = (priority or 5) * 7.0
    domain_boost = _DOMAIN_PRIORITY_BOOST.get((domain or "").lower(), 4)
    return _clamp_score(
        base_priority
        + score_keyword_buyer_intent(keyword) * 0.45
        + domain_boost * 2.0
    )


def _calculate_gap_score(
    keyword: str,
    demand: float,
    trend: float,
    comp_quality: float,
    margin: float,
    monthly_rev: float,
    listing_count: int | None,
    full_gap_score: float | None = None,
) -> tuple[float, float]:
    """
    Composite gap score used by fast keyword rankings.

    It favors buyer-ready, revenue-dense, margin-friendly keywords with weak
    incumbents, and blends in the full gap report when deeper evidence exists.
    """
    buyer_intent = score_keyword_buyer_intent(keyword)
    supply_gap = _score_supply_gap(listing_count)
    listing_eff = _score_listing_efficiency(monthly_rev or 0, listing_count)
    quality_gap = 100.0 - comp_quality if comp_quality and comp_quality > 0 else 0.0

    lightweight = (
        (demand or 0) * 0.18
        + (trend or 0) * 0.12
        + quality_gap * 0.17
        + (margin or 0) * 0.13
        + listing_eff * 0.14
        + buyer_intent * 0.14
        + supply_gap * 0.12
    )

    if full_gap_score is not None and full_gap_score > 0:
        lightweight = lightweight * 0.55 + full_gap_score * 0.45

    return _clamp_score(lightweight), listing_eff


def _avg(values: list[float]) -> float:
    usable = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v)) and float(v) > 0]
    return sum(usable) / len(usable) if usable else 0.0


def _price_viability_score(avg_price: float) -> float:
    if avg_price <= 0:
        return 0.0
    if 12 <= avg_price <= 45:
        return 92.0
    if 8 <= avg_price < 12:
        return 72.0
    if 45 < avg_price <= 70:
        return 68.0
    if 4 <= avg_price < 8:
        return 48.0
    if avg_price > 70:
        return 52.0
    return 25.0


def _score_market_evidence(metrics: dict) -> float:
    ksd_count = metrics.get("keyword_market_rows", 0) or 0
    sampled = metrics.get("sampled_listings", 0) or 0
    return _clamp_score(
        min(ksd_count, 4) / 4 * 12
        + min(sampled, 60) / 60 * 22
        + (16 if metrics.get("avg_price_usd", 0) > 0 else 0)
        + (16 if metrics.get("monthly_revenue_usd", 0) > 0 else 0)
        + (10 if metrics.get("listing_count", 0) > 0 else 0)
        + (10 if metrics.get("competition_quality", 0) > 0 else 0)
        + (8 if metrics.get("avg_favorites", 0) > 0 else 0)
        + (6 if metrics.get("price_p25_usd", 0) > 0 and metrics.get("price_p75_usd", 0) > 0 else 0)
    )


def _score_profitability_index(
    keyword: str,
    demand: float,
    margin: float,
    comp_quality: float,
    monthly_rev: float,
    listing_count: int | None,
    avg_price: float,
    revenue_per_listing: float,
    avg_favorites: float,
    market_evidence_score: float,
) -> float:
    buyer_intent = score_keyword_buyer_intent(keyword)
    competition_ease = 100.0 - comp_quality if comp_quality > 0 else _score_supply_gap(listing_count)
    revenue_density = _score_listing_efficiency(monthly_rev, listing_count)
    if revenue_per_listing > 0:
        revenue_density = max(revenue_density, _clamp_score(math.log10(max(1.0, revenue_per_listing)) / math.log10(350.0) * 100))
    favorite_signal = _clamp_score(math.log10(max(1.0, avg_favorites)) / math.log10(5000.0) * 100) if avg_favorites > 0 else 0.0
    price_viability = _price_viability_score(avg_price)
    raw = (
        (demand or 0) * 0.18
        + (margin or 0) * 0.20
        + competition_ease * 0.14
        + revenue_density * 0.18
        + price_viability * 0.12
        + buyer_intent * 0.10
        + favorite_signal * 0.04
        + market_evidence_score * 0.04
    )
    if market_evidence_score < 35:
        raw = min(raw, 68.0)
    elif market_evidence_score < 55:
        raw = min(raw, 78.0)
    return _clamp_score(raw)


def _extract_market_metrics(keyword: str, report_data: dict) -> dict:
    ksd = report_data.get("keyword_search_data", []) or []
    if not isinstance(ksd, list):
        ksd = []
    normalized = keyword.strip().lower()
    matching = [item for item in ksd if str(item.get("keyword", "")).strip().lower() == normalized]
    rows = matching or ksd
    counts = [
        int(item.get("listing_count") or item.get("total_listing_count") or 0)
        for item in rows
        if item.get("listing_count") or item.get("total_listing_count")
    ]
    listing_count = int(sum(counts) / len(counts)) if counts else 0
    monthly_revenue = _avg([float(item.get("estimated_market_monthly_revenue_usd") or 0) for item in rows])
    if not monthly_revenue:
        monthly_revenue = float(report_data.get("estimated_market_monthly_revenue_usd") or 0)
    avg_price = _avg([float(item.get("avg_price_usd") or 0) for item in rows]) or float(report_data.get("avg_price_usd") or 0)
    revenue_per_listing = monthly_revenue / listing_count if monthly_revenue > 0 and listing_count > 0 else 0.0
    sampled_listings = sum(
        int(item.get("sampled_listing_count") or len(item.get("top_listing_titles") or []))
        for item in rows
        if isinstance(item, dict)
    )
    metrics = {
        "keyword_market_rows": len(rows),
        "sampled_listings": sampled_listings,
        "listing_count": listing_count,
        "avg_price_usd": avg_price,
        "price_min_usd": _avg([float(item.get("price_min") or 0) for item in rows]),
        "price_p25_usd": _avg([float(item.get("price_p25") or 0) for item in rows]),
        "price_median_usd": _avg([float(item.get("price_median") or 0) for item in rows]),
        "price_p75_usd": _avg([float(item.get("price_p75") or 0) for item in rows]),
        "price_max_usd": _avg([float(item.get("price_max") or 0) for item in rows]),
        "avg_favorites": _avg([float(item.get("avg_favorites") or 0) for item in rows]),
        "max_favorites": int(max([int(item.get("max_favorites") or 0) for item in rows] or [0])),
        "pct_high_favorites": _avg([float(item.get("pct_high_favorites") or 0) for item in rows]),
        "pct_star_sellers": _avg([float(item.get("pct_star_sellers") or 0) for item in rows]),
        "pct_bestsellers": _avg([float(item.get("pct_bestsellers") or 0) for item in rows]),
        "competition_quality": _avg([float(item.get("competition_quality_score") or 0) for item in rows]) or float(report_data.get("avg_competition_quality") or 0),
        "monthly_revenue_usd": monthly_revenue,
        "revenue_per_listing": revenue_per_listing,
    }
    metrics["market_evidence_score"] = _score_market_evidence(metrics)
    return metrics


def _suppress_thin_market_scores(
    opportunity: float,
    demand: float,
    margin: float,
    trend: float,
    metrics: dict,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Avoid saving placeholder-looking profit scores when market evidence is absent."""
    evidence = metrics.get("market_evidence_score", 0) or 0
    if evidence >= 20:
        return float(opportunity or 0), float(demand or 0), float(margin or 0), float(trend or 0)

    return None, None, None, None


def save_scan(keyword: str, report) -> None:
    add_seed(keyword, source="scan_created")

    if hasattr(report, "__dataclass_fields__"):
        import dataclasses
        r = dataclasses.asdict(report)
    else:
        r = dict(report)

    now = datetime.utcnow().isoformat()
    kw = keyword.strip().lower()

    opp = r.get("opportunity_score") or 0
    demand = r.get("demand_score") or 0
    trend = r.get("trend_velocity_score") or 0
    margin = r.get("margin_score") or 0
    metrics = _extract_market_metrics(kw, r)
    opp, demand, margin, trend = _suppress_thin_market_scores(opp, demand, margin, trend, metrics)
    listing_count = metrics["listing_count"] or None
    comp_quality = metrics["competition_quality"]
    comp_q = comp_quality if comp_quality and comp_quality > 0 else 0
    monthly_rev = metrics["monthly_revenue_usd"] or 0
    market_evidence = metrics["market_evidence_score"]
    if market_evidence >= 20:
        profitability_index = _score_profitability_index(
            kw,
            demand=demand,
            margin=margin or 0,
            comp_quality=comp_q,
            monthly_rev=monthly_rev,
            listing_count=listing_count,
            avg_price=metrics["avg_price_usd"],
            revenue_per_listing=metrics["revenue_per_listing"],
            avg_favorites=metrics["avg_favorites"],
            market_evidence_score=market_evidence,
        )

        gap, listing_eff = _calculate_gap_score(
            kw,
            demand=demand,
            trend=trend,
            comp_quality=comp_q,
            margin=margin or 0,
            monthly_rev=monthly_rev,
            listing_count=listing_count,
        )
    else:
        profitability_index = None
        gap = None
        listing_eff = None

    with _conn() as con:
        con.execute("""
            INSERT INTO scans
              (keyword, scanned_at, opportunity_score, demand_score, competition_score,
               margin_score, trend_score, avg_price_usd, monthly_revenue_usd,
               competition_quality, listing_count, sources_used, report_path,
               peak_months, keyword_clusters_json, entry_strategy,
               gap_score, listing_efficiency, score_delta, trajectory,
               price_min_usd, price_p25_usd, price_median_usd, price_p75_usd,
               price_max_usd, avg_favorites, max_favorites, pct_high_favorites,
               pct_star_sellers, pct_bestsellers, revenue_per_listing,
               market_evidence_score, profitability_index)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            kw, now, opp, demand,
            r.get("competition_score"), margin,
            trend, metrics["avg_price_usd"],
            monthly_rev, comp_quality, listing_count,
            json.dumps(r.get("sources_used", [])),
            r.get("report_path"),
            json.dumps(r.get("peak_months", [])),
            json.dumps(r.get("keyword_clusters", [])),
            r.get("entry_strategy"),
            gap, listing_eff, 0.0, "stable",
            metrics["price_min_usd"],
            metrics["price_p25_usd"],
            metrics["price_median_usd"],
            metrics["price_p75_usd"],
            metrics["price_max_usd"],
            metrics["avg_favorites"],
            metrics["max_favorites"],
            metrics["pct_high_favorites"],
            metrics["pct_star_sellers"],
            metrics["pct_bestsellers"],
            metrics["revenue_per_listing"],
            market_evidence,
            profitability_index,
        ))

    if gap is not None:
        _update_gap_score(kw, gap, listing_efficiency=listing_eff)


def _update_gap_score(keyword: str, new_gap: float, listing_efficiency: float | None = None) -> None:
    """Compute trajectory and update gap_scores table.

    Velocity is time-normalized to a 30-day rate so keywords rescanned
    frequently don't show inflated deltas vs. keywords rescanned monthly.
    e.g. a +10 point jump in 2 days = +150/30d velocity (breakout)
         a +10 point jump in 60 days = +5/30d velocity (stable)
    """
    with _conn() as con:
        prev = con.execute(
            "SELECT gap_score, last_computed FROM gap_scores WHERE keyword = ?", (keyword,)
        ).fetchone()
        prev_score = prev[0] if prev else None
        prev_time_str = prev[1] if prev else None
        delta = (new_gap - prev_score) if prev_score is not None else 0.0

        # Time-normalize delta to a 30-day velocity
        velocity = delta
        if prev_score is not None and prev_time_str:
            try:
                elapsed = datetime.utcnow() - datetime.fromisoformat(prev_time_str)
                days = elapsed.total_seconds() / 86400
                velocity = delta if days < 1 else delta / days * 30
            except Exception:
                pass

        if velocity >= 8:
            trajectory = "rising"
        elif velocity <= -8:
            trajectory = "declining"
        else:
            trajectory = "stable"

        breakout = 1 if velocity >= 15 else 0

        con.execute("""
            INSERT INTO gap_scores
              (keyword, gap_score, listing_efficiency, score_delta,
               previous_gap_score, trajectory, breakout_flag, last_computed)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(keyword) DO UPDATE SET
              previous_gap_score = gap_scores.gap_score,
              gap_score = excluded.gap_score,
              listing_efficiency = excluded.listing_efficiency,
              score_delta = excluded.score_delta,
              trajectory = excluded.trajectory,
              breakout_flag = excluded.breakout_flag,
              last_computed = excluded.last_computed
        """, (keyword, new_gap, listing_efficiency or 0.0, delta, prev_score, trajectory, breakout,
              datetime.utcnow().isoformat()))

        # Update trajectory on most recent scan row too
        con.execute("""
            UPDATE scans SET gap_score=?, score_delta=?, trajectory=?
            WHERE keyword=? AND id=(SELECT MAX(id) FROM scans WHERE keyword=?)
        """, (new_gap, delta, trajectory, keyword, keyword))


def rebuild_gap_scores() -> int:
    """Recompute gap scores for all scanned keywords. Returns count updated."""
    with _conn() as con:
        rows = con.execute("""
            SELECT s.keyword, sc.demand_score, sc.trend_score,
                   sc.competition_quality, sc.margin_score,
                   sc.monthly_revenue_usd, sc.listing_count,
                   gr.composite_gap_score
            FROM seeds s
            JOIN scans sc ON sc.keyword = s.keyword
            LEFT JOIN gap_reports gr ON gr.id = (
                SELECT MAX(id) FROM gap_reports gr2 WHERE gr2.keyword = s.keyword
            )
            WHERE sc.id = (SELECT MAX(id) FROM scans sc2 WHERE sc2.keyword = s.keyword)
        """).fetchall()

    count = 0
    for r in rows:
        gap, listing_eff = _calculate_gap_score(
            r["keyword"],
            demand=r["demand_score"] or 0,
            trend=r["trend_score"] or 0,
            comp_quality=r["competition_quality"] or 0,
            margin=r["margin_score"] or 0,
            monthly_rev=r["monthly_revenue_usd"] or 0,
            listing_count=r["listing_count"],
            full_gap_score=r["composite_gap_score"],
        )
        _update_gap_score(r["keyword"], gap, listing_efficiency=listing_eff)
        count += 1
    return count


# ── Queue / batch selection ───────────────────────────────────────────────────

def get_unscanned(limit: int = 20, domain: Optional[str] = None) -> list[str]:
    with _conn() as con:
        candidate_limit = max(limit * 12, 100)
        if domain:
            rows = con.execute("""
                SELECT s.keyword, s.domain, s.priority, s.added_at FROM seeds s
                WHERE s.domain=?
                  AND NOT EXISTS (SELECT 1 FROM scans sc WHERE sc.keyword=s.keyword)
                ORDER BY s.priority DESC, s.added_at ASC LIMIT ?
            """, (domain, candidate_limit)).fetchall()
        else:
            rows = con.execute("""
                SELECT s.keyword, s.domain, s.priority, s.added_at FROM seeds s
                WHERE NOT EXISTS (SELECT 1 FROM scans sc WHERE sc.keyword=s.keyword)
                ORDER BY s.priority DESC, s.added_at ASC LIMIT ?
            """, (candidate_limit,)).fetchall()
        ranked = sorted(
            rows,
            key=lambda r: (
                _score_seed_priority(r["keyword"], r["domain"], r["priority"]),
                r["added_at"] or "",
            ),
            reverse=True,
        )
        return [r["keyword"] for r in ranked[:limit]]


def get_stale(days: int = 30, limit: int = 20, domain: Optional[str] = None) -> list[str]:
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    with _conn() as con:
        base = """
            SELECT s.keyword FROM seeds s
            JOIN (SELECT keyword, MAX(scanned_at) AS last_scan FROM scans GROUP BY keyword) latest
              ON latest.keyword=s.keyword
            LEFT JOIN gap_scores gs ON gs.keyword=s.keyword
            LEFT JOIN scans sc ON sc.keyword=s.keyword
              AND sc.id=(SELECT MAX(id) FROM scans sc2 WHERE sc2.keyword=s.keyword)
            WHERE latest.last_scan < ?
        """
        if domain:
            rows = con.execute(base + """
                AND s.domain=?
                ORDER BY
                    gs.breakout_flag DESC,
                    gs.gap_score DESC,
                    gs.listing_efficiency DESC,
                    sc.opportunity_score DESC,
                    latest.last_scan ASC
                LIMIT ?
            """,
                               (cutoff, domain, limit)).fetchall()
        else:
            rows = con.execute(base + """
                ORDER BY
                    gs.breakout_flag DESC,
                    gs.gap_score DESC,
                    gs.listing_efficiency DESC,
                    sc.opportunity_score DESC,
                    latest.last_scan ASC
                LIMIT ?
            """,
                               (cutoff, limit)).fetchall()
        return [r["keyword"] for r in rows]


def get_breakouts(limit: int = 20) -> list[str]:
    """Keywords whose gap score jumped 12+ points since last scan — highest priority."""
    with _conn() as con:
        rows = con.execute("""
            SELECT keyword FROM gap_scores
            WHERE breakout_flag=1
            ORDER BY score_delta DESC LIMIT ?
        """, (limit,)).fetchall()
        return [r[0] for r in rows]


def get_profit_evidence_gaps(limit: int = 20, min_age_hours: int = 12) -> list[str]:
    """High-potential keywords whose market evidence is still too thin."""
    cutoff = (datetime.utcnow() - timedelta(hours=min_age_hours)).isoformat()
    with _conn() as con:
        rows = con.execute("""
            SELECT s.keyword
            FROM seeds s
            JOIN scans sc ON sc.keyword=s.keyword
            LEFT JOIN gap_scores gs ON gs.keyword=s.keyword
            WHERE sc.id=(SELECT MAX(id) FROM scans sc2 WHERE sc2.keyword=s.keyword)
              AND sc.scanned_at < ?
              AND (
                COALESCE(sc.market_evidence_score, 0) < 55
                OR COALESCE(sc.avg_price_usd, 0) <= 0
                OR COALESCE(sc.monthly_revenue_usd, 0) <= 0
              )
              AND (
                COALESCE(sc.profitability_index, 0) >= 55
                OR COALESCE(gs.gap_score, sc.gap_score, 0) >= 58
                OR COALESCE(sc.opportunity_score, 0) >= 68
                OR COALESCE(sc.market_evidence_score, 0) < 20
              )
            ORDER BY
              COALESCE(sc.profitability_index, 0) DESC,
              COALESCE(gs.gap_score, sc.gap_score, 0) DESC,
              COALESCE(sc.opportunity_score, 0) DESC,
              sc.scanned_at ASC
            LIMIT ?
        """, (cutoff, limit)).fetchall()
        return [r[0] for r in rows]


def get_next_batch(count: int = 10, stale_days: int = 30) -> list[str]:
    """Smart batch: breakouts, profit evidence gaps, unscanned, then stale."""
    result: list[str] = []
    seen: set[str] = set()

    def _add(items):
        for kw in items:
            if kw not in seen and len(result) < count:
                result.append(kw)
                seen.add(kw)

    _add(get_breakouts(limit=count))
    _add(get_profit_evidence_gaps(limit=count))
    _add(get_unscanned(limit=count))
    _add(get_stale(days=stale_days, limit=count))
    return result[:count]


def get_all_seeds_with_status(limit: int = 2000) -> list[dict]:
    """Return all seeds with scan status for the UI checklist."""
    with _conn() as con:
        rows = con.execute("""
            SELECT s.keyword, s.domain, s.source, s.priority, s.added_at,
                   sc.scanned_at,
                   sc.opportunity_score,
                   COALESCE(gs.gap_score, sc.gap_score) AS gap_score,
                   gs.trajectory,
                   COALESCE(gs.breakout_flag, 0) AS breakout_flag,
                   gs.listing_efficiency
            FROM seeds s
            LEFT JOIN scans sc ON sc.keyword = s.keyword
              AND sc.id = (SELECT MAX(id) FROM scans sc2 WHERE sc2.keyword=s.keyword)
            LEFT JOIN gap_scores gs ON gs.keyword=s.keyword
            ORDER BY
                CASE WHEN sc.scanned_at IS NULL THEN 0 ELSE 1 END,
                COALESCE(gs.gap_score, sc.gap_score, 0) DESC,
                sc.scanned_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ── Query ─────────────────────────────────────────────────────────────────────

def get_top_opportunities(limit: int = 100, domain: Optional[str] = None) -> list[dict]:
    with _conn() as con:
        base = """
            SELECT s.keyword, s.domain, sc.opportunity_score, sc.demand_score,
                   sc.competition_score, sc.margin_score, sc.trend_score,
                   sc.avg_price_usd, sc.monthly_revenue_usd, sc.competition_quality,
                   sc.listing_count, sc.scanned_at, sc.entry_strategy, sc.peak_months,
                   sc.gap_score, sc.score_delta, sc.trajectory,
                   gs.breakout_flag
            FROM seeds s
            JOIN scans sc ON sc.keyword=s.keyword
            LEFT JOIN gap_scores gs ON gs.keyword=s.keyword
            WHERE sc.id=(SELECT MAX(id) FROM scans sc2 WHERE sc2.keyword=s.keyword)
              AND sc.opportunity_score IS NOT NULL
        """
        if domain:
            rows = con.execute(base + " AND s.domain=? ORDER BY sc.opportunity_score DESC LIMIT ?",
                               (domain, limit)).fetchall()
        else:
            rows = con.execute(base + " ORDER BY sc.opportunity_score DESC LIMIT ?",
                               (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_top_gaps(limit: int = 100, domain: Optional[str] = None) -> list[dict]:
    """Ranked by gap_score (underserved high-demand) rather than raw opportunity."""
    with _conn() as con:
        base = """
            SELECT s.keyword, s.domain, gs.gap_score, gs.score_delta, gs.trajectory,
                   gs.breakout_flag, sc.demand_score, sc.competition_quality,
                   sc.avg_price_usd, sc.monthly_revenue_usd, sc.scanned_at,
                   sc.opportunity_score, sc.trend_score
            FROM gap_scores gs
            JOIN seeds s ON s.keyword=gs.keyword
            JOIN scans sc ON sc.keyword=gs.keyword
            WHERE sc.id=(SELECT MAX(id) FROM scans sc2 WHERE sc2.keyword=gs.keyword)
              AND gs.gap_score IS NOT NULL
        """
        if domain:
            rows = con.execute(base + " AND s.domain=? ORDER BY gs.gap_score DESC LIMIT ?",
                               (domain, limit)).fetchall()
        else:
            rows = con.execute(base + " ORDER BY gs.gap_score DESC LIMIT ?",
                               (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_store_idea_signals(limit: int = 800, domain: Optional[str] = None) -> list[dict]:
    """Latest scanned keyword rows enriched with the newest gap report per keyword."""
    with _conn() as con:
        base = """
            SELECT
                s.keyword,
                s.domain,
                sc.opportunity_score,
                sc.demand_score,
                sc.competition_score,
                sc.margin_score,
                sc.trend_score,
                sc.avg_price_usd,
                sc.monthly_revenue_usd,
                sc.competition_quality,
                sc.listing_count,
                sc.price_min_usd,
                sc.price_p25_usd,
                sc.price_median_usd,
                sc.price_p75_usd,
                sc.price_max_usd,
                sc.avg_favorites,
                sc.max_favorites,
                sc.pct_high_favorites,
                sc.pct_star_sellers,
                sc.pct_bestsellers,
                sc.revenue_per_listing,
                sc.market_evidence_score,
                sc.profitability_index,
                sc.scanned_at,
                sc.entry_strategy,
                sc.peak_months,
                sc.keyword_clusters_json,
                COALESCE(sc.gap_score, gs.gap_score) AS gap_score,
                sc.listing_efficiency,
                sc.score_delta,
                sc.trajectory,
                gs.breakout_flag,
                gr.composite_gap_score,
                gr.volume_gap_score,
                gr.quality_gap_score,
                gr.tag_gap_score,
                gr.style_gap_score,
                gr.price_gap_score,
                gr.recency_gap_score,
                gr.buyer_intent_score,
                gr.profit_gap_score,
                gr.entry_angle,
                gr.recommended_price_min,
                gr.recommended_price_max,
                gr.listings_analyzed,
                gr.avg_listing_age_months,
                gr.revenue_per_listing AS gap_revenue_per_listing,
                gr.market_evidence_score AS gap_market_evidence_score
            FROM seeds s
            LEFT JOIN scans sc ON sc.keyword=s.keyword
            LEFT JOIN gap_scores gs ON gs.keyword=s.keyword
            LEFT JOIN gap_reports gr ON gr.id = (
                SELECT MAX(id) FROM gap_reports gr2 WHERE gr2.keyword=s.keyword
            )
            WHERE (sc.id IS NULL OR sc.id=(SELECT MAX(id) FROM scans sc2 WHERE sc2.keyword=s.keyword))
              AND (
                sc.opportunity_score IS NOT NULL
                OR sc.gap_score IS NOT NULL
                OR gs.gap_score IS NOT NULL
                OR gr.composite_gap_score IS NOT NULL
              )
        """
        if domain:
            rows = con.execute(
                base + """
                AND s.domain=?
                ORDER BY
                    ((COALESCE(sc.profitability_index, 0) * 0.34)
                    + (COALESCE(sc.margin_score, 0) * 0.18)
                    + (COALESCE(sc.gap_score, gr.composite_gap_score, gs.gap_score, 0) * 0.18)
                    + (COALESCE(sc.demand_score, 0) * 0.14)
                    + (COALESCE(sc.market_evidence_score, gr.market_evidence_score, 0) * 0.10)
                    + (COALESCE(sc.revenue_per_listing, gr.revenue_per_listing, 0) * 0.06)) DESC
                LIMIT ?
                """,
                (domain, limit),
            ).fetchall()
        else:
            rows = con.execute(
                base + """
                ORDER BY
                    ((COALESCE(sc.profitability_index, 0) * 0.34)
                    + (COALESCE(sc.margin_score, 0) * 0.18)
                    + (COALESCE(sc.gap_score, gr.composite_gap_score, gs.gap_score, 0) * 0.18)
                    + (COALESCE(sc.demand_score, 0) * 0.14)
                    + (COALESCE(sc.market_evidence_score, gr.market_evidence_score, 0) * 0.10)
                    + (COALESCE(sc.revenue_per_listing, gr.revenue_per_listing, 0) * 0.06)) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_stats() -> dict:
    with _conn() as con:
        total_seeds = con.execute("SELECT COUNT(*) FROM seeds").fetchone()[0]
        scanned     = con.execute("SELECT COUNT(DISTINCT keyword) FROM scans").fetchone()[0]
        total_scans = con.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
        breakouts   = con.execute("SELECT COUNT(*) FROM gap_scores WHERE breakout_flag=1").fetchone()[0]
        expansion_edges = con.execute("SELECT COUNT(*) FROM expansion_tree").fetchone()[0]

        avg_opp_row = con.execute("""
            SELECT AVG(sc.opportunity_score)
            FROM (SELECT keyword, MAX(id) as id FROM scans GROUP BY keyword) latest
            JOIN scans sc ON sc.id=latest.id
            WHERE sc.opportunity_score IS NOT NULL
        """).fetchone()
        avg_opp = avg_opp_row[0] if avg_opp_row[0] else 0

        avg_gap_row = con.execute("SELECT AVG(gap_score) FROM gap_scores WHERE gap_score IS NOT NULL").fetchone()
        avg_gap = avg_gap_row[0] if avg_gap_row[0] else 0

        top_gap = con.execute("""
            SELECT gs.keyword, gs.gap_score FROM gap_scores gs ORDER BY gs.gap_score DESC LIMIT 1
        """).fetchone()

        domains = con.execute(
            "SELECT domain, COUNT(*) as cnt FROM seeds GROUP BY domain ORDER BY cnt DESC"
        ).fetchall()

        return {
            "total_seeds":      total_seeds,
            "scanned":          scanned,
            "unscanned":        total_seeds - scanned,
            "total_scans":      total_scans,
            "coverage_pct":     round(scanned / total_seeds * 100, 1) if total_seeds else 0,
            "avg_opportunity":  round(avg_opp, 1),
            "avg_gap_score":    round(avg_gap, 1),
            "breakout_count":   breakouts,
            "expansion_edges":  expansion_edges,
            "top_gap_keyword":  dict(top_gap) if top_gap else None,
            "domains":          [dict(r) for r in domains],
        }


def get_health() -> dict:
    """Database file health and size stats."""
    db_path = DB_PATH.resolve()
    size_mb = db_path.stat().st_size / 1_048_576 if db_path.exists() else 0
    with _conn() as con:
        oldest = con.execute("SELECT MIN(scanned_at) FROM scans").fetchone()[0]
        newest = con.execute("SELECT MAX(scanned_at) FROM scans").fetchone()[0]
        orphan_seeds = con.execute("""
            SELECT COUNT(*) FROM seeds WHERE keyword NOT IN (SELECT keyword FROM scans)
        """).fetchone()[0]
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    return {
        "db_path":      str(db_path),
        "size_mb":      round(size_mb, 2),
        "oldest_scan":  oldest,
        "newest_scan":  newest,
        "orphan_seeds": orphan_seeds,
        "integrity":    integrity,
        "schema_version": SCHEMA_VERSION,
    }


def search_keywords(query: str, limit: int = 100) -> list[dict]:
    q = f"%{query.lower()}%"
    with _conn() as con:
        rows = con.execute("""
            SELECT s.keyword, s.domain, s.source, s.added_at,
                   sc.opportunity_score, sc.avg_price_usd, sc.scanned_at,
                   gs.gap_score, gs.trajectory, gs.breakout_flag
            FROM seeds s
            LEFT JOIN (SELECT keyword, MAX(id) as id FROM scans GROUP BY keyword) latest
              ON latest.keyword=s.keyword
            LEFT JOIN scans sc ON sc.id=latest.id
            LEFT JOIN gap_scores gs ON gs.keyword=s.keyword
            WHERE s.keyword LIKE ?
            ORDER BY gs.gap_score DESC NULLS LAST
            LIMIT ?
        """, (q, limit)).fetchall()
        return [dict(r) for r in rows]


def get_all_seeds(domain: Optional[str] = None) -> list[dict]:
    with _conn() as con:
        extra = "WHERE s.domain=?" if domain else ""
        args = (domain,) if domain else ()
        rows = con.execute(f"""
            SELECT s.keyword, s.domain, s.source, s.added_at, s.priority,
                   sc.opportunity_score, sc.scanned_at, gs.gap_score, gs.trajectory
            FROM seeds s
            LEFT JOIN (SELECT keyword, MAX(id) as id FROM scans GROUP BY keyword) latest
              ON latest.keyword=s.keyword
            LEFT JOIN scans sc ON sc.id=latest.id
            LEFT JOIN gap_scores gs ON gs.keyword=s.keyword
            {extra}
            ORDER BY gs.gap_score DESC NULLS LAST, s.keyword ASC
        """, args).fetchall()
        return [dict(r) for r in rows]


def get_domains() -> list[str]:
    with _conn() as con:
        rows = con.execute("SELECT DISTINCT domain FROM seeds ORDER BY domain").fetchall()
        return [r["domain"] for r in rows]


# ── Scheduler log ─────────────────────────────────────────────────────────────

def log_scheduler_run(mode: str = "continuous") -> int:
    """Start a new scheduler run record. Returns run ID."""
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO scheduler_log (started_at, mode, status) VALUES (?,?,?)",
            (now, mode, "running")
        )
        return cur.lastrowid


def update_scheduler_run(run_id: int, keywords_scanned: int = 0,
                         new_seeds: int = 0, status: str = "running",
                         error_msg: Optional[str] = None) -> None:
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        con.execute("""
            UPDATE scheduler_log SET keywords_scanned=?, new_seeds_found=?,
            status=?, error_msg=?, completed_at=?
            WHERE id=?
        """, (keywords_scanned, new_seeds, status,
              error_msg, now if status != "running" else None, run_id))


def get_scheduler_history(limit: int = 20) -> list[dict]:
    with _conn() as con:
        rows = con.execute("""
            SELECT * FROM scheduler_log ORDER BY started_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ── Export ────────────────────────────────────────────────────────────────────

def export_csv(path: str | Path, domain: Optional[str] = None,
               sort_by: str = "gap_score") -> int:
    """Export top opportunities to CSV. Returns row count."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = get_top_gaps(limit=10_000, domain=domain) if sort_by == "gap_score" \
        else get_top_opportunities(limit=10_000, domain=domain)

    if not data:
        return 0

    fieldnames = list(data[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(data)
    return len(data)


def export_json(path: str | Path, include_raw_scans: bool = False) -> int:
    """Export full DB snapshot to JSON. Returns row count."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict = {
        "exported_at": datetime.utcnow().isoformat(),
        "stats": get_stats(),
        "top_gaps": get_top_gaps(limit=500),
        "top_opportunities": get_top_opportunities(limit=500),
    }

    if include_raw_scans:
        with _conn() as con:
            rows = con.execute("SELECT * FROM scans ORDER BY scanned_at DESC LIMIT 5000").fetchall()
            payload["raw_scans"] = [dict(r) for r in rows]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return len(payload["top_gaps"])


# ── Backup ────────────────────────────────────────────────────────────────────

def backup(backup_dir: str | Path = "workspace/_keyword_db/backups") -> Path:
    """Copy the SQLite file to a timestamped backup. Returns backup path."""
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"keywords_{ts}.sqlite"
    shutil.copy2(DB_PATH, dest)
    # Keep only last 10 backups
    backups = sorted(backup_dir.glob("keywords_*.sqlite"))
    for old in backups[:-10]:
        old.unlink(missing_ok=True)
    return dest


# ── Prune ─────────────────────────────────────────────────────────────────────

def prune_old_scans(keep_per_keyword: int = 5) -> int:
    """
    Delete old scan rows, keeping the N most recent per keyword.
    Returns total rows deleted.
    """
    with _conn() as con:
        # Find IDs to delete: all except the N most recent per keyword
        rows = con.execute("""
            SELECT id FROM scans WHERE id NOT IN (
                SELECT id FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY keyword ORDER BY scanned_at DESC
                    ) as rn FROM scans
                ) ranked WHERE rn <= ?
            )
        """, (keep_per_keyword,)).fetchall()
        ids = [r[0] for r in rows]
        if ids:
            placeholders = ",".join("?" * len(ids))
            con.execute(f"DELETE FROM scans WHERE id IN ({placeholders})", ids)
        return len(ids)


def vacuum() -> None:
    """Reclaim space after pruning. Runs outside a transaction."""
    con = _conn()
    con.isolation_level = None
    con.execute("VACUUM")
    con.close()


# ── Gap reports ───────────────────────────────────────────────────────────────

def save_gap_report(
    keyword: str,
    volume_gap: float = 0.0,
    quality_gap: float = 0.0,
    tag_gap: float = 0.0,
    style_gap: float = 0.0,
    price_gap: float = 0.0,
    recency_gap: float = 0.0,
    buyer_intent: float = 0.0,
    profit_gap: float = 0.0,
    composite_gap: float = 0.0,
    entry_angle: str = "",
    recommended_price_min: float = 0.0,
    recommended_price_max: float = 0.0,
    untagged_searches: Optional[list] = None,
    dominant_competitor_tags: Optional[list] = None,
    recommended_tags: Optional[list] = None,
    listings_analyzed: int = 0,
    avg_listing_age_months: float = 0.0,
    price_p25_usd: float = 0.0,
    price_median_usd: float = 0.0,
    price_p75_usd: float = 0.0,
    avg_favorites: float = 0.0,
    pct_high_favorites: float = 0.0,
    pct_star_sellers: float = 0.0,
    pct_bestsellers: float = 0.0,
    revenue_per_listing: float = 0.0,
    market_evidence_score: float = 0.0,
) -> int:
    """Insert a gap report row. Returns the new row ID."""
    now = datetime.utcnow().isoformat()
    kw = keyword.strip().lower()
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO gap_reports
              (keyword, analyzed_at,
               volume_gap_score, quality_gap_score, tag_gap_score,
               style_gap_score, price_gap_score, recency_gap_score,
               buyer_intent_score, profit_gap_score,
               composite_gap_score, entry_angle,
               recommended_price_min, recommended_price_max,
               untagged_searches_json, dominant_competitor_tags_json,
               recommended_tags_json, listings_analyzed, avg_listing_age_months,
               price_p25_usd, price_median_usd, price_p75_usd,
               avg_favorites, pct_high_favorites, pct_star_sellers, pct_bestsellers,
               revenue_per_listing, market_evidence_score)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            kw, now,
            volume_gap, quality_gap, tag_gap,
            style_gap, price_gap, recency_gap,
            buyer_intent, profit_gap,
            composite_gap, entry_angle,
            recommended_price_min, recommended_price_max,
            json.dumps(untagged_searches or []),
            json.dumps(dominant_competitor_tags or []),
            json.dumps(recommended_tags or []),
            listings_analyzed, avg_listing_age_months,
            price_p25_usd,
            price_median_usd,
            price_p75_usd,
            avg_favorites,
            pct_high_favorites,
            pct_star_sellers,
            pct_bestsellers,
            revenue_per_listing,
            market_evidence_score,
        ))
        row_id = cur.lastrowid

    with _conn() as con:
        latest = con.execute("""
            SELECT demand_score, trend_score, competition_quality, margin_score,
                   monthly_revenue_usd, listing_count
            FROM scans
            WHERE keyword=?
            ORDER BY scanned_at DESC
            LIMIT 1
        """, (kw,)).fetchone()

    if latest:
        gap, listing_eff = _calculate_gap_score(
            kw,
            demand=latest["demand_score"] or 0,
            trend=latest["trend_score"] or 0,
            comp_quality=latest["competition_quality"] or 0,
            margin=latest["margin_score"] or 0,
            monthly_rev=latest["monthly_revenue_usd"] or 0,
            listing_count=latest["listing_count"],
            full_gap_score=composite_gap,
        )
        _update_gap_score(kw, gap, listing_efficiency=listing_eff)

    return row_id


def get_gap_report(keyword: str) -> Optional[dict]:
    """Most recent gap report for a keyword, or None."""
    kw = keyword.strip().lower()
    with _conn() as con:
        row = con.execute("""
            SELECT * FROM gap_reports WHERE keyword=?
            ORDER BY analyzed_at DESC LIMIT 1
        """, (kw,)).fetchone()
        if not row:
            return None
        d = dict(row)
        for field in ("untagged_searches_json", "dominant_competitor_tags_json", "recommended_tags_json"):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                d[field] = []
        return d


def get_top_gap_reports(limit: int = 100, min_score: float = 0.0) -> list[dict]:
    """Most recent gap report per keyword, ranked by composite_gap_score."""
    with _conn() as con:
        rows = con.execute("""
            SELECT gr.* FROM gap_reports gr
            WHERE gr.id = (
                SELECT MAX(id) FROM gap_reports gr2 WHERE gr2.keyword = gr.keyword
            )
            AND gr.composite_gap_score >= ?
            ORDER BY gr.composite_gap_score DESC
            LIMIT ?
        """, (min_score, limit)).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            for field in ("untagged_searches_json", "dominant_competitor_tags_json", "recommended_tags_json"):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    d[field] = []
            results.append(d)
        return results
