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
SCHEMA_VERSION = 10
SCORE_VERSION = "evidence-v1"
MIN_LISTING_SAMPLE = 5


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
    if DB_PATH.exists() or not SEED_DB_PATH.exists():
        return False
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SEED_DB_PATH.resolve().as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(DB_PATH) as target:
            source.backup(target)
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
        if version < 9:
            con.execute("ALTER TABLE scans ADD COLUMN scan_status TEXT")
            con.execute("ALTER TABLE scans ADD COLUMN scan_error TEXT")
            con.execute("""UPDATE scans SET scan_status=CASE
                WHEN COALESCE(market_evidence_score,0)>=20 THEN 'evidence'
                WHEN COALESCE(sources_used,'[]') NOT IN ('[]','', 'null') THEN 'signals'
                ELSE 'no_data' END""")
            _set_version(con, 9)
        if version < 10:
            _migrate_v10(con)
            _set_version(con, 10)
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


def _migrate_v10(con: sqlite3.Connection) -> None:
    """Add evidence provenance and remove legacy, unverified rankings."""
    for col, typedef in [
        ("score_version", "TEXT"),
        ("evidence_status", "TEXT NOT NULL DEFAULT 'unverified'"),
        ("evidence_details_json", "TEXT"),
        ("observed_search_volume", "REAL"),
        ("sampled_listing_count", "INTEGER"),
    ]:
        try:
            con.execute(f"ALTER TABLE scans ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass

    for col, typedef in [
        ("score_version", "TEXT"),
        ("evidence_status", "TEXT NOT NULL DEFAULT 'unverified'"),
        ("evidence_details_json", "TEXT"),
    ]:
        try:
            con.execute(f"ALTER TABLE gap_reports ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass

    con.executescript("""
        CREATE TABLE IF NOT EXISTS keyword_sources (
            keyword             TEXT NOT NULL,
            source              TEXT NOT NULL,
            first_seen_at       TEXT NOT NULL,
            last_seen_at        TEXT NOT NULL,
            observation_count   INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (keyword, source),
            FOREIGN KEY (keyword) REFERENCES seeds(keyword) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS keyword_observations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword         TEXT NOT NULL,
            source          TEXT NOT NULL,
            observed_at     TEXT NOT NULL,
            metric          TEXT NOT NULL,
            value           REAL NOT NULL,
            unit            TEXT NOT NULL,
            sample_size     INTEGER,
            metadata_json   TEXT,
            UNIQUE(keyword, source, observed_at, metric),
            FOREIGN KEY (keyword) REFERENCES seeds(keyword) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS keyword_product_economics (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword                 TEXT NOT NULL,
            product_type            TEXT NOT NULL,
            observed_at             TEXT NOT NULL,
            source                  TEXT NOT NULL,
            sale_price_usd          REAL NOT NULL,
            production_cost_usd     REAL NOT NULL,
            shipping_cost_usd       REAL NOT NULL,
            marketplace_fees_usd    REAL NOT NULL,
            advertising_cost_usd    REAL NOT NULL,
            refund_allowance_usd    REAL NOT NULL,
            contribution_profit_usd REAL NOT NULL,
            UNIQUE(keyword, product_type, observed_at, source),
            FOREIGN KEY (keyword) REFERENCES seeds(keyword) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS keyword_outcomes (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword                 TEXT NOT NULL,
            listing_id              TEXT NOT NULL,
            product_type            TEXT NOT NULL,
            period_start            TEXT NOT NULL,
            period_end              TEXT NOT NULL,
            impressions             INTEGER NOT NULL,
            clicks                  INTEGER NOT NULL,
            orders                  INTEGER NOT NULL,
            revenue_usd             REAL NOT NULL,
            marketplace_fees_usd    REAL NOT NULL,
            advertising_cost_usd    REAL NOT NULL,
            production_cost_usd     REAL NOT NULL,
            shipping_cost_usd       REAL NOT NULL,
            refunds_usd             REAL NOT NULL,
            contribution_profit_usd REAL NOT NULL,
            source                  TEXT NOT NULL,
            UNIQUE(listing_id, keyword, period_start, period_end, source),
            FOREIGN KEY (keyword) REFERENCES seeds(keyword) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_keyword_sources_source
            ON keyword_sources(source, keyword);
        CREATE INDEX IF NOT EXISTS idx_keyword_observations_lookup
            ON keyword_observations(keyword, metric, observed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_keyword_economics_lookup
            ON keyword_product_economics(keyword, product_type, observed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_keyword_outcomes_lookup
            ON keyword_outcomes(keyword, product_type, period_end DESC);
    """)

    now = datetime.utcnow().isoformat()
    con.execute("""
        INSERT OR IGNORE INTO keyword_sources
            (keyword, source, first_seen_at, last_seen_at, observation_count)
        SELECT keyword, source, added_at, ?, 1 FROM seeds
    """, (now,))

    # A retained score must prove that it came from an actual listing sample.
    con.execute("""
        DELETE FROM gap_reports
        WHERE COALESCE(listings_analyzed, 0) < ?
           OR COALESCE(market_evidence_score, 0) <= 0
    """, (MIN_LISTING_SAMPLE,))
    con.execute("""
        DELETE FROM scans
        WHERE COALESCE(sampled_listing_count, 0) < ?
           OR COALESCE(listing_count, 0) <= 0
           OR COALESCE(avg_price_usd, 0) <= 0
           OR COALESCE(market_evidence_score, 0) <= 0
    """, (MIN_LISTING_SAMPLE,))
    con.execute("""
        DELETE FROM gap_scores
        WHERE NOT EXISTS (
            SELECT 1 FROM scans
            WHERE scans.keyword=gap_scores.keyword
              AND scans.evidence_status='verified'
        )
    """)
    con.execute("DELETE FROM scheduler_log")


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
        con.executemany("""
            INSERT OR IGNORE INTO keyword_sources
                (keyword, source, first_seen_at, last_seen_at, observation_count)
            VALUES (?, 'library', ?, ?, 1)
        """, [(keyword, now, now) for keyword, _domain, _source, _added, _priority in rows])
        return cur.rowcount


def add_seed(keyword: str, domain: str = "discovered", source: str = "auto",
             priority: int = 5) -> bool:
    now = datetime.utcnow().isoformat()
    normalized = keyword.strip().lower()
    with _conn() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO seeds (keyword, domain, source, added_at, priority) VALUES (?,?,?,?,?)",
            (normalized, domain, source, now, priority),
        )
        con.execute("""
            INSERT INTO keyword_sources
                (keyword, source, first_seen_at, last_seen_at, observation_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(keyword, source) DO UPDATE SET
                last_seen_at=excluded.last_seen_at,
                observation_count=keyword_sources.observation_count + 1
        """, (normalized, source, now, now))
        con.execute(
            "UPDATE seeds SET priority=MAX(priority, ?) WHERE keyword=?",
            (priority, normalized),
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
        con.executemany("""
            INSERT INTO keyword_sources
                (keyword, source, first_seen_at, last_seen_at, observation_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(keyword, source) DO UPDATE SET
                last_seen_at=excluded.last_seen_at,
                observation_count=keyword_sources.observation_count + 1
        """, [(keyword, source, now, now) for keyword, _domain, _source, _added, _priority in rows])
        con.executemany(
            "UPDATE seeds SET priority=MAX(priority, ?) WHERE keyword=?",
            [(priority, keyword) for keyword, _domain, _source, _added, _priority in rows],
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
    "editable": 13,
    "printable": 12,
    "template": 11,
    "download": 11,
    "digital": 10,
    "instant": 9,
    "svg": 10,
    "bundle": 9,
    "set": 8,
    "for": 7,
    "appreciation": 7,
    "memorial": 10,
    "retirement": 9,
    "graduation": 9,
    "bachelorette": 8,
    "bridesmaid": 8,
    "shower": 7,
    "party": 7,
}

_PRODUCT_TERMS = {
    "shirt",
    "t-shirt",
    "tee",
    "tank",
    "sweatshirt",
    "hoodie",
    "apparel",
    "hat",
    "cap",
    "socks",
    "mug",
    "tumbler",
    "glass",
    "cup",
    "sticker",
    "stickers",
    "wall art",
    "poster",
    "canvas",
    "portrait",
    "print",
    "prints",
    "tote",
    "bag",
    "ornament",
    "planner",
    "journal",
    "binder",
    "worksheet",
    "calendar",
    "invitation",
    "invite",
    "card",
    "label",
    "tag",
    "game",
    "sign",
    "decor",
    "doormat",
    "pillow",
    "blanket",
    "candle",
    "keychain",
    "badge reel",
    "phone case",
    "case",
    "clipart",
    "png",
    "svg",
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
    "pickleball",
    "golf",
    "dance",
    "dancer",
    "runner",
    "yoga",
    "hiking",
    "camping",
    "fishing",
    "gardening",
    "plant",
    "zodiac",
    "librarian",
    "counselor",
    "therapist",
    "realtor",
    "coach",
    "grandma",
    "grandpa",
}

_RETAILER_NOISE_TERMS = {
    "amazon",
    "walmart",
    "target",
    "five below",
    "temu",
    "shein",
    "costco",
    "etsy.com",
}

_IP_RISK_TERMS = {
    "disney",
    "marvel",
    "star wars",
    "harry potter",
    "pokemon",
    "nintendo",
    "lego",
    "hello kitty",
    "snoopy",
    "nike",
    "stanley",
    "barbie",
    "taylor swift",
    "swiftie",
    "nfl",
    "nba",
    "mlb",
    "nhl",
    "fortnite",
    "minecraft",
}

_LOCAL_NOISE_TERMS = {
    "near me",
    "nearby",
    "local",
    "in store",
    "same day",
}

_LOW_BUYER_INTENT_PHRASES = {
    "how to",
    "tutorial",
    "ideas for",
    "meaning of",
    "definition",
    "reddit",
    "pinterest",
}

_LOW_VALUE_WORDS = {
    "free",
    "cheap",
}

_STYLE_TERMS = {
    "aesthetic",
    "vintage",
    "retro",
    "minimalist",
    "boho",
    "western",
    "coquette",
    "cottagecore",
    "dark academia",
    "gothic",
    "botanical",
    "celestial",
    "coastal",
    "rustic",
    "funny",
    "sarcastic",
    "cute",
    "spooky",
}

_OCCASION_TERMS = {
    "birthday",
    "wedding",
    "graduation",
    "retirement",
    "christmas",
    "halloween",
    "valentine",
    "mother's day",
    "father's day",
    "teacher appreciation",
    "housewarming",
    "memorial",
    "anniversary",
    "baby shower",
    "bridal shower",
    "first christmas",
}

_SOURCE_QUALITY_BOOST = {
    "expand_google_suggest": 8.0,
    "expand_competitor_terms": 9.0,
    "expand_trends_related": 6.0,
    "expand_etsy_autocomplete": 7.0,
    "google_suggest_bootstrap": 8.0,
    "google_suggest_proven": 9.0,
    "google_suggest_adjacent": 8.0,
    "google_suggest_trend": 7.0,
    "google_suggest_wild": 4.0,
    "etsy_autocomplete_bootstrap": 7.0,
    "etsy_trending_page": 10.0,
    "library": 3.0,
    "llm_brainstorm": -30.0,
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

_SCAN_LANE_ALLOCATION = {
    "proven": 0.50,
    "adjacent": 0.25,
    "trend": 0.15,
    "wild": 0.10,
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
    score += min(10.0, sum(3.0 for term in _STYLE_TERMS if term in words or term in kw))
    score += min(10.0, sum(4.0 for term in _OCCASION_TERMS if term in kw))

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


def _contains_any_phrase(keyword: str, phrases: set[str]) -> bool:
    return any(phrase in keyword for phrase in phrases)


def _source_quality_boost(source_key: str) -> float:
    if source_key in _SOURCE_QUALITY_BOOST:
        return _SOURCE_QUALITY_BOOST[source_key]
    if source_key.startswith("google_suggest_"):
        return 7.0
    if source_key.startswith("compound_"):
        return 4.0
    if source_key.startswith("expand_"):
        return -4.0
    return 0.0


def _keyword_signal_flags(keyword: str) -> dict[str, bool]:
    kw = " ".join(keyword.lower().split())
    words = set(kw.split())
    return {
        "product": any(term in kw for term in _PRODUCT_TERMS),
        "intent": any(term in words or term in kw for term in _BUYER_INTENT_TERMS),
        "passion": any(term in words or term in kw for term in _PASSION_TERMS),
        "style": any(term in words or term in kw for term in _STYLE_TERMS),
        "occasion": any(term in kw for term in _OCCASION_TERMS),
    }


def keyword_scan_lane(keyword: str, domain: str | None = None, source: str | None = None) -> str:
    """Classify a seed into a scanner portfolio lane."""
    kw = " ".join(keyword.lower().split())
    source_key = (source or "").lower()
    domain_key = (domain or "").lower()
    flags = _keyword_signal_flags(kw)
    signal_count = sum(1 for value in flags.values() if value)
    word_count = len(kw.split())

    if source_key.startswith("expand_") or source_key.startswith("compound_") or domain_key == "compound":
        return "adjacent"
    if "trend" in source_key or "trend" in domain_key or domain_key in {"aesthetics", "nature_themes"}:
        return "trend"
    if source_key.endswith("_wild") or (word_count >= 4 and flags["product"] and signal_count >= 2 and score_keyword_buyer_intent(kw) < 72):
        return "wild"
    if flags["product"] and (flags["intent"] or flags["passion"] or flags["occasion"]) and score_keyword_buyer_intent(kw) >= 58:
        return "proven"
    return "wild" if word_count >= 3 else "proven"


def score_keyword_scan_priority(
    keyword: str,
    domain: str | None = None,
    priority: int | None = None,
    source: str | None = None,
) -> float:
    """
    Pre-scan quality score for deciding what deserves scanner time.

    This intentionally favors buyer-ready Etsy searches and pushes noisy
    retailer/local/research phrases out of the high-throughput queue.
    """
    kw = " ".join(keyword.lower().split())
    words = kw.split()
    score = _score_seed_priority(keyword, domain, priority)

    if _contains_any_phrase(kw, _RETAILER_NOISE_TERMS):
        score -= 42.0
    if _contains_any_phrase(kw, _IP_RISK_TERMS):
        score -= 55.0
    if _contains_any_phrase(kw, _LOCAL_NOISE_TERMS):
        score -= 38.0
    if _contains_any_phrase(kw, _LOW_BUYER_INTENT_PHRASES):
        score -= 28.0
    if any(word in _LOW_VALUE_WORDS for word in words):
        score -= 36.0
    if ":" in kw:
        score -= 18.0

    word_count = len(words)
    if 2 <= word_count <= 5:
        score += 8.0
    elif word_count == 1:
        score -= 22.0
    elif word_count > 7:
        score -= 24.0

    if any(term in kw for term in _PRODUCT_TERMS):
        score += 9.0
    if any(term in kw for term in _BUYER_INTENT_TERMS):
        score += 7.0
    if any(term in kw for term in _PASSION_TERMS):
        score += 5.0
    if any(term in kw for term in _STYLE_TERMS):
        score += 4.0
    if any(term in kw for term in _OCCASION_TERMS):
        score += 5.0

    flags = _keyword_signal_flags(kw)
    signal_count = sum(1 for value in flags.values() if value)
    if flags["product"] and signal_count >= 2:
        score += 9.0
    elif signal_count == 0:
        score -= 12.0

    source_key = (source or "").lower()
    score += _source_quality_boost(source_key)

    return _clamp_score(score)


def is_scanworthy_seed(
    keyword: str,
    domain: str | None = None,
    priority: int | None = None,
    source: str | None = None,
    min_score: float = 58.0,
) -> bool:
    kw = " ".join(keyword.lower().split())
    if not kw or len(kw) < 4:
        return False
    if _contains_any_phrase(kw, _LOCAL_NOISE_TERMS):
        return False
    if _contains_any_phrase(kw, _RETAILER_NOISE_TERMS):
        return False
    if _contains_any_phrase(kw, _IP_RISK_TERMS):
        return False
    if any(word in _LOW_VALUE_WORDS for word in kw.split()):
        return False
    return score_keyword_scan_priority(kw, domain, priority, source) >= min_score


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


def _present_number(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _extract_market_metrics(keyword: str, report_data: dict) -> dict:
    """Extract only observations for the requested keyword; never borrow defaults."""
    raw_rows = report_data.get("keyword_search_data", []) or []
    if not isinstance(raw_rows, list):
        raw_rows = []
    normalized = keyword.strip().lower()
    rows = [
        item for item in raw_rows
        if isinstance(item, dict)
        and str(item.get("keyword", "")).strip().lower() == normalized
    ]
    row = rows[0] if len(rows) == 1 else None

    signals = report_data.get("keyword_signals", []) or []
    volume_observations = [
        _present_number(item.get("monthly_searches"))
        for item in signals
        if isinstance(item, dict)
        and str(item.get("keyword", "")).strip().lower() == normalized
        and str(item.get("source", "")).lower() in {"erank", "marmalead"}
    ]
    volume_observations = [value for value in volume_observations if value is not None and value > 0]

    if row is None:
        return {
            "sampled_listings": None,
            "listing_count": None,
            "avg_price_usd": None,
            "price_min_usd": None,
            "price_p25_usd": None,
            "price_median_usd": None,
            "price_p75_usd": None,
            "price_max_usd": None,
            "avg_favorites": None,
            "max_favorites": None,
            "pct_high_favorites": None,
            "pct_star_sellers": None,
            "pct_bestsellers": None,
            "observed_search_volume": volume_observations[0] if len(volume_observations) == 1 else None,
        }

    return {
        "sampled_listings": int(row.get("sampled_listing_count") or len(row.get("top_listing_titles") or [])) or None,
        "listing_count": int(row.get("listing_count") or row.get("total_listing_count") or 0) or None,
        "avg_price_usd": _present_number(row.get("avg_price_usd")),
        "price_min_usd": _present_number(row.get("price_min")),
        "price_p25_usd": _present_number(row.get("price_p25")),
        "price_median_usd": _present_number(row.get("price_median")),
        "price_p75_usd": _present_number(row.get("price_p75")),
        "price_max_usd": _present_number(row.get("price_max")),
        "avg_favorites": _present_number(row.get("avg_favorites")),
        "max_favorites": int(row["max_favorites"]) if row.get("max_favorites") is not None else None,
        "pct_high_favorites": _present_number(row.get("pct_high_favorites")),
        "pct_star_sellers": _present_number(row.get("pct_star_sellers")),
        "pct_bestsellers": _present_number(row.get("pct_bestsellers")),
        "observed_search_volume": volume_observations[0] if len(volume_observations) == 1 else None,
    }


def _classify_market_evidence(metrics: dict, scan_error: str | None = None) -> tuple[str, dict]:
    requirements = {
        "listing_sample": (metrics.get("sampled_listings") or 0) >= MIN_LISTING_SAMPLE,
        "listing_count": metrics.get("listing_count") is not None,
        "average_price": metrics.get("avg_price_usd") is not None,
    }
    if scan_error:
        status = "failed"
    elif all(requirements.values()):
        status = "verified"
    elif any(value is not None for value in metrics.values()):
        status = "partial"
    else:
        status = "unverified"
    return status, {
        "requirements": requirements,
        "missing": [name for name, present in requirements.items() if not present],
        "score_available": False,
        "score_reason": "No calibrated outcome model is available for this evidence set.",
    }


def _record_scan_observations(con: sqlite3.Connection, keyword: str, observed_at: str,
                              metrics: dict, sources: list[str]) -> None:
    market_source = next(
        (source for source in sources if source in {"etsy_open_api", "etsy_search_scraper"}),
        "etsy_market",
    )
    definitions = {
        "listing_count": ("count", None),
        "sampled_listings": ("count", None),
        "avg_price_usd": ("usd", metrics.get("sampled_listings")),
        "price_p25_usd": ("usd", metrics.get("sampled_listings")),
        "price_median_usd": ("usd", metrics.get("sampled_listings")),
        "price_p75_usd": ("usd", metrics.get("sampled_listings")),
        "avg_favorites": ("count", metrics.get("sampled_listings")),
        "pct_star_sellers": ("percent", metrics.get("sampled_listings")),
        "pct_bestsellers": ("percent", metrics.get("sampled_listings")),
    }
    for metric, (unit, sample_size) in definitions.items():
        value = metrics.get(metric)
        if value is None:
            continue
        con.execute("""
            INSERT OR REPLACE INTO keyword_observations
                (keyword, source, observed_at, metric, value, unit, sample_size, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
        """, (keyword, market_source, observed_at, metric, value, unit, sample_size))

    if metrics.get("observed_search_volume") is not None:
        con.execute("""
            INSERT OR REPLACE INTO keyword_observations
                (keyword, source, observed_at, metric, value, unit, sample_size, metadata_json)
            VALUES (?, 'external_keyword_provider', ?, 'monthly_searches', ?, 'searches_per_month', NULL, NULL)
        """, (keyword, observed_at, metrics["observed_search_volume"]))


def save_scan(keyword: str, report) -> None:
    add_seed(keyword, source="scan_created")

    if hasattr(report, "__dataclass_fields__"):
        import dataclasses
        r = dataclasses.asdict(report)
    else:
        r = dict(report)

    now = datetime.utcnow().isoformat()
    kw = keyword.strip().lower()

    metrics = _extract_market_metrics(kw, r)
    sources = [str(source) for source in (r.get("sources_used") or []) if source]
    evidence_status, evidence_details = _classify_market_evidence(metrics, r.get("scan_error"))
    scan_status = (
        "failed" if evidence_status == "failed"
        else "evidence" if evidence_status == "verified"
        else "signals" if sources
        else "no_data"
    )

    with _conn() as con:
        cur = con.execute("""
            INSERT INTO scans
              (keyword, scanned_at, opportunity_score, demand_score, competition_score,
               margin_score, trend_score, avg_price_usd, monthly_revenue_usd,
               competition_quality, listing_count, sources_used, report_path,
               peak_months, keyword_clusters_json, entry_strategy,
               gap_score, listing_efficiency, score_delta, trajectory,
               price_min_usd, price_p25_usd, price_median_usd, price_p75_usd,
               price_max_usd, avg_favorites, max_favorites, pct_high_favorites,
               pct_star_sellers, pct_bestsellers, revenue_per_listing,
               market_evidence_score, profitability_index, scan_status, scan_error)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            kw, now, None, None,
            None, None,
            None, metrics["avg_price_usd"],
            None, None, metrics["listing_count"],
            json.dumps(sources),
            r.get("report_path"),
            json.dumps(r.get("peak_months", [])),
            json.dumps(r.get("keyword_clusters", [])),
            r.get("entry_strategy"),
            None, None, None, None,
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
            None,
            None,
            None,
            scan_status,
            r.get("scan_error"),
        ))
        con.execute("""
            UPDATE scans
            SET score_version=NULL,
                evidence_status=?,
                evidence_details_json=?,
                observed_search_volume=?,
                sampled_listing_count=?
            WHERE id=?
        """, (
            evidence_status,
            json.dumps(evidence_details),
            metrics.get("observed_search_volume"),
            metrics.get("sampled_listings"),
            cur.lastrowid,
        ))
        _record_scan_observations(con, kw, now, metrics, sources)


def _update_gap_score(keyword: str, new_gap: float, listing_efficiency: float | None = None) -> None:
    """Retired: legacy gap trajectories were derived from unversioned estimates."""
    raise RuntimeError("gap score synthesis is disabled; persist verified observations instead")


def rebuild_gap_scores() -> int:
    """Remove legacy synthetic scores. Verified scores must be recomputed by a versioned model."""
    with _conn() as con:
        removed = con.execute("SELECT COUNT(*) FROM gap_scores").fetchone()[0]
        con.execute("DELETE FROM gap_scores")
        con.execute("""
            UPDATE scans SET gap_score=NULL, score_delta=NULL, trajectory=NULL,
                             listing_efficiency=NULL
        """)
    return removed


# ── Queue / batch selection ───────────────────────────────────────────────────

def _unscanned_candidate_rows(domain: Optional[str], candidate_limit: int) -> list[sqlite3.Row]:
    with _conn() as con:
        if domain:
            return con.execute("""
                SELECT s.keyword, s.domain, s.source, s.priority, s.added_at FROM seeds s
                WHERE s.domain=?
                  AND NOT EXISTS (SELECT 1 FROM scans sc WHERE sc.keyword=s.keyword)
                ORDER BY s.priority DESC, s.added_at ASC LIMIT ?
            """, (domain, candidate_limit)).fetchall()
        return con.execute("""
            SELECT s.keyword, s.domain, s.source, s.priority, s.added_at FROM seeds s
            WHERE NOT EXISTS (SELECT 1 FROM scans sc WHERE sc.keyword=s.keyword)
            ORDER BY s.priority DESC, s.added_at ASC LIMIT ?
        """, (candidate_limit,)).fetchall()


def _rank_seed_rows(rows: list[sqlite3.Row]) -> list[tuple[float, str, sqlite3.Row]]:
    ranked = [
        (
            score_keyword_scan_priority(r["keyword"], r["domain"], r["priority"], r["source"]),
            keyword_scan_lane(r["keyword"], r["domain"], r["source"]),
            r,
        )
        for r in rows
    ]
    return sorted(ranked, key=lambda item: (item[0], item[2]["added_at"] or ""), reverse=True)


def _lane_quotas(limit: int) -> dict[str, int]:
    if limit <= 0:
        return {lane: 0 for lane in _SCAN_LANE_ALLOCATION}

    lanes = list(_SCAN_LANE_ALLOCATION.keys())
    quotas = {lane: int(limit * _SCAN_LANE_ALLOCATION[lane]) for lane in lanes}
    quotas["proven"] += limit - sum(quotas.values())

    if limit >= len(lanes):
        for lane in lanes:
            if quotas[lane] == 0:
                donor = max(lanes, key=lambda key: quotas[key])
                if quotas[donor] > 1:
                    quotas[donor] -= 1
                    quotas[lane] = 1
    return quotas


def get_unscanned_portfolio(limit: int = 20, domain: Optional[str] = None, min_quality: float = 58.0) -> list[str]:
    """Return the explicit-priority queue; do not infer market quality from wording."""
    rows = _unscanned_candidate_rows(domain, limit)
    return [row["keyword"] for row in rows]


def get_unscanned(limit: int = 20, domain: Optional[str] = None, min_quality: float = 58.0) -> list[str]:
    rows = _unscanned_candidate_rows(domain, limit)
    return [row["keyword"] for row in rows]


def get_stale(days: int = 30, limit: int = 20, domain: Optional[str] = None) -> list[str]:
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    with _conn() as con:
        base = """
            SELECT s.keyword FROM seeds s
            JOIN (SELECT keyword, MAX(scanned_at) AS last_scan FROM scans GROUP BY keyword) latest
              ON latest.keyword=s.keyword
            WHERE latest.last_scan < ?
        """
        if domain:
            rows = con.execute(base + """
                AND s.domain=?
                ORDER BY latest.last_scan ASC
                LIMIT ?
            """,
                               (cutoff, domain, limit)).fetchall()
        else:
            rows = con.execute(base + """
                ORDER BY latest.last_scan ASC
                LIMIT ?
            """,
                               (cutoff, limit)).fetchall()
        return [r["keyword"] for r in rows]


def get_breakouts(limit: int = 20) -> list[str]:
    """No breakout is asserted until comparable, versioned observations exist."""
    return []


def get_profit_evidence_gaps(limit: int = 20, min_age_hours: int = 12) -> list[str]:
    """Old attempts missing the explicit minimum market observations."""
    cutoff = (datetime.utcnow() - timedelta(hours=min_age_hours)).isoformat()
    with _conn() as con:
        rows = con.execute("""
            SELECT s.keyword
            FROM seeds s
            JOIN scans sc ON sc.keyword=s.keyword
            WHERE sc.id=(SELECT MAX(id) FROM scans sc2 WHERE sc2.keyword=s.keyword)
              AND sc.scanned_at < ?
              AND (
                sc.evidence_status != 'verified'
                OR sc.sampled_listing_count IS NULL
                OR sc.sampled_listing_count < ?
                OR sc.avg_price_usd IS NULL
                OR sc.listing_count IS NULL
              )
            ORDER BY sc.scanned_at ASC
            LIMIT ?
        """, (cutoff, MIN_LISTING_SAMPLE, limit)).fetchall()
        return [r[0] for r in rows]


def get_next_batch(count: int = 10, stale_days: int = 30) -> list[str]:
    """Smart batch: evidence refresh plus protected new-niche discovery lanes."""
    result: list[str] = []
    seen: set[str] = set()

    def _add(items):
        for kw in items:
            if kw not in seen and len(result) < count:
                result.append(kw)
                seen.add(kw)

    evidence_budget = max(1, min(count, count // 4 or 1))
    _add(get_profit_evidence_gaps(limit=evidence_budget))

    remaining = count - len(result)
    if remaining > 0:
        _add(get_unscanned_portfolio(limit=remaining, min_quality=58.0))

    remaining = count - len(result)
    if remaining > 0:
        _add(get_unscanned(limit=remaining, min_quality=54.0))

    _add(get_stale(days=stale_days, limit=count))
    return result[:count]


def get_all_seeds_with_status(limit: int = 2000) -> list[dict]:
    """Return all seeds with scan status for the UI checklist."""
    with _conn() as con:
        rows = con.execute("""
            SELECT s.keyword, s.domain,
                   COALESCE((SELECT GROUP_CONCAT(ks.source, ', ')
                             FROM keyword_sources ks WHERE ks.keyword=s.keyword), s.source) AS source,
                   s.priority, s.added_at,
                   attempt.scanned_at,
                   attempt.scan_status,
                   attempt.scan_error,
                   attempt.evidence_status,
                   attempt.evidence_details_json,
                   evidence.opportunity_score,
                   evidence.gap_score,
                   evidence.trajectory,
                   evidence.observed_search_volume,
                   evidence.listing_count,
                   evidence.sampled_listing_count,
                   evidence.avg_price_usd,
                   0 AS breakout_flag,
                   evidence.listing_efficiency,
                   evidence.score_version
            FROM seeds s
            LEFT JOIN scans attempt ON attempt.keyword = s.keyword
              AND attempt.id = (SELECT MAX(id) FROM scans sc2 WHERE sc2.keyword=s.keyword)
            LEFT JOIN scans evidence ON evidence.keyword = s.keyword
              AND evidence.id = (
                  SELECT MAX(id) FROM scans sc3
                  WHERE sc3.keyword=s.keyword AND sc3.evidence_status='verified'
              )
            ORDER BY
                CASE WHEN attempt.scanned_at IS NULL THEN 0 ELSE 1 END,
                attempt.scanned_at DESC,
                s.keyword ASC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ── Query ─────────────────────────────────────────────────────────────────────

def get_top_opportunities(limit: int = 100, domain: Optional[str] = None) -> list[dict]:
    """Return only versioned, verified scores; there is no fallback ranking."""
    with _conn() as con:
        base = """
            SELECT s.keyword, s.domain, sc.opportunity_score, sc.demand_score,
                   sc.competition_score, sc.margin_score, sc.trend_score,
                   sc.avg_price_usd, sc.monthly_revenue_usd, sc.competition_quality,
                   sc.listing_count, sc.scanned_at, sc.entry_strategy, sc.peak_months,
                   sc.gap_score, sc.score_delta, sc.trajectory, sc.profitability_index,
                   sc.evidence_status, sc.score_version, sc.evidence_details_json,
                   COALESCE(sc.profitability_index, sc.opportunity_score, sc.gap_score) AS primary_score,
                   CASE
                       WHEN sc.profitability_index IS NOT NULL THEN 'profitability_index'
                       WHEN sc.opportunity_score IS NOT NULL THEN 'opportunity_score'
                       WHEN sc.gap_score IS NOT NULL THEN 'gap_score'
                       WHEN sc.gap_score IS NOT NULL THEN 'gap_score'
                       ELSE NULL
                   END AS primary_score_source,
                   0 AS breakout_flag
            FROM seeds s
            JOIN scans sc ON sc.keyword=s.keyword
            WHERE sc.id=(
                SELECT MAX(id) FROM scans sc2
                WHERE sc2.keyword=s.keyword AND sc2.evidence_status='verified'
            )
              AND sc.score_version IS NOT NULL
              AND COALESCE(sc.profitability_index, sc.opportunity_score, sc.gap_score) IS NOT NULL
        """
        if domain:
            rows = con.execute(base + " AND s.domain=? ORDER BY primary_score DESC, s.keyword ASC LIMIT ?",
                               (domain, limit)).fetchall()
        else:
            rows = con.execute(base + " ORDER BY primary_score DESC, s.keyword ASC LIMIT ?",
                               (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_top_gaps(limit: int = 100, domain: Optional[str] = None) -> list[dict]:
    """Return only verified, versioned gap reports."""
    with _conn() as con:
        base = """
            SELECT s.keyword, s.domain, gr.composite_gap_score AS gap_score,
                   NULL AS score_delta, NULL AS trajectory, 0 AS breakout_flag,
                   sc.demand_score, sc.competition_quality, sc.avg_price_usd,
                   sc.monthly_revenue_usd, sc.scanned_at, sc.opportunity_score,
                   sc.trend_score, sc.profitability_index,
                   gr.composite_gap_score AS primary_score,
                   'gap_score' AS primary_score_source,
                   gr.evidence_status, gr.score_version, gr.evidence_details_json
            FROM gap_reports gr
            JOIN seeds s ON s.keyword=gr.keyword
            JOIN scans sc ON sc.keyword=gr.keyword
            WHERE gr.id=(SELECT MAX(id) FROM gap_reports gr2 WHERE gr2.keyword=gr.keyword)
              AND sc.id=(SELECT MAX(id) FROM scans sc2 WHERE sc2.keyword=gr.keyword AND sc2.evidence_status='verified')
              AND gr.evidence_status='verified'
              AND gr.score_version IS NOT NULL
              AND gr.composite_gap_score IS NOT NULL
        """
        if domain:
            rows = con.execute(base + " AND s.domain=? ORDER BY gr.composite_gap_score DESC LIMIT ?",
                               (domain, limit)).fetchall()
        else:
            rows = con.execute(base + " ORDER BY gr.composite_gap_score DESC LIMIT ?",
                               (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_store_idea_signals(limit: int = 800, domain: Optional[str] = None) -> list[dict]:
    """Versioned, verified ranking rows only; unknowns never receive a fallback rank."""
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
                sc.sources_used,
                sc.gap_score,
                sc.listing_efficiency,
                sc.score_delta,
                sc.trajectory,
                0 AS breakout_flag,
                sc.evidence_status,
                sc.score_version,
                sc.evidence_details_json,
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
            JOIN scans sc ON sc.keyword=s.keyword
            LEFT JOIN gap_reports gr ON gr.id = (
                SELECT MAX(id) FROM gap_reports gr2
                WHERE gr2.keyword=s.keyword AND gr2.evidence_status='verified'
            )
            WHERE sc.id=(SELECT MAX(id) FROM scans sc2
                         WHERE sc2.keyword=s.keyword AND sc2.evidence_status='verified')
              AND sc.score_version IS NOT NULL
              AND COALESCE(sc.profitability_index, sc.opportunity_score,
                           sc.gap_score, gr.composite_gap_score) IS NOT NULL
        """
        if domain:
            rows = con.execute(
                base + """
                AND s.domain=?
                ORDER BY COALESCE(sc.profitability_index, sc.opportunity_score,
                                  sc.gap_score, gr.composite_gap_score) DESC
                LIMIT ?
                """,
                (domain, limit),
            ).fetchall()
        else:
            rows = con.execute(
                base + """
                ORDER BY COALESCE(sc.profitability_index, sc.opportunity_score,
                                  sc.gap_score, gr.composite_gap_score) DESC
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
        avg_opp = avg_opp_row[0]

        avg_gap_row = con.execute("""
            SELECT AVG(composite_gap_score) FROM gap_reports
            WHERE evidence_status='verified' AND score_version IS NOT NULL
              AND composite_gap_score IS NOT NULL
        """).fetchone()
        avg_gap = avg_gap_row[0]

        top_gap = con.execute("""
            SELECT keyword, composite_gap_score AS gap_score FROM gap_reports
            WHERE evidence_status='verified' AND score_version IS NOT NULL
              AND composite_gap_score IS NOT NULL
            ORDER BY composite_gap_score DESC LIMIT 1
        """).fetchone()

        domains = con.execute(
            "SELECT domain, COUNT(*) as cnt FROM seeds GROUP BY domain ORDER BY cnt DESC"
        ).fetchall()

        quality = con.execute("""SELECT
            SUM(sc.scan_status IN ('signals','evidence')) AS successful,
            SUM(sc.scan_status='evidence') AS evidence_backed,
            SUM(sc.scan_status='failed') AS failed,
            SUM(sc.scan_status='no_data') AS no_data,
            SUM(sc.scanned_at < ?) AS stale
            FROM scans sc JOIN (SELECT keyword, MAX(id) id FROM scans GROUP BY keyword) latest ON latest.id=sc.id
        """, ((datetime.utcnow()-timedelta(days=30)).isoformat(),)).fetchone()
        return {
            "attempted": scanned,
            "successful": quality["successful"] or 0,
            "evidence_backed": quality["evidence_backed"] or 0,
            "failed": quality["failed"] or 0,
            "no_data": quality["no_data"] or 0,
            "stale": quality["stale"] or 0,
            "total_seeds":      total_seeds,
            "scanned":          scanned,
            "unscanned":        total_seeds - scanned,
            "total_scans":      total_scans,
            "coverage_pct":     round(scanned / total_seeds * 100, 1) if total_seeds else None,
            "avg_opportunity":  round(avg_opp, 1) if avg_opp is not None else None,
            "avg_gap_score":    round(avg_gap, 1) if avg_gap is not None else None,
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


def record_product_economics(
    keyword: str,
    product_type: str,
    sale_price_usd: float,
    production_cost_usd: float,
    shipping_cost_usd: float,
    marketplace_fees_usd: float,
    advertising_cost_usd: float,
    refund_allowance_usd: float,
    source: str,
    observed_at: str | None = None,
) -> float:
    """Store auditable unit economics and return exact contribution profit."""
    values = (
        sale_price_usd, production_cost_usd, shipping_cost_usd,
        marketplace_fees_usd, advertising_cost_usd, refund_allowance_usd,
    )
    if not keyword.strip() or not product_type.strip() or not source.strip():
        raise ValueError("keyword, product_type, and source are required")
    if any(not math.isfinite(float(value)) or float(value) < 0 for value in values):
        raise ValueError("economics values must be finite and non-negative")
    if sale_price_usd <= 0:
        raise ValueError("sale_price_usd must be greater than zero")

    contribution = round(float(sale_price_usd) - sum(float(value) for value in values[1:]), 4)
    add_seed(keyword, source="economics")
    timestamp = observed_at or datetime.utcnow().isoformat()
    with _conn() as con:
        con.execute("""
            INSERT OR REPLACE INTO keyword_product_economics
              (keyword, product_type, observed_at, source, sale_price_usd,
               production_cost_usd, shipping_cost_usd, marketplace_fees_usd,
               advertising_cost_usd, refund_allowance_usd, contribution_profit_usd)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            keyword.strip().lower(), product_type.strip().lower(), timestamp, source.strip(),
            sale_price_usd, production_cost_usd, shipping_cost_usd,
            marketplace_fees_usd, advertising_cost_usd, refund_allowance_usd,
            contribution,
        ))
    return contribution


def record_keyword_outcome(
    *,
    keyword: str,
    listing_id: str,
    product_type: str,
    period_start: str,
    period_end: str,
    impressions: int,
    clicks: int,
    orders: int,
    revenue_usd: float,
    marketplace_fees_usd: float,
    advertising_cost_usd: float,
    production_cost_usd: float,
    shipping_cost_usd: float,
    refunds_usd: float,
    source: str,
) -> float:
    """Store observed listing outcomes without estimating missing values."""
    required = (keyword, listing_id, product_type, period_start, period_end, source)
    counts = (impressions, clicks, orders)
    money = (
        revenue_usd, marketplace_fees_usd, advertising_cost_usd,
        production_cost_usd, shipping_cost_usd, refunds_usd,
    )
    if not all(str(value).strip() for value in required):
        raise ValueError("keyword, listing, product, period, and source fields are required")
    if any(int(value) < 0 for value in counts):
        raise ValueError("outcome counts must be non-negative")
    if any(not math.isfinite(float(value)) or float(value) < 0 for value in money):
        raise ValueError("outcome money values must be finite and non-negative")

    contribution = round(float(revenue_usd) - sum(float(value) for value in money[1:]), 4)
    add_seed(keyword, source="outcome")
    with _conn() as con:
        con.execute("""
            INSERT OR REPLACE INTO keyword_outcomes
              (keyword, listing_id, product_type, period_start, period_end,
               impressions, clicks, orders, revenue_usd, marketplace_fees_usd,
               advertising_cost_usd, production_cost_usd, shipping_cost_usd,
               refunds_usd, contribution_profit_usd, source)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            keyword.strip().lower(), listing_id.strip(), product_type.strip().lower(),
            period_start, period_end, impressions, clicks, orders, revenue_usd,
            marketplace_fees_usd, advertising_cost_usd, production_cost_usd,
            shipping_cost_usd, refunds_usd, contribution, source.strip(),
        ))
    return contribution


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
    volume_gap: float | None = None,
    quality_gap: float | None = None,
    tag_gap: float | None = None,
    style_gap: float | None = None,
    price_gap: float | None = None,
    recency_gap: float | None = None,
    buyer_intent: float | None = None,
    profit_gap: float | None = None,
    composite_gap: float | None = None,
    entry_angle: str = "",
    recommended_price_min: float | None = None,
    recommended_price_max: float | None = None,
    untagged_searches: Optional[list] = None,
    dominant_competitor_tags: Optional[list] = None,
    recommended_tags: Optional[list] = None,
    listings_analyzed: int = 0,
    avg_listing_age_months: float | None = None,
    price_p25_usd: float | None = None,
    price_median_usd: float | None = None,
    price_p75_usd: float | None = None,
    avg_favorites: float | None = None,
    pct_high_favorites: float | None = None,
    pct_star_sellers: float | None = None,
    pct_bestsellers: float | None = None,
    revenue_per_listing: float | None = None,
    market_evidence_score: float | None = None,
    score_version: str | None = None,
) -> int:
    """Persist observed gap inputs; only an explicit complete score is rankable."""
    now = datetime.utcnow().isoformat()
    kw = keyword.strip().lower()
    evidence_status = "verified" if listings_analyzed >= MIN_LISTING_SAMPLE else (
        "partial" if listings_analyzed > 0 else "unverified"
    )
    accepted_score_version = (
        score_version if evidence_status == "verified" and composite_gap is not None else None
    )
    evidence_details = {
        "listings_analyzed": listings_analyzed,
        "minimum_listing_sample": MIN_LISTING_SAMPLE,
        "score_available": accepted_score_version is not None,
        "missing": [] if listings_analyzed >= MIN_LISTING_SAMPLE else ["minimum_listing_sample"],
    }
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
               revenue_per_listing, market_evidence_score,
               score_version, evidence_status, evidence_details_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
            accepted_score_version,
            evidence_status,
            json.dumps(evidence_details),
        ))
        row_id = cur.lastrowid
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
    """Most recent versioned, verified gap report per keyword."""
    with _conn() as con:
        rows = con.execute("""
            SELECT gr.* FROM gap_reports gr
            WHERE gr.id = (
                SELECT MAX(id) FROM gap_reports gr2 WHERE gr2.keyword = gr.keyword
            )
            AND gr.evidence_status='verified'
            AND gr.score_version IS NOT NULL
            AND gr.composite_gap_score IS NOT NULL
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
