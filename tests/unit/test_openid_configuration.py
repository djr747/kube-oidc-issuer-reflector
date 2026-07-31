"""Unit tests for the OIDC discovery endpoint (/.well-known/openid-configuration)."""

import json
from unittest.mock import MagicMock


class TestOpenIdConfiguration:
    """Tests for /.well-known/openid-configuration."""

    def test_success(self, client, mock_k8s_client):
        """Discovery endpoint reflects the Kubernetes API response as JSON."""
        discovery_doc = {
            "issuer": "https://issuer.example.com",
            "jwks_uri": "https://issuer.example.com/openid/v1/jwks",
        }
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_configuration.return_value = MagicMock(
            data=json.dumps(discovery_doc).encode()
        )
        mock_k8s_client.WellKnownApi.return_value = mock_api

        response = client.get("/.well-known/openid-configuration")

        assert response.status_code == 200
        body = response.get_json()
        assert body["issuer"] == "https://issuer.example.com"
        assert body["jwks_uri"] == "https://issuer.example.com/openid/v1/jwks"

    def test_kubernetes_exception_returns_500(self, client, mock_k8s_client):
        """Discovery endpoint returns 500 when the Kubernetes API fails."""
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_configuration.side_effect = Exception(
            "API error"
        )
        mock_k8s_client.WellKnownApi.return_value = mock_api

        response = client.get("/.well-known/openid-configuration")

        assert response.status_code == 500
        assert b"Internal error check logs" in response.data

    def test_malformed_json_returns_500(self, client, mock_k8s_client):
        """Discovery endpoint returns 500 when upstream returns invalid JSON."""
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_configuration.return_value = MagicMock(
            data=b"not json"
        )
        mock_k8s_client.WellKnownApi.return_value = mock_api

        response = client.get("/.well-known/openid-configuration")

        assert response.status_code == 500

    def test_allowed_user_agent_match(self, client, mock_k8s_client, monkeypatch):
        """Discovery endpoint allows requests with the correct User-Agent."""
        monkeypatch.setenv("ALLOWED_USER_AGENT", "my-agent/1.0")
        client.application.config["TESTING"] = True

        discovery_doc = {"issuer": "https://issuer.example.com"}
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_configuration.return_value = MagicMock(
            data=json.dumps(discovery_doc).encode()
        )
        mock_k8s_client.WellKnownApi.return_value = mock_api

        response = client.get(
            "/.well-known/openid-configuration",
            headers={"User-Agent": "my-agent/1.0"},
        )
        assert response.status_code == 200

    def test_allowed_user_agent_mismatch(self, client, mock_k8s_client, monkeypatch):
        """Discovery endpoint returns 403 when User-Agent does not match."""
        monkeypatch.setenv("ALLOWED_USER_AGENT", "my-agent/1.0")

        response = client.get(
            "/.well-known/openid-configuration",
            headers={"User-Agent": "wrong-agent/1.0"},
        )
        assert response.status_code == 403

    def test_allowed_user_agent_missing(self, client, mock_k8s_client, monkeypatch):
        """Discovery endpoint returns 403 when User-Agent is required but missing."""
        monkeypatch.setenv("ALLOWED_USER_AGENT", "my-agent/1.0")

        response = client.get("/.well-known/openid-configuration")
        assert response.status_code == 403

    def test_no_user_agent_restriction(self, client, mock_k8s_client, monkeypatch):
        """Discovery endpoint allows any request when ALLOWED_USER_AGENT is unset."""
        monkeypatch.delenv("ALLOWED_USER_AGENT", raising=False)

        discovery_doc = {"issuer": "https://issuer.example.com"}
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_configuration.return_value = MagicMock(
            data=json.dumps(discovery_doc).encode()
        )
        mock_k8s_client.WellKnownApi.return_value = mock_api

        response = client.get(
            "/.well-known/openid-configuration",
            headers={"User-Agent": "any-agent"},
        )
        assert response.status_code == 200
