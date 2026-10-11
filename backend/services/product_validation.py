"""Private, revisioned product validation. Missing evidence never becomes zero.

The local ledger is the authoritative writer. Supabase is a retryable mirror;
an unavailable mirror must never discard a successful local save.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import sqlite3
import uuid
import threading
from functools import wraps
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

MODEL_VERSION = "etgen-product-evidence-v1"
COST_FIELDS = ("production", "shipping", "packaging", "fees", "advertising", "refunds", "labor")
MAX_AGE_DAYS = 45
_writer_lock = threading.RLock()


def single_writer(action):
    @wraps(action)
    def locked(*args, **kwargs):
        with _writer_lock:
            return action(*args, **kwargs)
    return locked


def stamp():
    return datetime.now(timezone.utc).isoformat()


def today():
    return datetime.now(timezone.utc).date()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def db_path():
    from config import WORKSPACE
    return Path(os.environ.get("VALIDATION_DB_PATH", WORKSPACE / "_validation_db/validation.sqlite"))


def connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=FULL")
    con.executescript("""
      CREATE TABLE IF NOT EXISTS records (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, project_id TEXT NOT NULL,
        payload TEXT NOT NULL, fingerprint TEXT NOT NULL, updated_at TEXT NOT NULL,
        synced_fingerprint TEXT, sync_error TEXT);
      CREATE INDEX IF NOT EXISTS records_project ON records(project_id, kind);
      CREATE TABLE IF NOT EXISTS revisions (
        id INTEGER PRIMARY KEY, record_id TEXT NOT NULL, payload TEXT NOT NULL,
        fingerprint TEXT NOT NULL, saved_at TEXT NOT NULL,
        UNIQUE(record_id, fingerprint));
    """)
    return con


def records(project_id=None, kind=None):
    clauses, values = [], []
    for field, value in (("project_id", project_id), ("kind", kind)):
        if value is not None:
            clauses.append(field + "=?")
            values.append(value)
    con = connect()
    try:
        rows = con.execute("SELECT * FROM records" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY updated_at DESC,id", values).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"]), "sync_status": "synced" if row["synced_fingerprint"] == row["fingerprint"] else "pending"} for row in rows]
    finally:
        con.close()


@single_writer
def put(kind, project_id, payload, record_id=None):
    record_id = record_id or uuid.uuid4().hex
    fingerprint, now = digest(payload), stamp()
    encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
    con = connect()
    try:
        with con:
            con.execute("BEGIN IMMEDIATE")
            return write_record(con, record_id, kind, project_id, encoded, fingerprint, now)
    finally:
        con.close()


def write_record(con, record_id, kind, project_id, encoded, fingerprint, now):
    existing = con.execute("SELECT fingerprint,kind,project_id FROM records WHERE id=?", (record_id,)).fetchone()
    if existing and (existing["kind"] != kind or existing["project_id"] != project_id):
        raise ValueError("Record identity belongs to a different project or evidence type")
    if existing and existing["fingerprint"] == fingerprint:
        return {"id": record_id, "duplicate": True, "saved_locally": True}
    con.execute("INSERT OR IGNORE INTO revisions(record_id,payload,fingerprint,saved_at) VALUES(?,?,?,?)", (record_id, encoded, fingerprint, now))
    con.execute("""INSERT INTO records(id,kind,project_id,payload,fingerprint,updated_at)
        VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
        fingerprint=excluded.fingerprint,updated_at=excluded.updated_at,sync_error=NULL""",
        (record_id, kind, project_id, encoded, fingerprint, now))
    return {"id": record_id, "duplicate": False, "saved_locally": True}


@single_writer
def retry_sync(limit=100):
    """Bounded outbox replay; acknowledge only the exact transmitted revision."""
    url, key = os.getenv("SUPABASE_URL", "").rstrip("/"), os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    pending = [row for row in records() if row["sync_status"] == "pending"]
    if not url or not key:
        return {"configured": False, "synced": 0, "pending": len(pending)}
    failures, synced = 0, 0
    for row in pending[:min(max(int(limit), 1), 100)]:
        envelope = {k: row[k] for k in ("id", "kind", "project_id", "payload", "fingerprint", "updated_at")}
        try:
            response = httpx.post(url + "/rest/v1/product_validation_records", params={"on_conflict": "id"},
                headers={"apikey": key, "authorization": "Bearer " + key, "prefer": "resolution=merge-duplicates,return=minimal"}, json=envelope, timeout=5)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            con = connect()
            try:
                with con:
                    con.execute("UPDATE records SET sync_error=? WHERE id=? AND fingerprint=?", (type(exc).__name__, row["id"], row["fingerprint"]))
            finally:
                con.close()
            failures += 1
            break
        con = connect()
        try:
            with con:
                con.execute("UPDATE records SET synced_fingerprint=?,sync_error=NULL WHERE id=? AND fingerprint=?", (row["fingerprint"], row["id"], row["fingerprint"]))
            synced += 1
        finally:
            con.close()
    return {"configured": True, "synced": synced, "failed": failures, "pending": sum(row["sync_status"] == "pending" for row in records())}


def text(value, name):
    result = str(value or "").strip()
    if not result or len(result) > 300:
        raise ValueError(name + " is required (maximum 300 characters)")
    return result


def number(value, name, optional=False, integer=False):
    if optional and value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(name + " must be a non-negative number") from None
    if isinstance(value, bool) or not math.isfinite(result) or result < 0 or (integer and result != int(result)):
        raise ValueError(name + " must be a finite non-negative " + ("integer" if integer else "number"))
    return int(result) if integer else result


def day(value, name):
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(name + " must be a valid YYYY-MM-DD date") from None
    if parsed > today():
        raise ValueError(name + " cannot be in the future")
    return parsed.isoformat()


def period(data):
    start, end = day(data.get("period_start"), "period_start"), day(data.get("period_end"), "period_end")
    if start > end:
        raise ValueError("Reporting period ends before it starts")
    return start, end


def project(project_id):
    found = records(project_id, "project")
    if not found:
        raise ValueError("Product concept not found")
    return found[0]["payload"]


def create_project(data):
    if not isinstance(data.get("keywords"), list):
        raise ValueError("Keywords must be a list of buyer phrases")
    keywords = list(dict.fromkeys(" ".join(str(k).lower().split()) for k in data.get("keywords", []) if str(k).strip()))
    if not 1 <= len(keywords) <= 15 or any(len(k) > 200 for k in keywords):
        raise ValueError("Enter 1–15 distinct buyer keywords, at most 200 characters each")
    project_id = uuid.uuid4().hex
    payload = {"name": text(data.get("name"), "Product concept"), "product_type": text(data.get("product_type"), "Product type"), "keywords": keywords, "created_at": stamp()}
    put("project", project_id, payload, project_id)
    return {"id": project_id, **payload}


def save_market(project_id, data):
    concept = project(project_id)
    keyword = text(data.get("keyword"), "Keyword").lower()
    if keyword not in concept["keywords"]:
        raise ValueError("Keyword is outside this concept's validation queue")
    start, end = period(data)
    payload = {"keyword": keyword, "source": "etsy_marketplace_insights", "period_start": start, "period_end": end,
        "observed_at": day(data.get("observed_at"), "observed_at"), "searches": number(data.get("searches"), "Searches", integer=True),
        "listings": number(data.get("listings"), "Listings", integer=True), "geography": str(data.get("geography") or "unspecified"),
        "source_note": text(data.get("source_note"), "Source note")}
    if payload["observed_at"] < end:
        raise ValueError("Date recorded cannot precede the reporting period end")
    identity = digest([project_id, keyword, payload["source"], start, end, payload["geography"]])
    return put("market", project_id, payload, identity)


def save_competitors(project_id, data):
    concept = project(project_id)
    keyword = text(data.get("keyword"), "Keyword").lower()
    if keyword not in concept["keywords"]:
        raise ValueError("Keyword is outside this concept's validation queue")
    listings = data.get("listings") or []
    if not isinstance(listings, list) or not 1 <= len(listings) <= 100:
        raise ValueError("Provide 1–100 comparable listing samples")
    clean = {}
    for row in listings:
        if not isinstance(row, dict):
            raise ValueError("Each competitor sample must be a listing object")
        listing_id = text(row.get("listing_id"), "Listing ID")
        clean[listing_id] = {"listing_id": listing_id, "shop_id": text(row.get("shop_id"), "Shop ID"),
            "title": text(row.get("title"), "Listing title"), "price": number(row.get("price"), "Price"),
            "currency": text(row.get("currency"), "Currency").upper(), "shipping": number(row.get("shipping"), "Shipping", optional=True),
            "differentiation_note": str(row.get("differentiation_note") or "")[:1000]}
    observed = day(data.get("observed_at"), "observed_at")
    payload = {"keyword": keyword, "observed_at": observed, "source": text(data.get("source"), "Source"), "listings": list(clean.values()), "filters": str(data.get("filters") or "")[:1000]}
    payload["relevance_reviewed"] = data.get("relevance_reviewed") in (True, "on", "true")
    return put("competitors", project_id, payload, digest([project_id, keyword, observed, payload["source"]]))


def save_economics(project_id, data):
    project(project_id)
    payload = {"source": text(data.get("source"), "Cost source"), "observed_at": day(data.get("observed_at"), "observed_at"),
        "currency": text(data.get("currency"), "Currency").upper(), "scenarios": {}}
    for name in ("conservative", "base", "optimistic"):
        row = (data.get("scenarios") or {}).get(name)
        if not isinstance(row, dict):
            raise ValueError("Provide conservative, base and optimistic scenarios")
        payload["scenarios"][name] = {"price": number(row.get("price"), "Sale price"),
            **{field: number(row.get(field), field, optional=True) for field in COST_FIELDS},
            "setup": number(row.get("setup"), "Setup cost", optional=True),
            "fixed_monthly": number(row.get("fixed_monthly"), "Monthly fixed expenses", optional=True)}
        if payload["scenarios"][name]["price"] <= 0:
            raise ValueError("Sale price must be positive")
    return put("economics", project_id, payload)


def economics_summary(payload):
    result = {}
    for name, row in payload["scenarios"].items():
        missing = [field for field in COST_FIELDS if row[field] is None]
        margin = round(row["price"] - sum(row[field] for field in COST_FIELDS), 4) if not missing else None
        upfront = None if row["setup"] is None or row["fixed_monthly"] is None else row["setup"] + row["fixed_monthly"]
        result[name] = {**row, "missing": missing, "contribution_per_order": margin,
            "first_month_break_even_orders": math.ceil(upfront / margin) if margin is not None and margin > 0 and upfront is not None else None}
    return result


@single_writer
def save_outcome(project_id, data):
    project(project_id)
    start, end = period(data)
    payload = {"shop_id": text(data.get("shop_id"), "Shop ID"), "listing_id": text(data.get("listing_id"), "Listing ID"),
        "source": text(data.get("source"), "Outcome source"), "currency": text(data.get("currency"), "Currency").upper(),
        "period_start": start, "period_end": end,
        **{field: number(data.get(field), field, optional=True, integer=True) for field in ("impressions", "clicks", "visits", "orders")},
        "revenue": number(data.get("revenue"), "Revenue", optional=True),
        **{field: number(data.get(field), field, optional=True) for field in COST_FIELDS}}
    payload["setup_expenses"] = number(data.get("setup_expenses"), "Actual setup expenses", optional=True)
    payload["fixed_expenses"] = number(data.get("fixed_expenses"), "Actual fixed expenses", optional=True)
    identity = digest([payload["shop_id"], payload["listing_id"], start, end])
    # One listing/period belongs to one experiment, regardless of keyword/source.
    con = connect()
    try:
        with con:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute("SELECT project_id FROM records WHERE id=?", (identity,)).fetchone()
            if existing and existing["project_id"] != project_id:
                raise ValueError("This listing period is already attributed to another concept")
            for row in con.execute("SELECT id,payload FROM records WHERE kind='outcome'"):
                prior = json.loads(row["payload"])
                if row["id"] != identity and prior["shop_id"] == payload["shop_id"] and prior["listing_id"] == payload["listing_id"] and start <= prior["period_end"] and end >= prior["period_start"]:
                    raise ValueError("This reporting period overlaps an existing listing period; revise that record instead")
            return write_record(con, identity, "outcome", project_id, json.dumps(payload, sort_keys=True), digest(payload), stamp())
    finally:
        con.close()


def outcomes_summary(rows):
    if not rows:
        return {"status": "not_started", "periods": 0, "revenue": None, "contribution": None, "net_profit": None, "orders": None, "visits": None, "conversion_pct": None, "currencies": []}
    currencies = sorted({row["currency"] for row in rows})
    def total(field):
        return None if len(currencies) != 1 or any(row[field] is None for row in rows) else round(sum(row[field] for row in rows), 4)
    revenue, orders, visits = total("revenue"), total("orders"), total("visits")
    costs = [total(field) for field in COST_FIELDS]
    contribution = round(revenue - sum(costs), 4) if revenue is not None and all(value is not None for value in costs) else None
    setup, fixed = total("setup_expenses"), total("fixed_expenses")
    net = round(contribution - setup - fixed, 4) if contribution is not None and setup is not None and fixed is not None else None
    status = "inconclusive" if visits is None or visits < 100 or orders is None or contribution is None else "positive_contribution_test" if contribution > 0 and orders >= 3 else "review_test"
    return {"status": status, "periods": len(rows), "currencies": currencies, "revenue": revenue, "orders": orders, "visits": visits,
        "contribution": contribution, "net_profit": net, "conversion_pct": round(orders / visits * 100, 2) if visits and orders is not None else None,
        "notes": ["100 visits and 3 orders are initial review thresholds, not statistical proof.", "Contribution excludes setup and fixed expenses. Evaluate those separately."]}


def summary(project_id):
    concept = project(project_id)
    rows = records(project_id)
    market = [row["payload"] for row in rows if row["kind"] == "market"]
    samples = [row["payload"] for row in rows if row["kind"] == "competitors"]
    economics = next((row["payload"] for row in rows if row["kind"] == "economics"), None)
    costs = economics_summary(economics) if economics else None
    queue = []
    for keyword in concept["keywords"]:
        matches = [row for row in market if row["keyword"] == keyword]
        latest = max(matches, key=lambda row: (row["period_end"], row["observed_at"]), default=None)
        latest_samples = max((row for row in samples if row["keyword"] == keyword), key=lambda row: row["observed_at"], default=None)
        listing_count = len(latest_samples["listings"]) if latest_samples else 0
        market_age = (today() - date.fromisoformat(latest["period_end"])).days if latest else None
        sample_age = (today() - date.fromisoformat(latest_samples["observed_at"])).days if latest_samples else None
        blockers = []
        if not latest:
            blockers.append("Record Etsy searches and competing listings for a dated reporting period")
        elif market_age > MAX_AGE_DAYS:
            blockers.append("Refresh Etsy demand evidence")
        elif latest["searches"] == 0:
            blockers.append("No searches observed in this reporting period")
        if listing_count < 20:
            blockers.append("Collect 20 comparable competitor samples")
        elif sample_age > MAX_AGE_DAYS:
            blockers.append("Refresh competitor samples")
        if latest_samples and not latest_samples.get("relevance_reviewed"):
            blockers.append("Review competitor sample relevance")
        if latest_samples and economics and any(row["currency"] != economics["currency"] for row in latest_samples["listings"]):
            blockers.append("Review competitor currencies against the product pricing currency")
        if not costs or costs["conservative"]["contribution_per_order"] is None:
            blockers.append("Complete all conservative variable costs")
        elif costs["conservative"]["contribution_per_order"] <= 0:
            blockers.append("Conservative contribution must be positive")
        if not costs or costs["conservative"]["first_month_break_even_orders"] is None:
            blockers.append("Record setup and fixed expenses to calculate break-even")
        if economics and (today() - date.fromisoformat(economics["observed_at"])).days > MAX_AGE_DAYS:
            blockers.append("Refresh product cost evidence")
        queue.append({"keyword": keyword, "market": latest, "sample_count": listing_count, "sample_age_days": sample_age,
            "market_age_days": market_age, "status": "ready_to_test" if not blockers else "needs_evidence", "blockers": blockers,
            "distinct_sample_shops": len({row["shop_id"] for row in latest_samples["listings"]}) if latest_samples else 0})
    outcomes = outcomes_summary([row["payload"] for row in rows if row["kind"] == "outcome"])
    order_items = [row["payload"] for row in rows if row["kind"] == "order_item"]
    return {"id": project_id, **concept, "model_version": MODEL_VERSION, "queue": queue, "economics": costs,
        "economics_currency": economics["currency"] if economics else None, "outcomes": outcomes,
        "status": "ready_to_test" if any(row["status"] == "ready_to_test" for row in queue) else "needs_evidence",
        "order_reconciliation": {"items": len(order_items), "distinct_orders": len({(row["shop_id"], row["order_id"]) for row in order_items}),
            "notes": "Order items are reconciliation evidence; they are not added to listing-period totals again."},
        "sync_pending": sum(row["sync_status"] == "pending" for row in rows), "records": rows,
        "input_fingerprint": digest(sorted(row["fingerprint"] for row in rows)),
        "notes": ["Etsy demand and supply share a source and reporting period.", "Readiness is an evidence checklist, not a probability of profit.", "Google demand supports discovery; it is not Etsy purchase demand."]}


def export_ledger():
    con = connect()
    try:
        con.execute("BEGIN")
        revisions = [dict(row) for row in con.execute("SELECT * FROM revisions ORDER BY id")]
        rows = [{**dict(row), "payload": json.loads(row["payload"])} for row in con.execute("SELECT * FROM records ORDER BY id")]
    finally:
        con.close()
    payload = {"schema_version": 1, "model_version": MODEL_VERSION, "exported_at": stamp(), "records": rows, "revisions": revisions}
    return {"payload": payload, "sha256": digest(payload)}


@single_writer
def import_orders_csv(project_id, data, commit=False):
    """Import mapped order items without inventing a fee allocation or attribution.

    Mapping is explicit because Etsy's order/payment exports have different
    formats. Shop/order/transaction identity deduplicates across all concepts.
    """
    project(project_id)
    source = text(data.get("source"), "Source")
    shop = text(data.get("shop_id"), "Shop ID")
    rows = list(csv.DictReader(io.StringIO(str(data.get("text") or ""))))
    columns = data.get("columns") or {}
    required = ("order_id", "transaction_id", "listing_id", "date", "currency", "revenue")
    if not 1 <= len(rows) <= 1000:
        raise ValueError("Provide 1–1,000 order-item rows")
    if any(not columns.get(field) or columns[field] not in rows[0] for field in required):
        raise ValueError("Map order ID, transaction ID, listing ID, date, currency and retained revenue columns")
    con = connect()
    staged = {}
    try:
        con.execute("BEGIN IMMEDIATE")
        for raw in rows:
            item = {"shop_id": shop, "source": source,
                **{field: text(raw.get(columns[field]), field) for field in ("order_id", "transaction_id", "listing_id", "currency")},
                "date": day(raw.get(columns["date"]), "Order date"),
                "revenue": number(raw.get(columns["revenue"]), "Retained revenue"),
                "raw_row": raw, "column_mapping": columns,
                "revenue_basis": text(data.get("revenue_basis"), "Revenue definition")}
            identity = digest([shop, "order_item", item["order_id"], item["transaction_id"]])
            if identity in staged and digest(staged[identity]) != digest(item):
                raise ValueError("Conflicting duplicate transaction in this file")
            existing = con.execute("SELECT project_id FROM records WHERE id=?", (identity,)).fetchone()
            if existing and existing["project_id"] != project_id:
                raise ValueError("This transaction is attributed to another concept")
            staged[identity] = item
        if commit:
            with con:
                for identity, item in staged.items():
                    write_record(con, identity, "order_item", project_id, json.dumps(item, sort_keys=True), digest(item), stamp())
        return {"rows": len(staged), "committed": commit, "preview": list(staged.values())[:10],
            "notes": "Reconcile payment charges and costs in the listing-results worksheet. These orders are not added to results a second time."}
    finally:
        con.close()
def import_competitor_csv(project_id, data):
    rows = list(csv.DictReader(io.StringIO(str(data.get("text") or ""))))
    return save_competitors(project_id, {**data, "listings": rows})


@single_writer
def import_outcomes_csv(project_id, data, commit=False):
    """Preview a normalized listing-period worksheet; never infer absent metrics."""
    rows = list(csv.DictReader(io.StringIO(str(data.get("text") or ""))))
    if not 1 <= len(rows) <= 200:
        raise ValueError("Import 1–200 listing-period rows")
    # Validate the entire file transactionally in a temporary ledger before commit.
    con = connect()
    staged = []
    try:
        con.execute("BEGIN IMMEDIATE")
        for row in rows:
            start, end = period(row)
            clean = {"shop_id": text(row.get("shop_id"), "Shop ID"), "listing_id": text(row.get("listing_id"), "Listing ID"),
                "source": text(data.get("source"), "Source"), "currency": text(row.get("currency"), "Currency").upper(),
                "period_start": start, "period_end": end,
                **{field: number(row.get(field), field, optional=True, integer=True) for field in ("impressions", "clicks", "visits", "orders")},
                "revenue": number(row.get("revenue"), "Revenue", optional=True),
                **{field: number(row.get(field), field, optional=True) for field in (*COST_FIELDS, "setup_expenses", "fixed_expenses")}}
            identity = digest([clean["shop_id"], clean["listing_id"], start, end])
            if any(identity == prior[0] for prior in staged):
                raise ValueError("Duplicate listing period in this import")
            staged.append((identity, clean))
        prior = [(row["id"], row["project_id"], json.loads(row["payload"])) for row in con.execute("SELECT * FROM records WHERE kind='outcome'")]
        for identity, clean in staged:
            for old_id, old_project, old in [*prior, *((i, project_id, p) for i, p in staged if i != identity)]:
                if old_id == identity and old_project != project_id:
                    raise ValueError("Listing period belongs to another concept")
                if old_id != identity and old["shop_id"] == clean["shop_id"] and old["listing_id"] == clean["listing_id"] and clean["period_start"] <= old["period_end"] and clean["period_end"] >= old["period_start"]:
                    raise ValueError("Overlapping listing periods; correct the worksheet before importing")
        project(project_id)
        if commit:
            # A single transaction preserves all rows and revisions or none.
            with con:
                for identity, clean in staged:
                    fingerprint, now = digest(clean), stamp()
                    encoded = json.dumps(clean, sort_keys=True)
                    write_record(con, identity, "outcome", project_id, encoded, fingerprint, now)
        return {"rows": len(staged), "committed": commit, "preview": [payload for _, payload in staged]}
    finally:
        con.close()


def import_google_package(project_id, data):
    concept = project(project_id)
    package = data.get("package")
    if not isinstance(package, dict) or digest(package.get("payload")) != package.get("sha256"):
        raise ValueError("Google evidence package checksum does not match")
    payload = package["payload"]
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or payload.get("source") != "google_ads_keyword_planner":
        raise ValueError("Unsupported Google evidence package")
    signals = payload.get("signals")
    if not isinstance(signals, list) or len(signals) > 100:
        raise ValueError("Google package must contain at most 100 keyword results")
    useful = []
    for row in signals:
        if not isinstance(row, dict):
            raise ValueError("Each Google result must be a keyword object")
        aliases = [row.get("keyword"), *((row.get("metadata") or {}).get("close_variants") or [])]
        matched = [str(alias).lower() for alias in aliases if str(alias).lower() in concept["keywords"]]
        if matched:
            useful.append({**row, "matched_queue_keywords": matched,
                "monthly_searches": number(row.get("monthly_searches"), "Monthly searches", optional=True)})
    if not useful:
        raise ValueError("No Google results match this validation queue")
    return put("google", project_id, {"source": payload["source"], "collected_at": payload.get("collected_at"),
        "geography": payload.get("geography"), "signals": useful, "package_sha256": package["sha256"],
        "provenance": "Imported collector package; checksum verifies integrity, not provider authenticity"},
        digest([project_id, "google", package["sha256"]]))


@single_writer
def review_competitors(project_id, data):
    """Review an exact sample revision, preserving earlier evidence and notes."""
    rows = [row for row in records(project_id, "competitors") if row["id"] == data.get("record_id")]
    if not rows or rows[0]["fingerprint"] != data.get("fingerprint"):
        raise ValueError("Samples changed; refresh and review the current listings")
    payload = {**rows[0]["payload"], "relevance_reviewed": True,
        "review_note": text(data.get("review_note"), "Relevance review note")}
    return put("competitors", project_id, payload, rows[0]["id"])


def collect_etsy(project_id, keyword):
    concept = project(project_id)
    keyword = keyword.strip().lower()
    if keyword not in concept["keywords"]:
        raise ValueError("Choose a keyword from this concept's queue")
    from adapters.research.etsy_open_api import EtsyOpenAPIClient, EtsyOpenAPIError
    client = EtsyOpenAPIClient(timeout=10)
    try:
        if not client.is_configured():
            raise ValueError("Existing Etsy developer credentials are required; manual competitor import remains available")
        # Keep provider fields/currency intact; never convert an unknown price.
        raw = client._get("/listings/active", {"keywords": keyword, "limit": 50, "offset": 0, "sort_on": "score", "sort_order": "down"})
        rows = []
        for row in raw.get("results") or []:
            money = row.get("price") or {}
            if not money.get("divisor") or money.get("amount") is None or not money.get("currency_code"):
                continue
            rows.append({"listing_id": str(row.get("listing_id") or ""), "shop_id": str(row.get("shop_id") or ""),
                "title": row.get("title"), "price": float(money["amount"]) / float(money["divisor"]),
                "currency": money["currency_code"], "shipping": None})
        saved = save_competitors(project_id, {"keyword": keyword, "observed_at": today().isoformat(),
            "source": "etsy_open_api", "listings": rows, "filters": "keywords; score descending; first 50 API results; relevance requires review"})
        put("etsy_raw", project_id, {"keyword": keyword, "collected_at": stamp(), "response": raw})
        return {**saved, "sampled": len(rows), "provider_listing_count": raw.get("count"), "project": summary(project_id)}
    except (EtsyOpenAPIError, httpx.HTTPError) as exc:
        raise ValueError("Etsy collection failed: " + type(exc).__name__ + "; existing evidence is preserved") from exc
    finally:
        client.close()
