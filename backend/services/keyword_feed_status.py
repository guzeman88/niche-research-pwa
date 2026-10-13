"""Read-only, private feed visibility; never expose filesystem paths or secrets."""
from datetime import date, timedelta
import json


def status():
    from services.product_validation import db_path
    path = db_path().parent / "feed-status.json"
    if not path.exists():
        return {"status": "not_installed", "last_attempt": None, "sources": []}
    try:
        if path.stat().st_size > 2_000_000:
            raise ValueError("Oversized status")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {"status": payload.get("status", "unknown"), "last_attempt": payload.get("started_at"),
            "last_completed": payload.get("completed_at"), "errors": payload.get("errors", []),
            "last_success": payload.get("last_success"),
            "bulk": {key: payload.get("bulk", {}).get(key) for key in ("status", "keywords_scanned", "mirror")},
            "coverage": _coverage(payload.get('bulk', {}).get('coverage', {})),
            "bridge": {key: payload.get('bulk', {}).get('bridge', {}).get(key) for key in ('status', 'imported_rows', 'pending_rows')},
            "marketplace_plan": {**{key: payload.get('marketplace_plan', {}).get(key) for key in ('status', 'weekly_free_limit')},
                'suggestions': [{key: row.get(key) for key in ('keyword', 'lane')} for row in payload.get('marketplace_plan', {}).get('suggestions', [])]},
            "google": [{key: row.get(key) for key in ("status", "run_id", "keywords")} for row in payload.get("google", [])],
            "etsy_demand_waiting": len(payload.get("etsy_demand_queue", []))}
    except (OSError, ValueError, TypeError, AttributeError):
        return {"status": "unreadable", "last_attempt": None, "errors": ["Feed status unavailable; saved evidence remains intact"]}


def _coverage(value):
    return {**{key: value.get(key) for key in ('window', 'as_of', 'library_keywords', 'active_keywords', 'exploration_keywords')},
        'providers': [{key: row.get(key) for key in ('provider', 'attempts', 'unique_keywords', 'useful_attempts', 'empty_attempts', 'failed_attempts', 'repeated_attempts', 'entries')} for row in value.get('providers', [])],
        'candidate_preview': [{key: row.get(key) for key in ('keyword', 'competition_sample_current', 'google_demand_measured')} for row in value.get('candidate_preview', [])]}


def freshness(rows, keyword):
    samples = [r["payload"] for r in rows if r["kind"] == "competitors" and r["payload"].get("keyword") == keyword and r["payload"].get("source") == "etsy_open_api"]
    market = [r["payload"] for r in rows if r["kind"] == "market" and r["payload"].get("keyword") == keyword]
    google = [r["payload"] for r in rows if r["kind"] == "google" and any(keyword in s.get("matched_queue_keywords", []) for s in r["payload"].get("signals", []))]
    result = []
    for source, values, field, cadence in (
        ("Etsy competition", samples, "observed_at", 7),
        ("Etsy buyer demand", market, "period_end", 7),
        ("Google demand", google, "collected_at", 28),
    ):
        usable = []
        for value in values:
            try:
                observed = date.fromisoformat(str(value[field])[:10])
                if observed <= date.today():
                    usable.append((observed, value))
            except (ValueError, KeyError, TypeError):
                continue
        latest, payload = max(usable, key=lambda pair: pair[0], default=(None, {}))
        due = latest + timedelta(days=cadence) if latest else None
        result.append({"source": source, "last_observed": latest.isoformat() if latest else None,
            "next_due": due.isoformat() if due else None,
            "status": "missing" if latest is None else "due" if due <= date.today() else "current",
            "period_start": payload.get("period_start"), "period_end": payload.get("period_end"),
            "observations": len(values)})
    return result
