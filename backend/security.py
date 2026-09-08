"""Protect the private operator API; public research snapshots remain readable."""
from __future__ import annotations

import hmac
import ipaddress
import os
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


async def protect_operator_api(request: Request, call_next):
    private_read = request.url.path.startswith(("/api/settings", "/api/scheduler", "/api/stream", "/api/stores", "/api/workspace"))
    protected = request.url.path.startswith("/api/") and (
        request.method not in {"GET", "HEAD", "OPTIONS"} or private_read
    )
    if protected and request.method != "OPTIONS" and not is_authorized(request):
        return JSONResponse({"detail": "Connect with your operator API token to use this action."},
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
