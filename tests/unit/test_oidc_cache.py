"""Tests for per-worker OIDC document caching and cache configuration."""

import importlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, Mock

import pytest
from kubernetes.client.exceptions import ApiException


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        (
            "OIDC_DOCUMENT_CACHE_TTL_SECONDS",
            "invalid",
            "OIDC_DOCUMENT_CACHE_TTL_SECONDS must be a number",
        ),
        (
            "OIDC_DOCUMENT_CACHE_TTL_SECONDS",
            "-1",
            "OIDC_DOCUMENT_CACHE_TTL_SECONDS must be a finite non-negative number",
        ),
        (
            "OIDC_DOCUMENT_CACHE_STALE_IF_ERROR_SECONDS",
            "nan",
            "OIDC_DOCUMENT_CACHE_STALE_IF_ERROR_SECONDS must be a finite non-negative number",
        ),
        (
            "OIDC_DOCUMENT_CACHE_MAX_DOCUMENT_BYTES",
            "invalid",
            "OIDC_DOCUMENT_CACHE_MAX_DOCUMENT_BYTES must be an integer",
        ),
        (
            "OIDC_DOCUMENT_CACHE_MAX_DOCUMENT_BYTES",
            "0",
            "OIDC_DOCUMENT_CACHE_MAX_DOCUMENT_BYTES must be greater than zero",
        ),
    ],
)
def test_invalid_cache_environment_values_raise(app_module, monkeypatch, name, value, message):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        importlib.reload(app_module)


def test_unknown_cache_key_is_rejected(app_module):
    with pytest.raises(ValueError, match="Unknown OIDC document cache key"):
        app_module.fetch_with_cache("unknown", Mock())


def test_failed_refresh_serves_stale_document_and_backs_off(app_module, monkeypatch):
    app_module.OIDC_DOCUMENT_CACHE_TTL_SECONDS = 0
    app_module.OIDC_DOCUMENT_CACHE_STALE_IF_ERROR_SECONDS = 30
    app_module.OIDC_DOCUMENT_CACHE_ERROR_BACKOFF_SECONDS = 5
    monkeypatch.setattr(app_module.time, "monotonic", lambda: 102.0)
    document = {"keys": []}
    app_module._oidc_document_cache["jwks"] = app_module._CacheEntry(document, 100.0)
    fetch_document = Mock(side_effect=RuntimeError("API throttled"))

    assert app_module.fetch_with_cache("jwks", fetch_document) == document
    assert app_module._oidc_document_cache_retry_after["jwks"] == 107.0
    assert app_module.fetch_with_cache("jwks", fetch_document) == document
    fetch_document.assert_called_once_with()


def test_expired_stale_document_does_not_hide_refresh_error(app_module, monkeypatch):
    app_module.OIDC_DOCUMENT_CACHE_TTL_SECONDS = 0
    app_module.OIDC_DOCUMENT_CACHE_STALE_IF_ERROR_SECONDS = 30
    monkeypatch.setattr(app_module.time, "monotonic", lambda: 200.0)
    app_module._oidc_document_cache["jwks"] = app_module._CacheEntry({"keys": []}, 100.0)

    with pytest.raises(RuntimeError, match="API unavailable"):
        app_module.fetch_with_cache("jwks", Mock(side_effect=RuntimeError("API unavailable")))


def test_document_is_not_cached_when_it_exceeds_size_limit(app_module, monkeypatch):
    app_module.OIDC_DOCUMENT_CACHE_MAX_DOCUMENT_BYTES = 1
    monkeypatch.setattr(app_module.time, "monotonic", lambda: 100.0)
    document = {"keys": []}

    assert app_module.fetch_with_cache("jwks", lambda: document) == document
    assert "jwks" not in app_module._oidc_document_cache


def test_refresh_lock_uses_document_refreshed_while_waiting(app_module, monkeypatch):
    app_module.OIDC_DOCUMENT_CACHE_TTL_SECONDS = 10
    monkeypatch.setattr(app_module.time, "monotonic", lambda: 100.0)
    old = app_module._CacheEntry({"keys": ["old"]}, 0.0)
    refreshed = app_module._CacheEntry({"keys": ["new"]}, 100.0)

    class RefreshedDuringWait(dict):
        reads = 0

        def get(self, key, default=None):
            self.reads += 1
            return old if self.reads == 1 else refreshed

    app_module._oidc_document_cache = RefreshedDuringWait()
    fetch_document = Mock()

    assert app_module.fetch_with_cache("jwks", fetch_document) == refreshed.document
    fetch_document.assert_not_called()


