"""Structured imports for useful free keyword evidence sources.

The importers preserve source values and provenance. They do not manufacture
scores, fill missing cells, convert currencies, or infer reporting periods.
"""
from __future__ import annotations

import csv
import io
import math
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from pipeline import keyword_database as kdb


SUPPORTED_SOURCES = {
    "etsy_marketplace_insights",
    "erank",
    "marmalead",
    "etsy_shop_stats",
    "google_keyword_planner",
    "google_trends",
    "pinterest_trends",
}

KEYWORD_HEADERS = {"keyword", "keywords", "search term", "search terms", "query", "term", "phrase"}
SEARCH_HEADERS = {"searches", "etsy searches", "keyword searches", "search volume", "avg monthly searches", "avg searches", "average searches", "monthly searches", "volume"}
CURRENT_SEARCH_HEADERS = {"current searches", "current month searches", "current period searches"}
LISTING_HEADERS = {"listings", "number of listings", "competing listings", "listing count", "competition listings", "etsy competition", "results"}
CLICK_HEADERS = {"clicks", "avg clicks", "average clicks"}
CTR_HEADERS = {"ctr", "ctr percent", "click through rate", "click-through rate"}
COMPETITION_HEADERS = {
    "competition", "competition score", "competition indexed value",
    "keyword difficulty", "difficulty",
}
ENGAGEMENT_HEADERS = {"engagement", "engagement score", "engagement level"}
LOW_BID_HEADERS = {
    "top of page bid low range", "top of page bid low range usd",
    "top of page bid low", "low top of page bid",
}
HIGH_BID_HEADERS = {
    "top of page bid high range", "top of page bid high range usd",
    "top of page bid high", "high top of page bid",
}
VISIT_HEADERS = {"visits", "search visits", "etsy search visits"}
VIEW_HEADERS = {"views", "listing views"}
ORDER_HEADERS = {"orders", "sales"}
REVENUE_HEADERS = {"revenue", "revenue usd", "sales revenue", "sales revenue usd"}
TIME_HEADERS = {"week", "day", "month", "date"}


def import_evidence(*, source: str, text: str, name: str | None = None,
                    observed_at: str | None = None, geography: str | None = None,
                    period_start: str | None = None, period_end: str | None = None,
                    currency_code: str | None = None) -> dict:
    clean_source = source.strip().lower()
    if clean_source not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported evidence source: {source}")
    if not text.strip():
        raise ValueError("import text is empty")
    if clean_source == "etsy_marketplace_insights" and not (period_start and period_end):
        raise ValueError("Marketplace Insights imports require period_start and period_end")
    if clean_source == "etsy_shop_stats" and not (period_start and period_end):
        raise ValueError("Etsy Shop Stats imports require period_start and period_end")
    if clean_source == "google_keyword_planner" and not (period_start and period_end and geography):
        raise ValueError("Google Keyword Planner imports require period_start, period_end, and geography")
    if clean_source == "google_trends" and not geography:
        raise ValueError("Google Trends imports require an explicit geography")

    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    request = {
        "name": name,
        "geography": geography,
        "period_start": period_start,
        "period_end": period_end,
        "currency_code": currency_code,
    }
    run_id = kdb.start_evidence_collection(clean_source, request)
    try:
        if clean_source == "google_trends":
            result = _import_google_trends(
                text=text, source=clean_source, collected_at=timestamp,
                geography=geography or "", run_id=run_id,
            )
        elif clean_source == "pinterest_trends":
            result = _import_pinterest_trends(
                text=text, source=clean_source, collected_at=timestamp,
                geography=geography, run_id=run_id,
            )
        else:
            result = _import_keyword_table(
                text=text, source=clean_source, observed_at=timestamp,
                geography=geography, period_start=period_start,
                period_end=period_end, currency_code=currency_code,
                run_id=run_id,
            )
        status = "completed" if result["observations"] else "no_data"
        kdb.finish_evidence_collection(run_id, status, result["observations"])
        from services.supabase_evidence_sync import sync_collection_run
        durable_sync = sync_collection_run(run_id)
        return {
            "run_id": run_id,
            "source": clean_source,
            "message": f"Recorded {result['observations']} observations for {result['keywords']} keywords.",
            "durable_sync": durable_sync,
            **result,
        }
    except Exception as exc:
        kdb.finish_evidence_collection(run_id, "failed", 0, str(exc))
        raise


