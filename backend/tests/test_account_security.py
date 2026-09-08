import asyncio
import httpx
import pytest
from starlette.requests import Request
import security


def request(headers=()):
    return Request({"type": "http", "method": "POST", "scheme": "http", "path": "/api/settings",
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
