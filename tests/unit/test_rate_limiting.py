"""Unit tests for rate limiting and external caller address resolution."""

import importlib
import json
from unittest.mock import MagicMock

import pytest

from app.client_ip import resolve_client_ip


class TestRateLimiting:
    """Tests for flask_limiter enforcement and client separation."""

    def test_oidc_endpoints_rate_limited(self, app_module, mock_k8s_client, monkeypatch):
        monkeypatch.setenv("DEFAULT_RATE_LIMIT", "2 per minute")
        importlib.reload(app_module)
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_configuration.return_value = MagicMock(
            data=json.dumps(
                {
                    "issuer": "https://issuer.example",
                    "jwks_uri": "https://issuer.example/openid/v1/jwks",
                }
            ).encode()
        )
        mock_k8s_client.WellKnownApi.return_value = mock_api
        test_client = app_module.app.test_client()

        test_client.get("/.well-known/openid-configuration")
        test_client.get("/.well-known/openid-configuration")

        assert test_client.get("/.well-known/openid-configuration").status_code == 429

    def test_jwks_endpoints_rate_limited(self, app_module, mock_k8s_client, monkeypatch):
        monkeypatch.setenv("DEFAULT_RATE_LIMIT", "1 per minute")
        importlib.reload(app_module)
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_keyset.return_value = MagicMock(
            data=json.dumps({"keys": []}).encode()
        )
        mock_k8s_client.OpenidApi.return_value = mock_api
        test_client = app_module.app.test_client()

        test_client.get("/openid/v1/jwks")

        assert test_client.get("/openid/v1/jwks").status_code == 429

    def test_forwarded_callers_have_independent_limits(
        self, app_module, mock_k8s_client, monkeypatch
    ):
        """The edge-normalized caller address, not the proxy, keys the limiter."""
        monkeypatch.setenv("DEFAULT_RATE_LIMIT", "1 per minute")
        importlib.reload(app_module)
        monkeypatch.setattr(app_module, "get_k8s_client", lambda: mock_k8s_client)
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_keyset.return_value = MagicMock(
            data=b'{"keys": []}'
        )
        mock_k8s_client.OpenidApi.return_value = mock_api
        test_client = app_module.app.test_client()

        first = test_client.get("/openid/v1/jwks", headers={"X-Forwarded-For": "198.51.100.10"})
        limited = test_client.get("/openid/v1/jwks", headers={"X-Forwarded-For": "198.51.100.10"})
        second = test_client.get("/openid/v1/jwks", headers={"X-Forwarded-For": "203.0.113.20"})

        assert first.status_code == 200
        assert limited.status_code == 429
        assert second.status_code == 200
        # Both callers get independent rate limits while sharing the same cached JWKS.
        assert mock_api.get_service_account_issuer_open_id_keyset.call_count == 1


@pytest.mark.parametrize(
    ("forwarded_for", "peer", "expected"),
    [
        ("198.51.100.10", "10.20.0.8", "198.51.100.10"),
        ("198.51.100.10, 192.0.2.45", "10.20.0.8", "198.51.100.10"),
        ("2001:0db8::10, 2001:db8::20", "2001:db8::30", "2001:db8::10"),
        (None, "10.20.0.8", "10.20.0.8"),
        ("-", "10.20.0.8", "10.20.0.8"),
        ("invalid, 198.51.100.10", "10.20.0.8", "10.20.0.8"),
        (None, "invalid-peer", "invalid-peer"),
        (None, None, "-"),
    ],
)
def test_client_ip_resolution(forwarded_for, peer, expected):
    """Caller resolution handles proxy chains, fallbacks, and malformed input."""
    assert resolve_client_ip(forwarded_for, peer) == expected


def test_flask_client_ip_uses_leftmost_forwarded_address(app_module):
    """The request helper uses the normalized caller at the start of the chain."""
    with app_module.app.test_request_context(
        "/livez",
        headers={"X-Forwarded-For": "198.51.100.10, 192.0.2.45"},
        environ_base={"REMOTE_ADDR": "10.20.0.8"},
    ):
        assert app_module.get_client_ip() == "198.51.100.10"