def test_refresh_lock_uses_stale_document_when_backoff_started_while_waiting(
    app_module, monkeypatch
):
    app_module.OIDC_DOCUMENT_CACHE_TTL_SECONDS = 0
    app_module.OIDC_DOCUMENT_CACHE_STALE_IF_ERROR_SECONDS = 30
    monkeypatch.setattr(app_module.time, "monotonic", lambda: 100.0)
    stale = app_module._CacheEntry({"keys": ["stale"]}, 90.0)

    class StaleDocument(dict):
        def get(self, key, default=None):
            return stale

    class BackoffStartedWhileWaiting(dict):
        reads = 0

        def get(self, key, default=None):
            self.reads += 1
            return 0.0 if self.reads == 1 else 105.0

    app_module._oidc_document_cache = StaleDocument()
    app_module._oidc_document_cache_retry_after = BackoffStartedWhileWaiting()
    fetch_document = Mock()

    assert app_module.fetch_with_cache("jwks", fetch_document) == stale.document
    fetch_document.assert_not_called()


@pytest.mark.parametrize("status", [429, 503])
@pytest.mark.parametrize(
    ("path", "api_group", "method", "document"),
    [
        (
            "/openid/v1/jwks",
            "OpenidApi",
            "get_service_account_issuer_open_id_keyset",
            {"keys": [{"kid": "original", "kty": "RSA"}]},
        ),
        (
            "/.well-known/openid-configuration",
            "WellKnownApi",
            "get_service_account_issuer_open_id_configuration",
            {
                "issuer": "https://oidc.example.com",
                "jwks_uri": "https://oidc.example.com/openid/v1/jwks",
            },
        ),
    ],
)
def test_endpoint_cache_handles_api_throttling_and_recovers(
    app_module, client, mock_k8s_client, monkeypatch, status, path, api_group, method, document
):
    clock = [100.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    app_module.OIDC_DOCUMENT_CACHE_TTL_SECONDS = 1
    app_module.OIDC_DOCUMENT_CACHE_STALE_IF_ERROR_SECONDS = 20
    app_module.OIDC_DOCUMENT_CACHE_ERROR_BACKOFF_SECONDS = 5
    upstream = getattr(getattr(mock_k8s_client, api_group).return_value, method)
    response = MagicMock(data=json.dumps(document).encode())
    upstream.side_effect = [
        response,
        ApiException(status=status, reason="Upstream unavailable"),
        response,
    ]

    assert client.get(path).get_json() == document
    assert client.get(path).get_json() == document
    assert upstream.call_count == 1
    clock[0] = 102.0
    assert client.get(path).get_json() == document
    assert client.get(path).get_json() == document
    assert upstream.call_count == 2
    clock[0] = 108.0
    assert client.get(path).get_json() == document
    assert upstream.call_count == 3


def test_stale_expiry_takes_precedence_over_error_backoff(app_module, monkeypatch):
    clock = [102.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    app_module.OIDC_DOCUMENT_CACHE_TTL_SECONDS = 1
    app_module.OIDC_DOCUMENT_CACHE_STALE_IF_ERROR_SECONDS = 2
    app_module.OIDC_DOCUMENT_CACHE_ERROR_BACKOFF_SECONDS = 30
    document = {"keys": []}
    app_module._oidc_document_cache["jwks"] = app_module._CacheEntry(document, 100.0)
    upstream = Mock(side_effect=ApiException(status=429))
    assert app_module.fetch_with_cache("jwks", upstream) == document
    clock[0] = 104.0
    with pytest.raises(ApiException):
        app_module.fetch_with_cache("jwks", upstream)
    assert upstream.call_count == 2


def test_concurrent_requests_share_one_refresh(app_module, monkeypatch):
    monkeypatch.setattr(app_module.time, "monotonic", lambda: 100.0)
    start = threading.Barrier(8, timeout=5)
    fetching = threading.Event()
    release = threading.Event()
    document = {"keys": []}

    def fetch():
        fetching.set()
        assert release.wait(timeout=5)
        return document

    upstream = Mock(side_effect=fetch)

    def request_document():
        start.wait()
        return app_module.fetch_with_cache("jwks", upstream)

    with ThreadPoolExecutor(max_workers=8) as executor:
        requests = [executor.submit(request_document) for _ in range(8)]
        assert fetching.wait(timeout=5)
        release.set()
        assert [request.result(timeout=5) for request in requests] == [document] * 8
    upstream.assert_called_once_with()
