"""Backend-only provider collection telemetry stored in Supabase."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


def get_provider_states() -> dict[str, dict[str, Any]]:
    """Return backend provider health without returning any credential material."""
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return {}
    try:
        response = httpx.get(
            f"{url}/rest/v1/provider_runtime_state",
            params={
                "select": (
                    "provider,configured,status,last_attempt_at,last_success_at,row_count,"
                    "duration_ms,error,rate_limit,metadata,updated_at"
                ),
            },
            headers={"apikey": key, "authorization": f"Bearer {key}"},
            timeout=15,
        )
        response.raise_for_status()
        rows = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return {}
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("provider")): row
        for row in rows
        if isinstance(row, dict) and row.get("provider")
    }


def get_provider_events(*, hours: int = 24) -> list[dict[str, Any]]:
    """Return recent collection facts for measured coverage calculations."""
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return []
    since = datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))
    try:
        response = httpx.get(
            f"{url}/rest/v1/provider_collection_events",
            params={
                "select": (
                    "provider,operation,status,started_at,completed_at,keyword_count,"
                    "row_count,error,rate_limit,metadata"
                ),
                "completed_at": f"gte.{since.isoformat()}",
                "order": "completed_at.asc",
                "limit": "10000",
            },
            headers={"apikey": key, "authorization": f"Bearer {key}"},
            timeout=20,
        )
        response.raise_for_status()
        rows = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def record_provider_attempt(
    *,
    provider: str,
    operation: str,
    status: str,
    started_at: datetime,
    keyword_count: int,
    row_count: int,
    configured: bool = True,
    error: str | None = None,
    rate_limit: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist one attempt without allowing telemetry failure to stop collection."""
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return

    completed_at = datetime.now(timezone.utc)
    started = _utc(started_at)
    duration_ms = max(0, round((completed_at - started).total_seconds() * 1000))
    clean_error = str(error)[:2000] if error else None
    event = {
        "id": f"provider_{uuid.uuid4().hex}",
        "provider": provider,
        "operation": operation,
        "status": status,
        "started_at": started.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_ms": duration_ms,
        "keyword_count": max(0, int(keyword_count)),
        "row_count": max(0, int(row_count)),
        "error": clean_error,
        "rate_limit": rate_limit,
        "metadata": metadata,
    }
    state = {
        "provider": provider,
        "configured": bool(configured),
        "status": status,
        "last_attempt_at": completed_at.isoformat(),
        "row_count": event["row_count"],
        "duration_ms": duration_ms,
        "error": clean_error,
        "rate_limit": rate_limit,
        "metadata": metadata,
        "updated_at": completed_at.isoformat(),
    }
    if status in {"completed", "no_data", "partial", "unchanged"}:
        state["last_success_at"] = completed_at.isoformat()
    headers = {
        "apikey": key,
        "authorization": f"Bearer {key}",
        "content-type": "application/json",
        "prefer": "resolution=merge-duplicates,return=minimal",
    }
    try:
        with httpx.Client(timeout=15) as client:
            event_response = client.post(
                f"{url}/rest/v1/provider_collection_events",
                headers=headers,
                json=event,
            )
            event_response.raise_for_status()
            state_response = client.post(
                f"{url}/rest/v1/provider_runtime_state",
                params={"on_conflict": "provider"},
                headers=headers,
                json=state,
            )
            state_response.raise_for_status()
    except httpx.HTTPError:
        return


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
