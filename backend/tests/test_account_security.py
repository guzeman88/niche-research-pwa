import asyncio
import httpx
import pytest
from starlette.requests import Request
import security


def request(headers=(), path="/api/settings"):
    return Request({"type": "http", "method": "POST", "scheme": "http", "path": path,
        "server": ("127.0.0.1", 8001), "client": ("127.0.0.1", 5000),
        "query_string": b"", "headers": [(b"host", b"127.0.0.1:8001"), *headers]})


def test_invalid_bearer_never_falls_back_to_loopback(monkeypatch):
    monkeypatch.delenv("PIPELINE_API_TOKEN", raising=False)
    assert not security.is_authorized(request([(b"authorization", b"Bearer invalid")]))


@pytest.mark.parametrize("role,active,confirmed,expected", [
    ("admin", True, True, True), ("member", True, True, False),
    ("admin", False, True, False), ("admin", True, False, False),
    (None, True, True, False),
])
def test_account_authorization_uses_verified_user_and_rls_profile(monkeypatch, role, active, confirmed, expected):
    monkeypatch.setenv("SUPABASE_URL", "https://auth.example.test")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-test-key")
    def respond(req):
        assert req.headers["authorization"] == "Bearer test"
        if req.url.path.endswith("/user"):
            return httpx.Response(200, json={"id": "test-id", "email_confirmed_at": "now" if confirmed else None})
        return httpx.Response(200, json=[] if role is None else [{"id": "test-id", "role": role, "active": active}])
    original = httpx.AsyncClient
    monkeypatch.setattr(security.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(respond), **kwargs))
    assert asyncio.run(security.authenticated_administrator(request([(b"authorization", b"Bearer test")]))) is expected


def test_github_heartbeat_identity_is_exact_and_scheduler_scoped(monkeypatch):
    valid = {
        "repository": "guzeman88/niche-research-pwa",
        "workflow_ref": "guzeman88/niche-research-pwa/.github/workflows/keepalive.yml@refs/heads/main",
        "ref": "refs/heads/main",
        "event_name": "schedule",
    }

    async def claims(_token):
        return valid

    monkeypatch.setattr(security, "_github_oidc_claims", claims)
    authorized = request([(b"authorization", b"Bearer signed-token")], "/api/scheduler/start")
    wrong_path = request([(b"authorization", b"Bearer signed-token")], "/api/evidence/import")
    assert asyncio.run(security.github_heartbeat_authorized(authorized))
    assert not asyncio.run(security.github_heartbeat_authorized(wrong_path))


@pytest.mark.parametrize("claim,value", [
    ("repository", "someone/else"),
    ("workflow_ref", "guzeman88/niche-research-pwa/.github/workflows/other.yml@refs/heads/main"),
    ("ref", "refs/heads/feature"),
    ("event_name", "pull_request"),
])
def test_github_heartbeat_rejects_wrong_identity_claim(monkeypatch, claim, value):
    candidate = {
        "repository": "guzeman88/niche-research-pwa",
        "workflow_ref": "guzeman88/niche-research-pwa/.github/workflows/keepalive.yml@refs/heads/main",
        "ref": "refs/heads/main",
        "event_name": "workflow_dispatch",
    }
    candidate[claim] = value
    assert not security._github_heartbeat_claims_allowed(candidate)