def _import_keyword_table(*, text: str, source: str, observed_at: str,
                          geography: str | None, period_start: str | None,
                          period_end: str | None, currency_code: str | None,
                          run_id: str) -> dict:
    rows = _read_rows(text)
    if len(rows) < 2:
        raise ValueError("the import needs a header row and at least one data row")
    headers = [_normalize(value) for value in rows[0]]
    keyword_index = _find_header(headers, KEYWORD_HEADERS)
    if keyword_index is None:
        raise ValueError("no keyword or search-term column was found")

    observations = 0
    imported_keywords: set[str] = set()
    skipped = 0
    warnings: list[str] = []
    indexes = {
        "current_searches": _find_header(headers, CURRENT_SEARCH_HEADERS),
        "searches": _find_header(headers, SEARCH_HEADERS),
        "listings": _find_header(headers, LISTING_HEADERS),
        "clicks": _find_header(headers, CLICK_HEADERS),
        "ctr": _find_header(headers, CTR_HEADERS),
        "competition": _find_header(headers, COMPETITION_HEADERS),
        "engagement": _find_header(headers, ENGAGEMENT_HEADERS),
        "low_bid": _find_header(headers, LOW_BID_HEADERS),
        "high_bid": _find_header(headers, HIGH_BID_HEADERS),
        "visits": _find_header(headers, VISIT_HEADERS),
        "views": _find_header(headers, VIEW_HEADERS),
        "orders": _find_header(headers, ORDER_HEADERS),
        "revenue": _find_header(headers, REVENUE_HEADERS),
    }
    if not any(index is not None for index in indexes.values()):
        raise ValueError("no supported evidence columns were found")
    definitions = _definitions_for_source(source, indexes, currency_code)
    if source == "etsy_shop_stats" and indexes.get("revenue") is not None and not currency_code:
        warnings.append("Revenue was not imported because no currency code was supplied.")
    if source == "google_keyword_planner" and (
        indexes.get("low_bid") is not None or indexes.get("high_bid") is not None
    ) and not currency_code:
        warnings.append("Bid ranges were not imported because no currency code was supplied.")

    for row_number, row in enumerate(rows[1:], start=2):
        keyword = _cell(row, keyword_index).strip().lower()
        if not keyword:
            skipped += 1
            continue
        row_observations = 0
        for definition in definitions:
            raw = _cell(row, definition["index"])
            value, bound = _bounded_number(raw)
            if value is None:
                continue
            if value < 0:
                warnings.append(f"row {row_number}: negative {definition['metric']} skipped")
                continue
            metric = definition["metric"]
            unit = definition["unit"]
            if bound:
                metric = f"{metric}_{bound}_bound"
                unit = f"{unit}_{bound}_bound"
            kdb.record_keyword_observation(
                keyword=keyword,
                source=source,
                metric=metric,
                value=value,
                unit=unit,
                observed_at=observed_at,
                geography=geography,
                period_start=period_start if definition.get("uses_period", True) else None,
                period_end=period_end if definition.get("uses_period", True) else None,
                collection_run_id=run_id,
                metadata={
                    "import_header": headers[definition["index"]],
                    "row": row_number,
                    **({"bound": bound, "raw_value": raw.strip()} if bound else {}),
                },
            )
            row_observations += 1
        if row_observations:
            imported_keywords.add(keyword)
            observations += row_observations
        else:
            skipped += 1
    return {
        "rows": max(0, len(rows) - 1),
        "keywords": len(imported_keywords),
        "observations": observations,
        "skipped": skipped,
        "warnings": warnings[:50],
    }


def _definitions_for_source(source: str, indexes: dict[str, int | None],
                            currency_code: str | None) -> list[dict]:
    definitions: list[dict] = []

    def add(key: str, metric: str, unit: str, *, uses_period: bool = True) -> None:
        index = indexes.get(key)
        if index is not None:
            definitions.append({
                "index": index, "metric": metric, "unit": unit,
                "uses_period": uses_period,
            })

    if source == "etsy_marketplace_insights":
        add("searches", "searches", "searches_per_period")
        add("listings", "listing_count", "count")
    elif source == "erank":
        add("current_searches", "current_period_searches", "searches_per_period")
        add("searches", "monthly_searches", "searches_per_month", uses_period=False)
        add("clicks", "monthly_clicks", "clicks_per_month", uses_period=False)
        add("ctr", "click_through_rate", "percent", uses_period=False)
        add("listings", "competition_listings", "count", uses_period=False)
        add("competition", "provider_competition", "provider_value", uses_period=False)
    elif source == "marmalead":
        add("searches", "monthly_searches", "searches_per_month")
        add("engagement", "provider_engagement", "provider_value")
        add("competition", "provider_competition", "provider_value")
        add("listings", "competition_listings", "count")
    elif source == "google_keyword_planner":
        add("searches", "monthly_searches", "searches_per_month")
        add("competition", "provider_competition", "provider_value")
        if currency_code:
            unit = currency_code.strip().lower()
            add("low_bid", "top_of_page_bid_low", unit)
            add("high_bid", "top_of_page_bid_high", unit)
    elif source == "etsy_shop_stats":
        add("visits", "shop_search_visits", "count")
        add("views", "shop_listing_views", "count")
        add("orders", "shop_orders", "count")
        revenue_index = indexes.get("revenue")
        if revenue_index is not None and currency_code:
            add("revenue", "shop_revenue", currency_code.strip().lower())
    return definitions


