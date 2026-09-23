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
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Paths resolved relative to the backend/ directory
import os as _os
_BACKEND_DIR = Path(_os.environ.get("BACKEND_DIR", Path(__file__).parent.parent.resolve()))
DB_PATH = _BACKEND_DIR / "workspace/_keyword_db/keywords.sqlite"
SEED_PATH = _BACKEND_DIR / "config/seed_keywords.json"
SEED_DB_PATH = _BACKEND_DIR / "seed_data/_keyword_db/keywords.sqlite"
SCHEMA_VERSION = 17


# ── Connection ────────────────────────────────────────────────────────────────

class _ClosingConnection(sqlite3.Connection):
    """Commit or roll back, then release the file handle after every context."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30, factory=_ClosingConnection)
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
            added_at    TEXT NOT NULL
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
            score_delta             REAL,
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
        ("score_delta",         "REAL"),
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
            volume_gap_score            REAL,
            quality_gap_score           REAL,
            tag_gap_score               REAL,
            style_gap_score             REAL,
            price_gap_score             REAL,
            recency_gap_score           REAL,
            composite_gap_score         REAL,
            entry_angle                 TEXT DEFAULT '',
            recommended_price_min       REAL,
            recommended_price_max       REAL,
            untagged_searches_json      TEXT DEFAULT '[]',
            dominant_competitor_tags_json TEXT DEFAULT '[]',
            recommended_tags_json       TEXT DEFAULT '[]',
            listings_analyzed           INTEGER DEFAULT 0,
            avg_listing_age_months      REAL
        );

        CREATE INDEX IF NOT EXISTS idx_gap_reports_keyword ON gap_reports(keyword);
        CREATE INDEX IF NOT EXISTS idx_gap_reports_composite ON gap_reports(composite_gap_score DESC);
    """)


