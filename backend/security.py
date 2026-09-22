"""Protect the private operator API; public research snapshots remain readable."""
from __future__ import annotations

import hmac
import ipaddress
import logging
import os
import time
import httpx
from jose import JWTError, jwt
from urllib.parse import urlparse

from fastapi import Request
from starlette.responses import JSONResponse


GITHUB_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
GITHUB_OIDC_JWKS_URL = f"{GITHUB_OIDC_ISSUER}/.well-known/jwks"
GITHUB_HEARTBEAT_PATHS = frozenset({"/api/scheduler/start", "/api/scheduler/status"})
_github_jwks_cache: dict = {"keys": [], "expires_at": 0.0}
logger = logging.getLogger(__name__)


def allowed_origins() -> list[str]:
    return [value.strip().rstrip("/") for value in os.getenv(
        "PIPELINE_ALLOWED_ORIGINS", "https://etgen.netlify.app"
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


async def _github_oidc_claims(token: str) -> dict | None:
    """Verify a GitHub-issued token and return only its signed claims."""
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not kid:
            return None

        now = time.monotonic()
        if now >= float(_github_jwks_cache.get("expires_at", 0)):
            async with httpx.AsyncClient(timeout=10) as client:
                result = await client.get(GITHUB_OIDC_JWKS_URL)
                result.raise_for_status()
                payload = result.json()
            keys = payload.get("keys") if isinstance(payload, dict) else None
            if not isinstance(keys, list):
                return None
            _github_jwks_cache.update(keys=keys, expires_at=now + 3600)

        key = next((item for item in _github_jwks_cache["keys"] if item.get("kid") == kid), None)
        if not key:
            # A rotated signing key should trigger one clean refresh on the next request.
            _github_jwks_cache["expires_at"] = 0.0
            return None
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=GITHUB_OIDC_ISSUER,
            audience=os.getenv("GITHUB_HEARTBEAT_AUDIENCE", "etgen-evidence-collector"),
            options={"require_exp": True, "require_iat": True, "require_sub": True},
        )
    except (JWTError, httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        logger.warning("GitHub heartbeat token verification failed: %s", type(error).__name__)
        return None


def _github_heartbeat_claims_allowed(claims: dict | None) -> bool:
    if not claims:
        return False
    repository = os.getenv("GITHUB_HEARTBEAT_REPOSITORY", "guzeman88/niche-research-pwa")
    workflow_ref = os.getenv(
        "GITHUB_HEARTBEAT_WORKFLOW_REF",
        f"{repository}/.github/workflows/keepalive.yml@refs/heads/main",
    )
    checks = {
        "repository": hmac.compare_digest(str(claims.get("repository", "")), repository),
        "workflow_ref": hmac.compare_digest(str(claims.get("workflow_ref", "")), workflow_ref),
        "ref": hmac.compare_digest(str(claims.get("ref", "")), "refs/heads/main"),
        "event_name": claims.get("event_name") in {"schedule", "workflow_dispatch"},
    }
    rejected = [name for name, accepted in checks.items() if not accepted]
    if rejected:
        logger.warning("GitHub heartbeat identity rejected for claims: %s", ", ".join(rejected))
    return not rejected


async def github_heartbeat_authorized(request: Request) -> bool:
    """Allow only EtGen's scheduled workflow to operate the collector lifecycle."""
    if request.url.path not in GITHUB_HEARTBEAT_PATHS:
        return False
    provided = request.headers.get("authorization", "")
    if not provided.startswith("Bearer "):
        return False
    return _github_heartbeat_claims_allowed(await _github_oidc_claims(provided[7:]))


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
    private_read = request.url.path.startswith(("/api/settings", "/api/scheduler", "/api/stream", "/api/stores", "/api/workspace", "/api/evidence"))
    protected = request.url.path.startswith("/api/") and (
        request.method not in {"GET", "HEAD", "OPTIONS"} or private_read
    )
    if (protected and request.method != "OPTIONS" and not is_authorized(request)
            and not await github_heartbeat_authorized(request)
            and not await authenticated_administrator(request)):
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