def _import_google_trends(*, text: str, source: str, collected_at: str,
                          geography: str, run_id: str) -> dict:
    rows = _read_rows(text)
    header_row = None
    for index, row in enumerate(rows):
        if row and _normalize(row[0]) in TIME_HEADERS and len(row) > 1:
            header_row = index
            break
    if header_row is None:
        raise ValueError("no Google Trends date header was found")
    headers = [value.strip() for value in rows[header_row]]
    points_by_keyword: dict[str, list[dict]] = {
        keyword.strip().lower(): [] for keyword in headers[1:] if keyword.strip()
    }
    skipped = 0
    for row in rows[header_row + 1:]:
        point_at = _cell(row, 0).strip()
        if not point_at:
            skipped += 1
            continue
        for column, keyword in enumerate(headers[1:], start=1):
            normalized = keyword.strip().lower()
            if not normalized:
                continue
            value = _number(_cell(row, column))
            if value is None:
                continue
            points_by_keyword[normalized].append({
                "date": point_at,
                "value": value,
                "unit": "relative_interest_index",
            })
    observations = 0
    imported_keywords = 0
    timeframe = _normalize(headers[0])
    for keyword, points in points_by_keyword.items():
        count = kdb.record_keyword_trend_points(
            keyword, source, points, collected_at=collected_at,
            geography=geography, timeframe=timeframe,
            collection_run_id=run_id,
            metadata={"import_header": headers[0]},
        )
        if count:
            imported_keywords += 1
            observations += count
    return {
        "rows": max(0, len(rows) - header_row - 1),
        "keywords": imported_keywords,
        "observations": observations,
        "skipped": skipped,
        "warnings": [],
    }