def _migrate_v5(con: sqlite3.Connection) -> None:
    """Add profit and buyer-intent signals to full gap reports."""
    for col, typedef in [
        ("buyer_intent_score", "REAL"),
        ("profit_gap_score", "REAL"),
    ]:
        try:
            con.execute(f"ALTER TABLE gap_reports ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass


def _migrate_v6(con: sqlite3.Connection) -> None:
    """Add deeper profitability and market-evidence fields."""
    scan_cols = [
        ("price_min_usd", "REAL"),
        ("price_p25_usd", "REAL"),
        ("price_median_usd", "REAL"),
        ("price_p75_usd", "REAL"),
        ("price_max_usd", "REAL"),
        ("avg_favorites", "REAL"),
        ("max_favorites", "INTEGER"),
        ("pct_high_favorites", "REAL"),
        ("pct_star_sellers", "REAL"),
        ("pct_bestsellers", "REAL"),
        ("revenue_per_listing", "REAL"),
        ("market_evidence_score", "REAL"),
        ("profitability_index", "REAL"),
    ]
    gap_cols = [
        ("price_p25_usd", "REAL"),
        ("price_median_usd", "REAL"),
        ("price_p75_usd", "REAL"),
        ("avg_favorites", "REAL"),
        ("pct_high_favorites", "REAL"),
        ("pct_star_sellers", "REAL"),
        ("pct_bestsellers", "REAL"),
        ("revenue_per_listing", "REAL"),
        ("market_evidence_score", "REAL"),
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
        if version < 11:
            _migrate_v11(con)
            _set_version(con, 11)
        if version < 12:
            _migrate_v12(con)
            _set_version(con, 12)
        if version < 13:
            _migrate_v13(con)
            _set_version(con, 13)
        if version < 14:
            _migrate_v14(con)
            _set_version(con, 14)
        if version < 15:
            _migrate_v15(con)
            _set_version(con, 15)
        if version < 16:
            _migrate_v16(con)
            _set_version(con, 16)
        if version < 17:
            _migrate_v17(con)
            _set_version(con, 17)
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

    # A retained score must prove that it came from actual observations. No
    # global sample-size cutoff is imposed here; model-specific validation must
    # be declared by the versioned scoring model that produced the score.
    con.execute("""
        DELETE FROM gap_reports
        WHERE COALESCE(listings_analyzed, 0) <= 0
           OR COALESCE(market_evidence_score, 0) <= 0
    """)
    con.execute("""
        DELETE FROM scans
        WHERE COALESCE(sampled_listing_count, 0) <= 0
           OR COALESCE(listing_count, 0) <= 0
           OR COALESCE(avg_price_usd, 0) <= 0
           OR COALESCE(market_evidence_score, 0) <= 0
    """)
    con.execute("""
        DELETE FROM gap_scores
        WHERE NOT EXISTS (
            SELECT 1 FROM scans
            WHERE scans.keyword=gap_scores.keyword
              AND scans.evidence_status='verified'
        )
    """)
    con.execute("DELETE FROM scheduler_log")


def _migrate_v11(con: sqlite3.Connection) -> None:
    """Clear legacy derived values that have no accepted score provenance."""
    con.execute("""
        UPDATE scans
        SET opportunity_score=NULL,
            demand_score=NULL,
            competition_score=NULL,
            margin_score=NULL,
            trend_score=NULL,
            monthly_revenue_usd=NULL,
            competition_quality=NULL,
            gap_score=NULL,
            listing_efficiency=NULL,
            score_delta=NULL,
            trajectory=NULL,
            revenue_per_listing=NULL,
            market_evidence_score=NULL,
            profitability_index=NULL
        WHERE score_version IS NULL OR evidence_status != 'verified'
    """)
    con.execute("""
        UPDATE gap_reports
        SET volume_gap_score=NULL,
            quality_gap_score=NULL,
            tag_gap_score=NULL,
            style_gap_score=NULL,
            price_gap_score=NULL,
            recency_gap_score=NULL,
            buyer_intent_score=NULL,
            profit_gap_score=NULL,
            composite_gap_score=NULL,
            recommended_price_min=NULL,
            recommended_price_max=NULL,
            revenue_per_listing=NULL,
            market_evidence_score=NULL
        WHERE score_version IS NULL OR evidence_status != 'verified'
    """)
    con.execute("DELETE FROM gap_scores")


def _migrate_v12(con: sqlite3.Connection) -> None:
    """Remove the legacy arbitrary definition of a high-favorite listing."""
    con.execute("UPDATE scans SET pct_high_favorites=NULL")
    con.execute("UPDATE gap_reports SET pct_high_favorites=NULL")


def _migrate_v13(con: sqlite3.Connection) -> None:
    """Remove hand-assigned seed priorities from storage and scheduling."""
    columns = {row[1] for row in con.execute("PRAGMA table_info(seeds)").fetchall()}
    if "priority" in columns:
        con.execute("ALTER TABLE seeds DROP COLUMN priority")


def _migrate_v14(con: sqlite3.Connection) -> None:
    """Preserve source-level evidence instead of only report aggregates."""
    for col, typedef in [
        ("geography", "TEXT"),
        ("period_start", "TEXT"),
        ("period_end", "TEXT"),
        ("provider_record_id", "TEXT"),
        ("collection_run_id", "TEXT"),
    ]:
        try:
            con.execute(f"ALTER TABLE keyword_observations ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass

    con.executescript("""
        CREATE TABLE IF NOT EXISTS evidence_collection_runs (
            id                  TEXT PRIMARY KEY,
            source              TEXT NOT NULL,
            started_at          TEXT NOT NULL,
            completed_at        TEXT,
            status              TEXT NOT NULL,
            request_json        TEXT,
            observation_count   INTEGER NOT NULL DEFAULT 0,
            error               TEXT
        );

        CREATE TABLE IF NOT EXISTS keyword_suggestions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_keyword      TEXT NOT NULL,
            suggestion          TEXT NOT NULL,
            source              TEXT NOT NULL,
            query               TEXT NOT NULL,
            position            INTEGER NOT NULL,
            observed_at         TEXT NOT NULL,
            geography           TEXT,
            collection_run_id   TEXT,
            metadata_json       TEXT,
            UNIQUE(parent_keyword, suggestion, source, query, observed_at),
            FOREIGN KEY (parent_keyword) REFERENCES seeds(keyword) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS keyword_trend_points (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword             TEXT NOT NULL,
            source              TEXT NOT NULL,
            point_at            TEXT NOT NULL,
            value               REAL NOT NULL,
            unit                TEXT NOT NULL,
            geography           TEXT,
            timeframe           TEXT,
            is_partial          INTEGER,
            collected_at        TEXT NOT NULL,
            collection_run_id   TEXT,
            metadata_json       TEXT,
            UNIQUE(keyword, source, point_at, geography, timeframe, collected_at),
            FOREIGN KEY (keyword) REFERENCES seeds(keyword) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS keyword_listing_snapshots (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword             TEXT NOT NULL,
            source              TEXT NOT NULL,
            observed_at         TEXT NOT NULL,
            listing_id          TEXT NOT NULL,
            title               TEXT,
            shop_name           TEXT,
            url                 TEXT,
            price               REAL,
            currency_code       TEXT,
            favorites           INTEGER,
            review_count        INTEGER,
            is_star_seller      INTEGER,
            is_bestseller       INTEGER,
            position            INTEGER,
            collection_run_id   TEXT,
            metadata_json       TEXT,
            UNIQUE(keyword, source, observed_at, listing_id),
            FOREIGN KEY (keyword) REFERENCES seeds(keyword) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_collection_runs_started
            ON evidence_collection_runs(started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_keyword_suggestions_parent
            ON keyword_suggestions(parent_keyword, observed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_keyword_trends_lookup
            ON keyword_trend_points(keyword, point_at DESC);
        CREATE INDEX IF NOT EXISTS idx_keyword_listing_snapshots_lookup
            ON keyword_listing_snapshots(keyword, observed_at DESC);
    """)


def _migrate_v15(con: sqlite3.Connection) -> None:
    """Track whether a collection run has reached durable cloud storage."""
    for col, typedef in [
        ("durable_sync_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("durable_synced_at", "TEXT"),
        ("durable_sync_error", "TEXT"),
    ]:
        try:
            con.execute(f"ALTER TABLE evidence_collection_runs ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass


def _migrate_v16(con: sqlite3.Connection) -> None:
    """Persist latest collection progress independently of process-local scans."""
    con.executescript("""
        CREATE TABLE IF NOT EXISTS keyword_collection_state (
            keyword                 TEXT PRIMARY KEY REFERENCES seeds(keyword) ON DELETE CASCADE,
            last_collected_at       TEXT NOT NULL,
            evidence_status        TEXT NOT NULL,
            listing_count          INTEGER,
            sampled_listing_count  INTEGER,
            avg_price_usd           REAL,
            sources_json            TEXT NOT NULL,
            last_run_id             TEXT,
            updated_at              TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_keyword_collection_state_oldest
            ON keyword_collection_state(last_collected_at ASC);
    """)


def _migrate_v17(con: sqlite3.Connection) -> None:
    """Track provider-specific refresh work without inventing evidence values."""
    con.executescript("""
        CREATE TABLE IF NOT EXISTS provider_keyword_state (
            provider                TEXT NOT NULL,
            keyword                 TEXT NOT NULL REFERENCES seeds(keyword) ON DELETE CASCADE,
            last_attempt_at         TEXT NOT NULL,
            last_success_at         TEXT,
            status                  TEXT NOT NULL,
            row_count               INTEGER NOT NULL DEFAULT 0,
            error                   TEXT,
            PRIMARY KEY (provider, keyword)
        );
        CREATE INDEX IF NOT EXISTS idx_provider_keyword_due
            ON provider_keyword_state(provider, last_attempt_at ASC);
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
            rows.append((kw.strip().lower(), domain, "library", now))
    with _conn() as con:
        cur = con.executemany(
            "INSERT OR IGNORE INTO seeds (keyword, domain, source, added_at) VALUES (?,?,?,?)",
            rows,
        )
        con.executemany("""
            INSERT OR IGNORE INTO keyword_sources
                (keyword, source, first_seen_at, last_seen_at, observation_count)
            VALUES (?, 'library', ?, ?, 1)
        """, [(keyword, now, now) for keyword, _domain, _source, _added in rows])
        return cur.rowcount


def add_seed(keyword: str, domain: str = "discovered", source: str = "auto") -> bool:
    """Add an unranked discovery candidate."""
    now = datetime.utcnow().isoformat()
    normalized = keyword.strip().lower()
    with _conn() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO seeds (keyword, domain, source, added_at) VALUES (?,?,?,?)",
            (normalized, domain, source, now),
        )
        con.execute("""
            INSERT INTO keyword_sources
                (keyword, source, first_seen_at, last_seen_at, observation_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(keyword, source) DO UPDATE SET
                last_seen_at=excluded.last_seen_at,
                observation_count=keyword_sources.observation_count + 1
        """, (normalized, source, now, now))
        return cur.rowcount > 0


def add_seeds_bulk(keywords: list[str], domain: str = "discovered", source: str = "auto") -> int:
    """Add unranked discovery candidates."""
    now = datetime.utcnow().isoformat()
    rows = [(kw.strip().lower(), domain, source, now)
            for kw in keywords if kw.strip()]
    if not rows:
        return 0
    with _conn() as con:
        cur = con.executemany(
            "INSERT OR IGNORE INTO seeds (keyword, domain, source, added_at) VALUES (?,?,?,?)",
            rows,
        )
        con.executemany("""
            INSERT INTO keyword_sources
                (keyword, source, first_seen_at, last_seen_at, observation_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(keyword, source) DO UPDATE SET
                last_seen_at=excluded.last_seen_at,
                observation_count=keyword_sources.observation_count + 1
        """, [(keyword, source, now, now) for keyword, _domain, _source, _added in rows])
        return cur.rowcount


def merge_remote_collection_state(
    seeds: list[dict],
    states: list[dict],
) -> tuple[int, int]:
    """Merge durable Supabase seed/progress rows without inflating source counts."""
    now = datetime.utcnow().isoformat()
    seed_rows = [
        (
            str(row.get("keyword") or "").strip().lower(),
            str(row.get("domain") or "discovered"),
            str(row.get("source") or "cloud_sync"),
            str(row.get("added_at") or now),
        )
        for row in seeds
        if str(row.get("keyword") or "").strip()
    ]
    state_rows = [
        (
            str(row.get("keyword") or "").strip().lower(),
            str(row.get("last_collected_at") or ""),
            str(row.get("evidence_status") or "unverified"),
            row.get("listing_count"),
            row.get("sampled_listing_count"),
            row.get("avg_price_usd"),
            json.dumps(row.get("sources") or []),
            row.get("last_run_id"),
            str(row.get("updated_at") or now),
        )
        for row in states
        if str(row.get("keyword") or "").strip() and row.get("last_collected_at")
    ]
    with _conn() as con:
        before_seeds = int(con.execute("SELECT COUNT(*) FROM seeds").fetchone()[0] or 0)
        before_states = int(con.execute(
            "SELECT COUNT(*) FROM keyword_collection_state"
        ).fetchone()[0] or 0)
        con.executemany(
            "INSERT OR IGNORE INTO seeds(keyword, domain, source, added_at) VALUES (?,?,?,?)",
            seed_rows,
        )
        con.executemany("""
            INSERT OR IGNORE INTO keyword_sources
                (keyword, source, first_seen_at, last_seen_at, observation_count)
            VALUES (?, ?, ?, ?, 1)
        """, [
            (keyword, source, added_at, added_at)
            for keyword, _domain, source, added_at in seed_rows
        ])
        con.executemany("""
            INSERT INTO keyword_collection_state
                (keyword, last_collected_at, evidence_status, listing_count,
                 sampled_listing_count, avg_price_usd, sources_json, last_run_id, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(keyword) DO UPDATE SET
                last_collected_at=excluded.last_collected_at,
                evidence_status=excluded.evidence_status,
                listing_count=excluded.listing_count,
                sampled_listing_count=excluded.sampled_listing_count,
                avg_price_usd=excluded.avg_price_usd,
                sources_json=excluded.sources_json,
                last_run_id=excluded.last_run_id,
                updated_at=excluded.updated_at
            WHERE excluded.last_collected_at > keyword_collection_state.last_collected_at
        """, state_rows)
        after_seeds = int(con.execute("SELECT COUNT(*) FROM seeds").fetchone()[0] or 0)
        after_states = int(con.execute(
            "SELECT COUNT(*) FROM keyword_collection_state"
        ).fetchone()[0] or 0)
    return after_seeds - before_seeds, after_states - before_states


# ── Evidence collection ──────────────────────────────────────────────────────

def start_evidence_collection(source: str, request: dict | None = None,
                              run_id: str | None = None) -> str:
    """Create a durable collection attempt before any provider work starts."""
    clean_source = source.strip().lower()
    if not clean_source:
        raise ValueError("collection source is required")
    identifier = run_id or f"ev_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute("""
            INSERT OR IGNORE INTO evidence_collection_runs
                (id, source, started_at, status, request_json)
            VALUES (?, ?, ?, 'running', ?)
        """, (identifier, clean_source, now, json.dumps(request or {}, sort_keys=True)))
    return identifier


def finish_evidence_collection(run_id: str, status: str,
                               observation_count: int = 0,
                               error: str | None = None) -> None:
    """Finalize a collection run without translating failure into evidence."""
    if status not in {"completed", "partial", "failed", "no_data"}:
        raise ValueError("invalid collection status")
    with _conn() as con:
        con.execute("""
            UPDATE evidence_collection_runs
            SET completed_at=?, status=?, observation_count=?, error=?
            WHERE id=?
        """, (
            datetime.now(timezone.utc).isoformat(), status,
            max(0, int(observation_count)), error, run_id,
        ))


def mark_evidence_collection_sync(run_id: str, status: str,
                                  error: str | None = None) -> None:
    """Record cloud durability separately from provider collection status."""
    if status not in {"synced", "failed", "not_configured", "pending"}:
        raise ValueError("invalid durable sync status")
    with _conn() as con:
        con.execute("""
            UPDATE evidence_collection_runs
            SET durable_sync_status=?, durable_synced_at=?, durable_sync_error=?
            WHERE id=?
        """, (
            status,
            datetime.now(timezone.utc).isoformat() if status == "synced" else None,
            error,
            run_id,
        ))


def record_keyword_observation(
    *,
    keyword: str,
    source: str,
    metric: str,
    value: float,
    unit: str,
    observed_at: str | None = None,
    sample_size: int | None = None,
    geography: str | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
    provider_record_id: str | None = None,
    collection_run_id: str | None = None,
    metadata: dict | None = None,
) -> int:
    """Store one exact provider value with enough context to audit it later."""
    normalized = keyword.strip().lower()
    clean_source = source.strip().lower()
    clean_metric = metric.strip().lower()
    clean_unit = unit.strip().lower()
    numeric = _present_number(value)
    if not all((normalized, clean_source, clean_metric, clean_unit)):
        raise ValueError("keyword, source, metric, and unit are required")
    if numeric is None:
        raise ValueError("observation value must be finite")
    if sample_size is not None and int(sample_size) < 0:
        raise ValueError("sample size must be non-negative")
    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    add_seed(normalized, source=clean_source)
    with _conn() as con:
        cur = con.execute("""
            INSERT OR REPLACE INTO keyword_observations
                (keyword, source, observed_at, metric, value, unit, sample_size,
                 metadata_json, geography, period_start, period_end,
                 provider_record_id, collection_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            normalized, clean_source, timestamp, clean_metric, numeric, clean_unit,
            sample_size, json.dumps(metadata, sort_keys=True) if metadata else None,
            geography, period_start, period_end, provider_record_id, collection_run_id,
        ))
        return int(cur.lastrowid)


def record_keyword_suggestions(
    parent_keyword: str,
    source: str,
    suggestions: list[dict],
    *,
    observed_at: str | None = None,
    geography: str | None = None,
    collection_run_id: str | None = None,
) -> int:
    """Store autocomplete results with their exact query and returned position."""
    parent = parent_keyword.strip().lower()
    clean_source = source.strip().lower()
    if not parent or not clean_source:
        raise ValueError("parent keyword and source are required")
    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    add_seed(parent, source=clean_source)
    rows = []
    child_keywords = []
    for item in suggestions:
        suggestion = str(item.get("suggestion") or item.get("keyword") or "").strip().lower()
        query = str(item.get("query") or parent).strip().lower()
        position = _present_int(item.get("position"))
        if not suggestion or position is None or position < 1:
            continue
        child_keywords.append(suggestion)
        rows.append((
            parent, suggestion, clean_source, query, position, timestamp,
            item.get("geography") or geography, collection_run_id,
            json.dumps(item.get("metadata"), sort_keys=True) if item.get("metadata") else None,
        ))
    if not rows:
        return 0
    add_seeds_bulk(child_keywords, source=f"discover_{clean_source}")
    with _conn() as con:
        before = con.total_changes
        con.executemany("""
            INSERT OR IGNORE INTO keyword_suggestions
                (parent_keyword, suggestion, source, query, position, observed_at,
                 geography, collection_run_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        return con.total_changes - before


def record_keyword_trend_points(
    keyword: str,
    source: str,
    points: list[dict],
    *,
    collected_at: str | None = None,
    geography: str | None = None,
    timeframe: str | None = None,
    collection_run_id: str | None = None,
    metadata: dict | None = None,
) -> int:
    """Store the full provider time series; never collapse it to a trend label."""
    normalized = keyword.strip().lower()
    clean_source = source.strip().lower()
    timestamp = collected_at or datetime.now(timezone.utc).isoformat()
    if not normalized or not clean_source:
        raise ValueError("keyword and source are required")
    add_seed(normalized, source=clean_source)
    rows = []
    for point in points:
        point_at = str(point.get("date") or point.get("point_at") or "").strip()
        value = _present_number(point.get("value"))
        if not point_at or value is None:
            continue
        partial = point.get("is_partial")
        rows.append((
            normalized, clean_source, point_at, value,
            str(point.get("unit") or "relative_interest_index").strip().lower(),
            point.get("geography") or geography,
            point.get("timeframe") or timeframe,
            None if partial is None else int(bool(partial)), timestamp,
            collection_run_id,
            json.dumps(metadata, sort_keys=True) if metadata else None,
        ))
    if not rows:
        return 0
    with _conn() as con:
        before = con.total_changes
        con.executemany("""
            INSERT OR IGNORE INTO keyword_trend_points
                (keyword, source, point_at, value, unit, geography, timeframe,
                 is_partial, collected_at, collection_run_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        return con.total_changes - before


def record_keyword_listing_snapshots(
    keyword: str,
    source: str,
    listings: list[dict],
    *,
    observed_at: str | None = None,
    collection_run_id: str | None = None,
) -> int:
    """Store individual listing observations so aggregate prices remain auditable."""
    normalized = keyword.strip().lower()
    clean_source = source.strip().lower()
    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    if not normalized or not clean_source:
        raise ValueError("keyword and source are required")
    add_seed(normalized, source=clean_source)
    rows = []
    for position, item in enumerate(listings, start=1):
        listing_id = str(item.get("listing_id") or "").strip()
        if not listing_id:
            continue
        price = _present_number(item.get("price") if item.get("price") is not None else item.get("price_usd"))
        rows.append((
            normalized, clean_source, timestamp, listing_id,
            str(item.get("title") or "").strip() or None,
            str(item.get("shop_name") or "").strip() or None,
            str(item.get("url") or "").strip() or None,
            price, str(item.get("currency_code") or "").strip().upper() or None,
            _present_int(item.get("favorites") if item.get("favorites") is not None else item.get("num_favorites")),
            _present_int(item.get("review_count")),
            None if item.get("is_star_seller") is None else int(bool(item.get("is_star_seller"))),
            None if item.get("is_bestseller") is None else int(bool(item.get("is_bestseller"))),
            _present_int(item.get("position")) or position, collection_run_id,
            json.dumps(item.get("metadata"), sort_keys=True) if item.get("metadata") else None,
        ))
    if not rows:
        return 0
    with _conn() as con:
        before = con.total_changes
        con.executemany("""
            INSERT OR IGNORE INTO keyword_listing_snapshots
                (keyword, source, observed_at, listing_id, title, shop_name, url,
                 price, currency_code, favorites, review_count, is_star_seller,
                 is_bestseller, position, collection_run_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        return con.total_changes - before


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

    return add_seeds_bulk([c.strip().lower() for c in children],
                          domain="discovered", source=f"expand_{source}")


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

def _contains_any_phrase(keyword: str, phrases: set[str]) -> bool:
    return any(phrase in keyword for phrase in phrases)


def is_scanworthy_seed(
    keyword: str,
    domain: str | None = None,
    source: str | None = None,
) -> bool:
    """Apply only explicit safety/noise exclusions; do not guess market quality."""
    del domain, source
    kw = " ".join(keyword.lower().split())
    if not kw:
        return False
    if _contains_any_phrase(kw, _IP_RISK_TERMS):
        return False
    return True


def _present_number(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _present_int(value) -> int | None:
    number = _present_number(value)
    return int(number) if number is not None and number.is_integer() else None


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
    volume_observations = [value for value in volume_observations if value is not None and value >= 0]
    relative_interest_observations = {
        source: [
            _present_number(item.get("relative_interest"))
            for item in signals
            if isinstance(item, dict)
            and str(item.get("keyword", "")).strip().lower() == normalized
            and str(item.get("source", "")).lower() == source
        ]
        for source in ("google_trends", "pinterest_trends")
    }
    relative_interest_observations = {
        source: [value for value in values if value is not None]
        for source, values in relative_interest_observations.items()
    }
    relative_interest_periods = {
        source: [
            str(item.get("relative_interest_period"))
            for item in signals
            if isinstance(item, dict)
            and str(item.get("keyword", "")).strip().lower() == normalized
            and str(item.get("source", "")).lower() == source
            and item.get("relative_interest_period")
        ]
        for source in ("google_trends", "pinterest_trends")
    }

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
            "google_trends_relative_interest": (
                relative_interest_observations["google_trends"][0]
                if len(relative_interest_observations["google_trends"]) == 1 else None
            ),
            "pinterest_relative_interest": (
                relative_interest_observations["pinterest_trends"][0]
                if len(relative_interest_observations["pinterest_trends"]) == 1 else None
            ),
            "google_trends_relative_interest_period": (
                relative_interest_periods["google_trends"][0]
                if len(relative_interest_periods["google_trends"]) == 1 else None
            ),
            "pinterest_relative_interest_period": (
                relative_interest_periods["pinterest_trends"][0]
                if len(relative_interest_periods["pinterest_trends"]) == 1 else None
            ),
        }

    return {
        "sampled_listings": _present_int(row.get("sampled_listing_count")),
        "listing_count": _present_int(
            row.get("listing_count")
            if row.get("listing_count") is not None
            else row.get("total_listing_count")
        ),
        "avg_price_usd": _present_number(row.get("avg_price_usd")),
        "price_min_usd": _present_number(row.get("price_min")),
        "price_p25_usd": _present_number(row.get("price_p25")),
        "price_median_usd": _present_number(row.get("price_median")),
        "price_p75_usd": _present_number(row.get("price_p75")),
        "price_max_usd": _present_number(row.get("price_max")),
        "avg_favorites": _present_number(row.get("avg_favorites")),
        "max_favorites": int(row["max_favorites"]) if row.get("max_favorites") is not None else None,
        # No global favorite-count threshold is treated as meaningful evidence.
        "pct_high_favorites": None,
        "pct_star_sellers": _present_number(row.get("pct_star_sellers")),
        "pct_bestsellers": _present_number(row.get("pct_bestsellers")),
        "observed_search_volume": volume_observations[0] if len(volume_observations) == 1 else None,
        "google_trends_relative_interest": (
            relative_interest_observations["google_trends"][0]
            if len(relative_interest_observations["google_trends"]) == 1 else None
        ),
        "pinterest_relative_interest": (
            relative_interest_observations["pinterest_trends"][0]
            if len(relative_interest_observations["pinterest_trends"]) == 1 else None
        ),
        "google_trends_relative_interest_period": (
            relative_interest_periods["google_trends"][0]
            if len(relative_interest_periods["google_trends"]) == 1 else None
        ),
        "pinterest_relative_interest_period": (
            relative_interest_periods["pinterest_trends"][0]
            if len(relative_interest_periods["pinterest_trends"]) == 1 else None
        ),
    }


def _classify_market_evidence(metrics: dict, scan_error: str | None = None) -> tuple[str, dict]:
    requirements = {
        "listing_sample": (metrics.get("sampled_listings") or 0) > 0,
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
                              metrics: dict, sources: list[str],
                              collection_run_id: str | None = None) -> None:
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
                (keyword, source, observed_at, metric, value, unit, sample_size,
                 metadata_json, collection_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """, (
            keyword, market_source, observed_at, metric, value, unit,
            sample_size, collection_run_id,
        ))


def _record_report_source_evidence(keyword: str, report: dict,
                                   collection_run_id: str | None) -> int:
    """Persist source-native signals, series, suggestions, and listing rows."""
    normalized = keyword.strip().lower()
    count = 0
    for signal in report.get("keyword_signals", []) or []:
        if not isinstance(signal, dict):
            continue
        source = str(signal.get("source") or "").strip().lower()
        signal_keyword = str(signal.get("keyword") or "").strip().lower()
        if not source or not signal_keyword:
            continue
        observed_at = signal.get("observed_at") or report.get("generated_at")
        geography = signal.get("geography")
        metadata = signal.get("metadata") if isinstance(signal.get("metadata"), dict) else None

        query = str(signal.get("query") or "").strip().lower()
        position = _present_int(signal.get("position"))
        if query and position is not None:
            count += record_keyword_suggestions(
                normalized, source,
                [{
                    "suggestion": signal_keyword,
                    "query": query,
                    "position": position,
                    "geography": geography,
                    "metadata": metadata,
                }],
                observed_at=observed_at,
                geography=geography,
                collection_run_id=collection_run_id,
            )

        if signal_keyword == normalized:
            definitions = (
                ("monthly_searches", "monthly_searches", "searches_per_month"),
                ("competition_score", "provider_competition", "provider_value"),
                ("avg_price_usd", "average_price", "usd"),
                ("relative_interest", "relative_interest", "provider_index"),
            )
            for key, metric, unit in definitions:
                value = _present_number(signal.get(key))
                if value is None:
                    continue
                record_keyword_observation(
                    keyword=normalized,
                    source=source,
                    metric=metric,
                    value=value,
                    unit=unit,
                    observed_at=observed_at,
                    geography=geography,
                    collection_run_id=collection_run_id,
                    metadata={
                        **(metadata or {}),
                        **({"timeframe": signal.get("relative_interest_period")}
                           if signal.get("relative_interest_period") else {}),
                    } or None,
                )
                count += 1

            provider_observations = (metadata or {}).get("observations")
            if isinstance(provider_observations, list):
                for observation_index, observation in enumerate(provider_observations):
                    if not isinstance(observation, dict):
                        continue
                    value = _present_number(observation.get("value"))
                    metric = str(observation.get("metric") or "").strip().lower()
                    unit = str(observation.get("unit") or "").strip().lower()
                    if value is None or not metric or not unit:
                        continue
                    record_keyword_observation(
                        keyword=normalized,
                        source=source,
                        metric=metric,
                        value=value,
                        unit=unit,
                        observed_at=observed_at,
                        geography=geography,
                        collection_run_id=collection_run_id,
                        metadata={
                            key: item for key, item in (metadata or {}).items()
                            if key != "observations" and (key != "posts" or observation_index == 0)
                        },
                    )
                    count += 1

        time_series = signal.get("time_series")
        if signal_keyword == normalized and isinstance(time_series, list):
            count += record_keyword_trend_points(
                normalized,
                source,
                time_series,
                collected_at=observed_at,
                geography=geography,
                timeframe=signal.get("relative_interest_period"),
                collection_run_id=collection_run_id,
                metadata=metadata,
            )

    market_source = next(
        (source for source in (report.get("sources_used") or [])
         if source in {"etsy_open_api", "etsy_search_scraper"}),
        "etsy_market",
    )
    for row in report.get("keyword_search_data", []) or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("keyword") or "").strip().lower() != normalized:
            continue
        listings = row.get("listing_samples")
        if isinstance(listings, list):
            count += record_keyword_listing_snapshots(
                normalized,
                market_source,
                listings,
                observed_at=report.get("generated_at"),
                collection_run_id=collection_run_id,
            )
    return count


def save_scan(keyword: str, report) -> None:
    add_seed(keyword, source="scan_created")

    if hasattr(report, "__dataclass_fields__"):
        import dataclasses
        r = dataclasses.asdict(report)
    else:
        r = dict(report)

    now = datetime.utcnow().isoformat()
    kw = keyword.strip().lower()
    report_id = str(r.get("report_id") or "").strip()
    collection_run_id = None
    if report_id:
        collection_run_id = start_evidence_collection(
            "multi_source_research",
            {"keyword": kw, "sources": r.get("sources_used") or []},
            run_id=f"{report_id}:{kw}",
        )

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
        con.execute("""
            INSERT INTO keyword_collection_state
                (keyword, last_collected_at, evidence_status, listing_count,
                 sampled_listing_count, avg_price_usd, sources_json, last_run_id, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(keyword) DO UPDATE SET
                last_collected_at=excluded.last_collected_at,
                evidence_status=excluded.evidence_status,
                listing_count=excluded.listing_count,
                sampled_listing_count=excluded.sampled_listing_count,
                avg_price_usd=excluded.avg_price_usd,
                sources_json=excluded.sources_json,
                last_run_id=excluded.last_run_id,
                updated_at=excluded.updated_at
        """, (
            kw, now, evidence_status, metrics.get("listing_count"),
            metrics.get("sampled_listings"), metrics.get("avg_price_usd"),
            json.dumps(sources), collection_run_id, now,
        ))
        _record_scan_observations(con, kw, now, metrics, sources, collection_run_id)

    if collection_run_id:
        try:
            detail_count = _record_report_source_evidence(kw, r, collection_run_id)
            aggregate_count = sum(
                1 for key in (
                    "listing_count", "sampled_listings", "avg_price_usd",
                    "price_p25_usd", "price_median_usd", "price_p75_usd",
                    "avg_favorites", "pct_star_sellers", "pct_bestsellers",
                ) if metrics.get(key) is not None
            )
            total = detail_count + aggregate_count
            finish_evidence_collection(
                collection_run_id,
                "completed" if total else "no_data",
                total,
            )
            from services.supabase_evidence_sync import sync_collection_run
            sync_collection_run(collection_run_id)
        except Exception as exc:
            finish_evidence_collection(collection_run_id, "partial", 0, str(exc))
            raise


def save_provider_signals(
    keyword: str,
    provider: str,
    signals: list,
    *,
    generated_at: str | None = None,
) -> int:
    """Persist source-native signals without replacing Etsy collection state.

    Secondary collectors use this path so a trend or community refresh cannot
    turn a previously verified marketplace scan back into an unverified one.
    """
    normalized = keyword.strip().lower()
    clean_provider = provider.strip().lower()
    if not normalized or not clean_provider:
        raise ValueError("keyword and provider are required")
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    signal_rows = []
    for signal in signals:
        if hasattr(signal, "__dataclass_fields__"):
            import dataclasses
            row = dataclasses.asdict(signal)
        else:
            row = dict(signal)
        if str(row.get("keyword") or "").strip().lower() == normalized:
            signal_rows.append(row)
    run_id = start_evidence_collection(
        clean_provider,
        {"keyword": normalized, "provider": clean_provider},
        run_id=f"{clean_provider}:{normalized}:{uuid.uuid4().hex}",
    )
    report = {
        "generated_at": timestamp,
        "sources_used": [clean_provider] if signal_rows else [],
        "keyword_signals": signal_rows,
        "keyword_search_data": [],
    }
    try:
        count = _record_report_source_evidence(normalized, report, run_id)
        finish_evidence_collection(run_id, "completed" if count else "no_data", count)
        try:
            from services.supabase_evidence_sync import sync_collection_run
            sync_collection_run(run_id)
        except Exception:
            # The local evidence remains valid and its run stays available for a
            # later durable sync attempt.
            pass
        return count
    except Exception as exc:
        finish_evidence_collection(run_id, "failed", 0, str(exc))
        raise


def provider_keywords_due(
    provider: str,
    keywords: list[str],
    *,
    stale_days: int,
) -> list[str]:
    """Return requested keywords that have no provider attempt in the refresh window."""
    init_db()
    normalized = list(dict.fromkeys(
        " ".join(str(keyword).lower().split())
        for keyword in keywords
        if str(keyword).strip()
    ))
    if not normalized:
        return []
    cutoff = (datetime.utcnow() - timedelta(days=max(1, int(stale_days)))).isoformat()
    placeholders = ",".join("?" for _ in normalized)
    with _conn() as con:
        rows = con.execute(
            f"""
            SELECT keyword, last_attempt_at FROM provider_keyword_state
            WHERE provider=? AND keyword IN ({placeholders})
            """,
            (provider.strip().lower(), *normalized),
        ).fetchall()
    attempted = {
        row["keyword"]
        for row in rows
        if row["last_attempt_at"] and row["last_attempt_at"] >= cutoff
    }
    return [keyword for keyword in normalized if keyword not in attempted]


def record_provider_keyword_attempt(
    provider: str,
    keyword: str,
    *,
    status: str,
    row_count: int,
    error: str | None = None,
    attempted_at: str | None = None,
) -> None:
    """Record provider work separately from market evidence and model scores."""
    init_db()
    normalized = " ".join(keyword.lower().split())
    clean_provider = provider.strip().lower()
    if not normalized or not clean_provider:
        return
    add_seed(normalized, source=f"provider_{clean_provider}")
    timestamp = attempted_at or datetime.now(timezone.utc).isoformat()
    success_at = timestamp if status in {"completed", "no_data", "unchanged"} else None
    with _conn() as con:
        con.execute("""
            INSERT INTO provider_keyword_state
                (provider, keyword, last_attempt_at, last_success_at, status, row_count, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, keyword) DO UPDATE SET
                last_attempt_at=excluded.last_attempt_at,
                last_success_at=COALESCE(excluded.last_success_at, provider_keyword_state.last_success_at),
                status=excluded.status,
                row_count=excluded.row_count,
                error=excluded.error
        """, (
            clean_provider, normalized, timestamp, success_at, status,
            max(0, int(row_count)), str(error)[:2000] if error else None,
        ))


def get_provider_keyword_coverage(provider: str, *, hours: int = 24) -> dict:
    """Return observed provider attempts; an absent denominator remains unknown."""
    init_db()
    cutoff = (datetime.utcnow() - timedelta(hours=max(1, int(hours)))).isoformat()
    with _conn() as con:
        row = con.execute("""
            SELECT COUNT(*) AS attempted,
                   SUM(CASE WHEN status IN ('completed','no_data','unchanged') THEN 1 ELSE 0 END) AS completed,
                   SUM(CASE WHEN row_count > 0 THEN 1 ELSE 0 END) AS with_data,
                   SUM(row_count) AS rows
            FROM provider_keyword_state
            WHERE provider=? AND last_attempt_at>=?
        """, (provider.strip().lower(), cutoff)).fetchone()
    return {
        "attempted": int(row["attempted"] or 0),
        "completed": int(row["completed"] or 0),
        "with_data": int(row["with_data"] or 0),
        "rows": int(row["rows"] or 0),
    }


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
                SELECT s.keyword, s.domain, s.source, s.added_at FROM seeds s
                WHERE s.domain=?
                  AND NOT EXISTS (SELECT 1 FROM keyword_collection_state cs WHERE cs.keyword=s.keyword)
                ORDER BY s.added_at ASC, s.keyword ASC LIMIT ?
            """, (domain, candidate_limit)).fetchall()
        return con.execute("""
            SELECT s.keyword, s.domain, s.source, s.added_at FROM seeds s
            WHERE NOT EXISTS (SELECT 1 FROM keyword_collection_state cs WHERE cs.keyword=s.keyword)
            ORDER BY s.added_at ASC, s.keyword ASC LIMIT ?
        """, (candidate_limit,)).fetchall()


def get_unscanned_portfolio(limit: int = 20, domain: Optional[str] = None) -> list[str]:
    """Return unranked candidates in deterministic discovery order."""
    rows = _unscanned_candidate_rows(domain, limit)
    return [row["keyword"] for row in rows]


def get_unscanned(limit: int = 20, domain: Optional[str] = None) -> list[str]:
    rows = _unscanned_candidate_rows(domain, limit)
    return [row["keyword"] for row in rows]


def get_stale(days: int = 30, limit: int = 20, domain: Optional[str] = None) -> list[str]:
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    with _conn() as con:
        base = """
            SELECT s.keyword FROM seeds s
            JOIN keyword_collection_state latest ON latest.keyword=s.keyword
            WHERE latest.last_collected_at < ?
        """
        if domain:
            rows = con.execute(base + """
                AND s.domain=?
                ORDER BY latest.last_collected_at ASC
                LIMIT ?
            """,
                               (cutoff, domain, limit)).fetchall()
        else:
            rows = con.execute(base + """
                ORDER BY latest.last_collected_at ASC
                LIMIT ?
            """,
                               (cutoff, limit)).fetchall()
        return [r["keyword"] for r in rows]


def get_breakouts(limit: int = 20) -> list[str]:
    """No breakout is asserted until comparable, versioned observations exist."""
    return []


def get_profit_evidence_gaps(limit: int = 20, min_age_hours: int = 12) -> list[str]:
    """Old attempts missing one or more required market observations."""
    cutoff = (datetime.utcnow() - timedelta(hours=min_age_hours)).isoformat()
    with _conn() as con:
        rows = con.execute("""
            SELECT s.keyword
            FROM seeds s
            JOIN keyword_collection_state sc ON sc.keyword=s.keyword
            WHERE sc.last_collected_at < ?
              AND (
                sc.evidence_status != 'verified'
                OR sc.sampled_listing_count IS NULL
                OR sc.sampled_listing_count <= 0
                OR sc.avg_price_usd IS NULL
                OR sc.listing_count IS NULL
              )
            ORDER BY sc.last_collected_at ASC
            LIMIT ?
        """, (cutoff, limit)).fetchall()
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
        _add(get_unscanned_portfolio(limit=remaining))

    remaining = count - len(result)
    if remaining > 0:
        _add(get_unscanned(limit=remaining))

    remaining = count - len(result)
    if remaining > 0:
        _add(get_stale(days=stale_days, limit=remaining))
    remaining = count - len(result)
    if remaining > 0:
        _add(get_oldest_collected(limit=remaining))
    return result[:count]


def get_oldest_collected(limit: int = 20) -> list[str]:
    """Keep the collector cycling after every candidate has initial evidence."""
    with _conn() as con:
        rows = con.execute("""
            SELECT keyword FROM keyword_collection_state
            ORDER BY last_collected_at ASC, keyword ASC
            LIMIT ?
        """, (limit,)).fetchall()
    return [row["keyword"] for row in rows]


def get_all_seeds_with_status(limit: int = 2000) -> list[dict]:
    """Return all seeds with scan status for the UI checklist."""
    with _conn() as con:
        rows = con.execute("""
            SELECT s.keyword, s.domain,
                   COALESCE((SELECT GROUP_CONCAT(ks.source, ', ')
                             FROM keyword_sources ks WHERE ks.keyword=s.keyword), s.source) AS source,
                   s.added_at,
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
                   sc.price_min_usd, sc.price_p25_usd, sc.price_median_usd,
                   sc.price_p75_usd, sc.price_max_usd, sc.avg_favorites,
                   sc.max_favorites, sc.pct_high_favorites, sc.pct_star_sellers,
                   sc.pct_bestsellers, sc.observed_search_volume,
                   sc.sampled_listing_count, sc.sources_used,
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
        scanned     = con.execute("SELECT COUNT(*) FROM keyword_collection_state").fetchone()[0]
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
            SUM(evidence_status != 'failed' AND (
                evidence_status IN ('partial','verified')
                OR sources_json NOT IN ('[]','','null')
            )) AS successful,
            SUM(evidence_status='verified') AS evidence_backed,
            SUM(evidence_status='failed') AS failed,
            SUM(evidence_status='unverified' AND sources_json IN ('[]','','null')) AS no_data,
            SUM(last_collected_at < ?) AS stale
            FROM keyword_collection_state
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
            SELECT s.keyword, s.domain, s.source, s.added_at,
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


def get_keyword_evidence(keyword: str, limit: int = 100) -> dict | None:
    """Return auditable evidence for one exact keyword without inferred values."""
    normalized = keyword.strip().lower()
    if not normalized:
        return None
    row_limit = max(1, min(int(limit), 500))
    with _conn() as con:
        seed = con.execute(
            "SELECT * FROM seeds WHERE keyword = ?",
            (normalized,),
        ).fetchone()
        if seed is None:
            return None
        latest_attempt = con.execute(
            "SELECT * FROM scans WHERE keyword = ? ORDER BY scanned_at DESC, id DESC LIMIT 1",
            (normalized,),
        ).fetchone()
        latest_verified = con.execute(
            """
            SELECT * FROM scans
            WHERE keyword = ? AND evidence_status = 'verified' AND score_version IS NOT NULL
            ORDER BY scanned_at DESC, id DESC LIMIT 1
            """,
            (normalized,),
        ).fetchone()
        sources = con.execute(
            "SELECT * FROM keyword_sources WHERE keyword = ? ORDER BY source",
            (normalized,),
        ).fetchall()
        observations = con.execute(
            """
            SELECT * FROM keyword_observations
            WHERE keyword = ? ORDER BY observed_at DESC, id DESC LIMIT ?
            """,
            (normalized, row_limit),
        ).fetchall()
        economics = con.execute(
            """
            SELECT * FROM keyword_product_economics
            WHERE keyword = ? ORDER BY observed_at DESC, id DESC LIMIT ?
            """,
            (normalized, row_limit),
        ).fetchall()
        outcomes = con.execute(
            """
            SELECT * FROM keyword_outcomes
            WHERE keyword = ? ORDER BY period_end DESC, id DESC LIMIT ?
            """,
            (normalized, row_limit),
        ).fetchall()
        suggestions = con.execute(
            """
            SELECT * FROM keyword_suggestions
            WHERE parent_keyword = ? ORDER BY observed_at DESC, position ASC LIMIT ?
            """,
            (normalized, row_limit),
        ).fetchall()
        trend_points = con.execute(
            """
            SELECT * FROM keyword_trend_points
            WHERE keyword = ? ORDER BY point_at DESC, id DESC LIMIT ?
            """,
            (normalized, row_limit),
        ).fetchall()
        listing_snapshots = con.execute(
            """
            SELECT * FROM keyword_listing_snapshots
            WHERE keyword = ? ORDER BY observed_at DESC, position ASC LIMIT ?
            """,
            (normalized, row_limit),
        ).fetchall()
        collection_runs = con.execute(
            """
            SELECT DISTINCT run.* FROM evidence_collection_runs run
            WHERE run.id IN (
                SELECT collection_run_id FROM keyword_observations WHERE keyword = ?
                UNION SELECT collection_run_id FROM keyword_trend_points WHERE keyword = ?
                UNION SELECT collection_run_id FROM keyword_listing_snapshots WHERE keyword = ?
                UNION SELECT collection_run_id FROM keyword_suggestions WHERE parent_keyword = ?
            )
            ORDER BY started_at DESC LIMIT ?
            """,
            (normalized, normalized, normalized, normalized, row_limit),
        ).fetchall()
    return {
        "keyword": normalized,
        "seed": dict(seed),
        "latest_attempt": dict(latest_attempt) if latest_attempt else None,
        "latest_verified_evidence": dict(latest_verified) if latest_verified else None,
        "sources": [dict(row) for row in sources],
        "observations": [dict(row) for row in observations],
        "product_economics": [dict(row) for row in economics],
        "outcomes": [dict(row) for row in outcomes],
        "suggestions": [dict(row) for row in suggestions],
        "trend_points": [dict(row) for row in trend_points],
        "listing_snapshots": [dict(row) for row in listing_snapshots],
        "collection_runs": [dict(row) for row in collection_runs],
    }


def get_evidence_coverage(run_limit: int = 20) -> dict:
    """Return factual coverage counts; no completeness score is synthesized."""
    recent_limit = max(1, min(int(run_limit), 100))
    with _conn() as con:
        total_keywords = int(con.execute("SELECT COUNT(*) FROM seeds").fetchone()[0] or 0)
        metrics = {
            row["metric"]: int(row["keyword_count"])
            for row in con.execute("""
                SELECT metric, COUNT(DISTINCT keyword) AS keyword_count
                FROM keyword_observations GROUP BY metric ORDER BY metric
            """).fetchall()
        }
        sources = [dict(row) for row in con.execute("""
            SELECT source,
                   COUNT(DISTINCT keyword) AS keywords,
                   COUNT(*) AS observations,
                   MAX(observed_at) AS latest_observation_at
            FROM keyword_observations
            GROUP BY source ORDER BY source
        """).fetchall()]
        suggestion_sources = [dict(row) for row in con.execute("""
            SELECT source,
                   COUNT(DISTINCT parent_keyword) AS parent_keywords,
                   COUNT(*) AS suggestions,
                   MAX(observed_at) AS latest_observation_at
            FROM keyword_suggestions
            GROUP BY source ORDER BY source
        """).fetchall()]
        coverage = {
            "candidate_keywords": total_keywords,
            "keywords_with_any_observation": int(con.execute(
                "SELECT COUNT(DISTINCT keyword) FROM keyword_observations"
            ).fetchone()[0] or 0),
            "keywords_with_demand": int(con.execute("""
                SELECT COUNT(DISTINCT keyword) FROM keyword_observations
                WHERE metric IN ('monthly_searches', 'searches_30d', 'searches')
            """).fetchone()[0] or 0),
            "keywords_with_supply": int(con.execute("""
                SELECT COUNT(DISTINCT keyword) FROM keyword_observations
                WHERE metric IN ('listing_count', 'competition_listings')
            """).fetchone()[0] or 0),
            "keywords_with_trend_series": int(con.execute(
                "SELECT COUNT(DISTINCT keyword) FROM keyword_trend_points"
            ).fetchone()[0] or 0),
            "keywords_with_listing_samples": int(con.execute(
                "SELECT COUNT(DISTINCT keyword) FROM keyword_listing_snapshots"
            ).fetchone()[0] or 0),
            "keywords_with_shop_outcomes": int(con.execute(
                "SELECT COUNT(DISTINCT keyword) FROM keyword_outcomes"
            ).fetchone()[0] or 0),
            "keywords_with_unit_economics": int(con.execute(
                "SELECT COUNT(DISTINCT keyword) FROM keyword_product_economics"
            ).fetchone()[0] or 0),
        }
        recent_runs = [dict(row) for row in con.execute("""
            SELECT * FROM evidence_collection_runs
            ORDER BY started_at DESC LIMIT ?
        """, (recent_limit,)).fetchall()]
    return {
        "coverage": coverage,
        "metrics": metrics,
        "observation_sources": sources,
        "suggestion_sources": suggestion_sources,
        "recent_runs": recent_runs,
        "durability": {
            "cloud_sync_configured": bool(
                _os.environ.get("SUPABASE_URL", "").strip()
                and _os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            ),
            "run_statuses": {
                row["durable_sync_status"]: int(row["run_count"])
                for row in _durability_rows()
            },
        },
    }


def _durability_rows() -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute("""
            SELECT durable_sync_status, COUNT(*) AS run_count
            FROM evidence_collection_runs GROUP BY durable_sync_status
        """).fetchall()


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
    evidence_status = "verified" if listings_analyzed > 0 else "unverified"
    accepted_score_version = (
        score_version if evidence_status == "verified" and composite_gap is not None else None
    )
    if accepted_score_version is None:
        volume_gap = None
        quality_gap = None
        tag_gap = None
        style_gap = None
        price_gap = None
        recency_gap = None
        buyer_intent = None
        profit_gap = None
        composite_gap = None
        market_evidence_score = None
    pct_high_favorites = None
    evidence_details = {
        "listings_analyzed": listings_analyzed,
        "score_available": accepted_score_version is not None,
        "missing": [] if listings_analyzed > 0 else ["listing_sample"],
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


def get_top_gap_reports(limit: int = 100) -> list[dict]:
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
            ORDER BY gr.composite_gap_score DESC
            LIMIT ?
        """, (limit,)).fetchall()
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
