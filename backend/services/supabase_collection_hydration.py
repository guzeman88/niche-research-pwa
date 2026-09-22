"""Restore durable keyword queue progress from Supabase after process restarts."""

from __future__ import annotations

import os
from typing import Any

import httpx


def hydrate_collection_state() -> dict[str, int | bool | str]:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return {"configured": False, "seeds": 0, "states": 0}

    headers = {"apikey": key, "authorization": f"Bearer {key}"}
    try:
        with httpx.Client(timeout=30) as client:
            seeds = _all_rows(
                client,
                f"{url}/rest/v1/keyword_seeds",
                headers,
                "keyword,domain,source,added_at",
            )
            states = _all_rows(
                client,
                f"{url}/rest/v1/keyword_collection_state",
                headers,
                (
                    "keyword,last_collected_at,evidence_status,listing_count,"
                    "sampled_listing_count,avg_price_usd,sources,last_run_id,updated_at"
                ),
            )
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        return {"configured": True, "seeds": 0, "states": 0, "error": str(exc)}

    from pipeline import keyword_database as kdb

    new_seeds, new_states = kdb.merge_remote_collection_state(seeds, states)
    return {
        "configured": True,
        "seeds": len(seeds),
        "states": len(states),
        "new_seeds": new_seeds,
        "new_states": new_states,
    }


def _all_rows(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    columns: str,
) -> list[dict[str, Any]]:
    page_size = 1000
    offset = 0
    result: list[dict[str, Any]] = []
    while True:
        response = client.get(
            url,
            params={
                "select": columns,
                "order": "keyword.asc",
                "limit": str(page_size),
                "offset": str(offset),
            },
            headers=headers,
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            raise ValueError("Supabase returned a non-list collection page")
        result.extend(row for row in rows if isinstance(row, dict))
        if len(rows) < page_size:
            return result
        offset += page_size
