"""Unit tests for the health endpoints (/livez and /readyz)."""

import json
from unittest.mock import MagicMock


class TestLiveness:
    """Tests for /livez."""

    def test_liveness_returns_200(self, client):
        """Liveness probe returns 200 without making Kubernetes API calls."""
        response = client.get("/livez")
        assert response.status_code == 200
        assert b"I am alive!" in response.data

    def test_liveness_excluded_from_rate_limiting(self, app_module, mock_k8s_client, monkeypatch):
        """Liveness probe is exempt from rate limiting."""
        monkeypatch.setenv("DEFAULT_RATE_LIMIT", "1 per minute")
        import importlib

        importlib.reload(app_module)
        app_module.app.config["TESTING"] = True
        test_client = app_module.app.test_client()

        for _ in range(5):
            response = test_client.get("/livez")
            assert response.status_code == 200


class TestReadiness:
    """Tests for /readyz."""

    def test_readiness_success(self, client, mock_k8s_client):
        """Readiness probe returns 200 when OIDC discovery is accessible."""
        discovery_doc = {"issuer": "https://issuer.example.com"}
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_configuration.return_value = MagicMock(
            data=json.dumps(discovery_doc).encode()
        )
        mock_k8s_client.WellKnownApi.return_value = mock_api
        mock_k8s_client.OpenidApi.return_value.get_service_account_issuer_open_id_keyset.return_value = MagicMock(
            data=b'{"keys": []}'
        )

        response = client.get("/readyz")
        assert response.status_code == 200
        assert b"I am ready!" in response.data

    def test_readiness_failure_returns_503(self, client, mock_k8s_client):
        """Readiness probe returns 503 when Kubernetes API fails."""
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_configuration.side_effect = Exception(
            "API error"
        )
        mock_k8s_client.WellKnownApi.return_value = mock_api

        response = client.get("/readyz")
        assert response.status_code == 503
        assert b"I am not ready!" in response.data

    def test_readiness_malformed_json_returns_503(self, client, mock_k8s_client):
        """Readiness probe returns 503 when upstream returns invalid JSON."""
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_configuration.return_value = MagicMock(
            data=b"not json"
        )
        mock_k8s_client.WellKnownApi.return_value = mock_api

        response = client.get("/readyz")
        assert response.status_code == 503

    def test_readiness_excluded_from_rate_limiting(self, client, mock_k8s_client):
        """Readiness probe is exempt from rate limiting."""
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_configuration.return_value = MagicMock(
            data=b'{"issuer": "ok"}'
        )
        mock_k8s_client.WellKnownApi.return_value = mock_api
        mock_k8s_client.OpenidApi.return_value.get_service_account_issuer_open_id_keyset.return_value = MagicMock(
            data=b'{"keys": []}'
        )

        for _ in range(5):
            response = client.get("/readyz")
            assert response.status_code == 200
