"""Best-effort durable sync for one completed keyword-evidence collection run."""
from __future__ import annotations

import json
import os
from typing import Any

import httpx


def is_configured() -> bool:
    return bool(
        os.getenv("SUPABASE_URL", "").strip()
        and os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )


def sync_collection_run(run_id: str) -> dict:
    """Upsert one run and all linked raw evidence; never invent missing rows."""
    from pipeline import keyword_database as kdb

    if not is_configured():
        kdb.mark_evidence_collection_sync(run_id, "not_configured")
        return {"configured": False, "status": "not_configured"}

    try:
        payloads = _payloads(run_id)
        for table, conflict in (
            ("keyword_seeds", "keyword"),
            ("evidence_collection_runs", "id"),
            ("keyword_sources", "keyword,source"),
            ("keyword_observations", "keyword,source,observed_at,metric"),
            ("keyword_suggestions", "source_suggestion_id"),
            ("keyword_trend_points", "source_trend_point_id"),
            ("keyword_listing_snapshots", "source_listing_snapshot_id"),
        ):
            _upsert(table, conflict, payloads[table])
        kdb.mark_evidence_collection_sync(run_id, "synced")
        _upsert("evidence_collection_runs", "id", _payloads(run_id)["evidence_collection_runs"])
        return {
            "configured": True,
            "status": "synced",
            "rows": {table: len(rows) for table, rows in payloads.items()},
        }
    except Exception as exc:
        kdb.mark_evidence_collection_sync(run_id, "failed", str(exc))
        return {"configured": True, "status": "failed", "error": str(exc)}


def _payloads(run_id: str) -> dict[str, list[dict[str, Any]]]:
    from pipeline import keyword_database as kdb

    with kdb._conn() as con:
        observations = [dict(row) for row in con.execute(
            "SELECT * FROM keyword_observations WHERE collection_run_id=?", (run_id,)
        ).fetchall()]
        suggestions = [dict(row) for row in con.execute(
            "SELECT * FROM keyword_suggestions WHERE collection_run_id=?", (run_id,)
        ).fetchall()]
        trends = [dict(row) for row in con.execute(
            "SELECT * FROM keyword_trend_points WHERE collection_run_id=?", (run_id,)
        ).fetchall()]
        listings = [dict(row) for row in con.execute(
            "SELECT * FROM keyword_listing_snapshots WHERE collection_run_id=?", (run_id,)
        ).fetchall()]
        run = con.execute("SELECT * FROM evidence_collection_runs WHERE id=?", (run_id,)).fetchone()
        keywords = {
            *(row["keyword"] for row in observations),
            *(row["parent_keyword"] for row in suggestions),
            *(row["suggestion"] for row in suggestions),
            *(row["keyword"] for row in trends),
            *(row["keyword"] for row in listings),
        }
        if keywords:
            placeholders = ",".join("?" for _ in keywords)
            values = sorted(keywords)
            seeds = [dict(row) for row in con.execute(
                f"SELECT * FROM seeds WHERE keyword IN ({placeholders})", values
            ).fetchall()]
            sources = [dict(row) for row in con.execute(
                f"SELECT * FROM keyword_sources WHERE keyword IN ({placeholders})", values
            ).fetchall()]
        else:
            seeds, sources = [], []
    return {
        "keyword_seeds": [{
            "keyword": row["keyword"], "domain": row["domain"], "source": row["source"],
            "added_at": row["added_at"],
        } for row in seeds],
        "evidence_collection_runs": [_run_row(dict(run))] if run else [],
        "keyword_sources": [{
            "keyword": row["keyword"], "source": row["source"],
            "first_seen_at": row["first_seen_at"], "last_seen_at": row["last_seen_at"],
            "observation_count": row["observation_count"], "metadata": None,
        } for row in sources],
        "keyword_observations": [_observation_row(row) for row in observations],
        "keyword_suggestions": [_suggestion_row(row) for row in suggestions],
        "keyword_trend_points": [_trend_row(row) for row in trends],
        "keyword_listing_snapshots": [_listing_row(row) for row in listings],
    }


def _run_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"], "source": row["source"], "started_at": row["started_at"],
        "completed_at": row.get("completed_at"), "status": row["status"],
        "request": _json(row.get("request_json")),
        "observation_count": row.get("observation_count") or 0, "error": row.get("error"),
        "durable_sync_status": row.get("durable_sync_status") or "pending",
        "durable_synced_at": row.get("durable_synced_at"),
        "durable_sync_error": row.get("durable_sync_error"),
    }


def _observation_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row.get(key) for key in (
            "keyword", "source", "observed_at", "metric", "value", "unit", "sample_size",
            "geography", "period_start", "period_end", "provider_record_id", "collection_run_id",
        )
    } | {"metadata": _json(row.get("metadata_json"))}


def _suggestion_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_suggestion_id": row["id"], "parent_keyword": row["parent_keyword"],
        "suggestion": row["suggestion"], "source": row["source"], "query": row["query"],
        "position": row["position"], "observed_at": row["observed_at"],
        "geography": row.get("geography"), "collection_run_id": row.get("collection_run_id"),
        "metadata": _json(row.get("metadata_json")),
    }


def _trend_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_trend_point_id": row["id"], "keyword": row["keyword"], "source": row["source"],
        "point_at": row["point_at"], "value": row["value"], "unit": row["unit"],
        "geography": row.get("geography"), "timeframe": row.get("timeframe"),
        "is_partial": None if row.get("is_partial") is None else bool(row["is_partial"]),
        "collected_at": row["collected_at"], "collection_run_id": row.get("collection_run_id"),
        "metadata": _json(row.get("metadata_json")),
    }


def _listing_row(row: dict[str, Any]) -> dict[str, Any]:
    result = {key: row.get(key) for key in (
        "keyword", "source", "observed_at", "listing_id", "title", "shop_name", "url",
        "price", "currency_code", "favorites", "review_count", "position", "collection_run_id",
    )}
    result.update({
        "source_listing_snapshot_id": row["id"],
        "is_star_seller": None if row.get("is_star_seller") is None else bool(row["is_star_seller"]),
        "is_bestseller": None if row.get("is_bestseller") is None else bool(row["is_bestseller"]),
        "metadata": _json(row.get("metadata_json")),
    })
    return result


def _upsert(table: str, conflict: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    response = httpx.post(
        f"{url}/rest/v1/{table}",
        params={"on_conflict": conflict},
        headers={
            "apikey": key, "authorization": f"Bearer {key}",
            "content-type": "application/json",
            "prefer": "resolution=merge-duplicates,return=minimal",
        },
        content=json.dumps(rows),
        timeout=30,
    )
    response.raise_for_status()


def _json(value: Any) -> Any:
    if value is None or isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
