from __future__ import annotations

from unittest.mock import Mock

from adapters.research import etsy_open_api


def setup_function() -> None:
    etsy_open_api._clear_stored_api_key_cache()


def teardown_function() -> None:
    etsy_open_api._clear_stored_api_key_cache()


def test_explicit_environment_credential_takes_precedence(monkeypatch) -> None:
    monkeypatch.setenv("ETSY_X_API_KEY", "environment-key:environment-secret")
    monkeypatch.setattr(
        etsy_open_api,
        "_supabase_api_key_header",
        Mock(side_effect=AssertionError("Supabase should not be queried")),
    )

    assert etsy_open_api._api_key_header() == "environment-key:environment-secret"


def test_supabase_credential_is_used_when_environment_is_empty(monkeypatch) -> None:
    monkeypatch.delenv("ETSY_X_API_KEY", raising=False)
    monkeypatch.delenv("ETSY_API_KEYSTRING", raising=False)
    monkeypatch.delenv("ETSY_API_KEY", raising=False)
    monkeypatch.delenv("ETSY_SHARED_SECRET", raising=False)
    monkeypatch.delenv("ETSY_API_SHARED_SECRET", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = [{"secret_value": "stored-key:stored-secret"}]
    request = Mock(return_value=response)
    monkeypatch.setattr(etsy_open_api.httpx, "get", request)

    assert etsy_open_api._api_key_header() == "stored-key:stored-secret"
    assert etsy_open_api._api_key_header() == "stored-key:stored-secret"
    request.assert_called_once()


def test_missing_stored_credential_remains_unconfigured(monkeypatch) -> None:
    for name in (
        "ETSY_X_API_KEY",
        "ETSY_API_KEYSTRING",
        "ETSY_API_KEY",
        "ETSY_SHARED_SECRET",
        "ETSY_API_SHARED_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = []
    monkeypatch.setattr(etsy_open_api.httpx, "get", Mock(return_value=response))

    assert etsy_open_api._api_key_header() == ""
    assert etsy_open_api.is_etsy_open_api_configured() is False


def test_supabase_failure_does_not_create_a_fake_credential(monkeypatch) -> None:
    monkeypatch.delenv("ETSY_X_API_KEY", raising=False)
    monkeypatch.delenv("ETSY_API_KEYSTRING", raising=False)
    monkeypatch.delenv("ETSY_API_KEY", raising=False)
    monkeypatch.delenv("ETSY_SHARED_SECRET", raising=False)
    monkeypatch.delenv("ETSY_API_SHARED_SECRET", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setattr(
        etsy_open_api.httpx,
        "get",
        Mock(side_effect=etsy_open_api.httpx.ConnectError("unavailable")),
    )

    assert etsy_open_api._api_key_header() == ""