def _import_pinterest_trends(*, text: str, source: str, collected_at: str,
                             geography: str | None, run_id: str) -> dict:
    """Import Pinterest's official Trends CSV without inventing absolute volume."""
    rows = _read_rows(text)
    header_row = next((
        index for index, row in enumerate(rows)
        if len(row) > 1 and _normalize(row[0]) == "rank" and _normalize(row[1]) == "trend"
    ), None)
    if header_row is None:
        raise ValueError("no Pinterest Trends Rank,Trend header was found")

    export_url = next((cell.strip() for row in rows[:header_row] for cell in row
                       if "trends.pinterest.com/search/" in cell), "")
    filters = {
        _normalize(row[0]): row[1].strip()
        for row in rows[:header_row] if len(row) > 1 and row[0].strip() and row[1].strip()
    }
    parsed_geo = ""
    if export_url:
        parsed_geo = (parse_qs(urlparse(export_url.replace("&amp;", "&")).query)
                      .get("country", [""])[0].strip())
    report_geo = (geography or parsed_geo).strip()
    if not report_geo:
        raise ValueError("Pinterest Trends imports require a geography or an official export URL with country")

    raw_headers = [cell.strip() for cell in rows[header_row]]
    headers = [_normalize(cell) for cell in raw_headers]
    indexes = {
        "rank": _find_header(headers, {"rank"}),
        "trend": _find_header(headers, {"trend"}),
        "normalized_volume": _find_header(headers, {"normalized volume"}),
        "weekly": _find_header(headers, {"weekly change"}),
        "monthly": _find_header(headers, {"monthly change"}),
        "yearly": _find_header(headers, {"yearly change"}),
    }
    date_columns = [
        (index, header) for index, header in enumerate(raw_headers)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", header)
    ]
    if not date_columns:
        raise ValueError("Pinterest Trends import has no dated trend columns")

    trend_type = filters.get("trend type", "")
    date_range = filters.get("date range", "")
    period_start, period_end = date_columns[0][1], date_columns[-1][1]
    observations = 0
    imported_keywords: set[str] = set()
    skipped = 0
    warnings: list[str] = []

    for row_number, row in enumerate(rows[header_row + 1:], start=header_row + 2):
        keyword = _cell(row, indexes["trend"]).strip().lower()
        if not keyword:
            skipped += 1
            continue
        metadata = {
            "export_url": export_url or None,
            "trend_type": trend_type or None,
            "date_range": date_range or None,
            "row": row_number,
            "series_normalization": "provider_normalized_0_100",
        }
        row_observations = 0
        for key, metric, unit in (
            ("rank", "provider_rank", "rank"),
            ("normalized_volume", "normalized_volume", "relative_interest_index"),
        ):
            value = _number(_cell(row, indexes[key]))
            if value is None:
                continue
            if value < 0:
                warnings.append(f"row {row_number}: negative {metric} skipped")
                continue
            kdb.record_keyword_observation(
                keyword=keyword, source=source, metric=metric, value=value, unit=unit,
                observed_at=collected_at, geography=report_geo,
                period_start=period_start, period_end=period_end,
                collection_run_id=run_id,
                metadata={**metadata, "import_header": raw_headers[indexes[key]]},
            )
            row_observations += 1

        for key, metric in (
            ("weekly", "growth_week_over_week"),
            ("monthly", "growth_month_over_month"),
            ("yearly", "growth_year_over_year"),
        ):
            raw = _cell(row, indexes[key])
            value, bound = _bounded_number(raw)
            if value is None:
                continue
            stored_metric = f"{metric}_{bound}_bound" if bound else metric
            unit = f"percent_{bound}_bound" if bound else "percent"
            kdb.record_keyword_observation(
                keyword=keyword, source=source, metric=stored_metric, value=value, unit=unit,
                observed_at=collected_at, geography=report_geo,
                period_start=period_start, period_end=period_end,
                collection_run_id=run_id,
                metadata={
                    **metadata, "import_header": raw_headers[indexes[key]],
                    **({"bound": bound, "raw_value": raw.strip()} if bound else {}),
                },
            )
            row_observations += 1

        points = []
        for column, point_at in date_columns:
            value = _number(_cell(row, column))
            if value is not None:
                points.append({
                    "date": point_at, "value": value,
                    "unit": "relative_interest_index",
                })
        point_count = kdb.record_keyword_trend_points(
            keyword, source, points, collected_at=collected_at,
            geography=report_geo, timeframe=date_range or trend_type or None,
            collection_run_id=run_id, metadata=metadata,
        )
        if row_observations or point_count:
            imported_keywords.add(keyword)
            observations += row_observations + point_count
        else:
            skipped += 1
    return {
        "rows": max(0, len(rows) - header_row - 1),
        "keywords": len(imported_keywords),
        "observations": observations,
        "skipped": skipped,
        "warnings": warnings[:50],
    }


def _read_rows(text: str) -> list[list[str]]:
    clean = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").strip()
    if not clean:
        return []
    sample = clean[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel_tab if "\t" in clean.split("\n", 1)[0] else csv.excel
    return [row for row in csv.reader(io.StringIO(clean), dialect) if any(cell.strip() for cell in row)]


def _find_header(headers: list[str], aliases: set[str]) -> int | None:
    return next((index for index, header in enumerate(headers) if header in aliases), None)


def _cell(row: list[str], index: int | None) -> str:
    return row[index] if index is not None and index < len(row) else ""


def _normalize(value: str) -> str:
    clean = value.strip().lower().replace("_", " ").replace("%", " percent")
    clean = re.sub(r"[().]", " ", clean)
    return re.sub(r"\s+", " ", clean).strip()


def _number(value: str) -> float | None:
    clean = value.strip().replace(",", "").replace("$", "").replace("%", "")
    if not clean or clean.lower() in {"n/a", "na", "null", "tbd", "-", "<1"}:
        return None
    multiplier = 1.0
    if clean[-1:].lower() in {"k", "m"}:
        multiplier = 1_000.0 if clean[-1:].lower() == "k" else 1_000_000.0
        clean = clean[:-1]
    try:
        number = float(clean) * multiplier
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _bounded_number(value: str) -> tuple[float | None, str | None]:
    clean = value.strip()
    bound = None
    if clean.startswith("<"):
        bound, clean = "upper", clean[1:].strip()
    elif clean.endswith("+"):
        bound, clean = "lower", clean[:-1].strip()
    return _number(clean), bound
