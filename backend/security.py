"""Protect the private operator API; public research snapshots remain readable."""
from __future__ import annotations

import hmac
import ipaddress
import os
import httpx
from urllib.parse import urlparse

from fastapi import Request
from starlette.responses import JSONResponse


def allowed_origins() -> list[str]:
    return [value.strip().rstrip("/") for value in os.getenv(
        "PIPELINE_ALLOWED_ORIGINS", "https://etsy-niches.netlify.app"
    ).split(",") if value.strip()]


def _loopback(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def is_authorized(request: Request) -> bool:
    key = os.getenv("PIPELINE_API_TOKEN", "")
    provided = request.headers.get("authorization", "")
    if key and hmac.compare_digest(provided, f"Bearer {key}"):
        return True
    if provided:
        return False
    # Remote proxies/tunnels must authenticate even when their TCP peer is local.
    forwarded = any(name in request.headers for name in (
        "forwarded", "x-forwarded-for", "x-forwarded-host", "cf-connecting-ip",
    ))
    origin = request.headers.get("origin")
    local_origin = not origin or _loopback(urlparse(origin).hostname)
    return bool(
        not forwarded and request.client and _loopback(request.client.host)
        and _loopback(request.url.hostname) and local_origin
    )


async def authenticated_administrator(request: Request) -> bool:
    """Validate with Auth online, then enforce the database's active/MFA policies."""
    token = request.headers.get("authorization", "")
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    anon = os.getenv("SUPABASE_ANON_KEY", "")
    if not token.startswith("Bearer ") or not url.startswith("https://") or not anon:
        return False
    headers = {"Authorization": token, "apikey": anon}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            result = await client.get(f"{url}/auth/v1/user", headers=headers)
            if result.status_code != 200:
                return False
            user = result.json()
            if not user.get("email_confirmed_at") or not user.get("id"):
                return False
            result = await client.get(f"{url}/rest/v1/app_profiles", headers=headers,
                params={"id": f"eq.{user['id']}", "select": "id,role,active"})
            if result.status_code != 200:
                return False
            profiles = result.json()
            if len(profiles) != 1 or profiles[0].get("role") != "admin" or not profiles[0].get("active"):
                return False
            request.state.account_id = user["id"]
            return True
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return False


async def protect_operator_api(request: Request, call_next):
    private_read = request.url.path.startswith(("/api/settings", "/api/scheduler", "/api/stream", "/api/stores", "/api/workspace"))
    protected = request.url.path.startswith("/api/") and (
        request.method not in {"GET", "HEAD", "OPTIONS"} or private_read
    )
    if protected and request.method != "OPTIONS" and not is_authorized(request) and not await authenticated_administrator(request):
        return JSONResponse({"detail": "Sign in with an active administrator account to use this action."},
                            status_code=401, headers={"WWW-Authenticate": "Bearer"})
    return await call_next(request)


def redact_settings(value):
    if isinstance(value, dict):
        return {key: ("[configured]" if item else "") if any(
            word in key.lower() for word in ("key", "token", "secret", "password")
        ) and isinstance(item, str) else redact_settings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_settings(item) for item in value]
    return value
