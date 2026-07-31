"""Unit tests for rate limiting behavior."""

import json
from unittest.mock import MagicMock


class TestRateLimiting:
    """Tests for flask_limiter enforcement and exemptions."""

    def test_oidc_endpoints_rate_limited(self, app_module, mock_k8s_client, monkeypatch):
        """OIDC discovery endpoint returns 429 after exceeding the rate limit."""
        monkeypatch.setenv("DEFAULT_RATE_LIMIT", "2 per minute")

        import importlib

        importlib.reload(app_module)

        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_configuration.return_value = MagicMock(
            data=json.dumps({"issuer": "ok"}).encode()
        )
        mock_k8s_client.WellKnownApi.return_value = mock_api

        app_module.app.config["TESTING"] = True
        test_client = app_module.app.test_client()

        # First two should succeed
        test_client.get("/.well-known/openid-configuration")
        test_client.get("/.well-known/openid-configuration")
        # Third should be rate limited (429)
        r3 = test_client.get("/.well-known/openid-configuration")

        assert r3.status_code == 429

    def test_jwks_endpoints_rate_limited(self, app_module, mock_k8s_client, monkeypatch):
        """JWKS endpoint returns 429 after exceeding the rate limit."""
        monkeypatch.setenv("DEFAULT_RATE_LIMIT", "1 per minute")

        import importlib

        importlib.reload(app_module)

        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_keyset.return_value = MagicMock(
            data=json.dumps({"keys": []}).encode()
        )
        mock_k8s_client.OpenidApi.return_value = mock_api

        app_module.app.config["TESTING"] = True
        test_client = app_module.app.test_client()

        test_client.get("/openid/v1/jwks")
        r2 = test_client.get("/openid/v1/jwks")

        assert r2.status_code == 429
