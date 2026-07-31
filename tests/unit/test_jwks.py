"""Unit tests for the JWKS endpoint (/openid/v1/jwks)."""

import json
from unittest.mock import MagicMock


class TestJwks:
    """Tests for /openid/v1/jwks."""

    def test_success(self, client, mock_k8s_client):
        """JWKS endpoint reflects the Kubernetes API response as JSON."""
        jwks_doc = {
            "keys": [
                {
                    "kid": "test-key-id",
                    "kty": "RSA",
                    "n": "modulus",
                    "e": "AQAB",
                }
            ]
        }
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_keyset.return_value = MagicMock(
            data=json.dumps(jwks_doc).encode()
        )
        mock_k8s_client.OpenidApi.return_value = mock_api

        response = client.get("/openid/v1/jwks")

        assert response.status_code == 200
        body = response.get_json()
        assert "keys" in body
        assert len(body["keys"]) == 1
        assert body["keys"][0]["kid"] == "test-key-id"

    def test_kubernetes_exception_returns_500(self, client, mock_k8s_client):
        """JWKS endpoint returns 500 when the Kubernetes API fails."""
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_keyset.side_effect = Exception("API error")
        mock_k8s_client.OpenidApi.return_value = mock_api

        response = client.get("/openid/v1/jwks")

        assert response.status_code == 500
        assert b"Internal error check logs" in response.data

    def test_malformed_json_returns_500(self, client, mock_k8s_client):
        """JWKS endpoint returns 500 when upstream returns invalid JSON."""
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_keyset.return_value = MagicMock(
            data=b"not json"
        )
        mock_k8s_client.OpenidApi.return_value = mock_api

        response = client.get("/openid/v1/jwks")

        assert response.status_code == 500

    def test_allowed_user_agent_match(self, client, mock_k8s_client, monkeypatch):
        """JWKS endpoint allows requests with the correct User-Agent."""
        monkeypatch.setenv("ALLOWED_USER_AGENT", "my-agent/1.0")

        jwks_doc = {"keys": [{"kid": "key1", "kty": "RSA"}]}
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_keyset.return_value = MagicMock(
            data=json.dumps(jwks_doc).encode()
        )
        mock_k8s_client.OpenidApi.return_value = mock_api

        response = client.get(
            "/openid/v1/jwks",
            headers={"User-Agent": "my-agent/1.0"},
        )
        assert response.status_code == 200

    def test_allowed_user_agent_mismatch(self, client, mock_k8s_client, monkeypatch):
        """JWKS endpoint returns 403 when User-Agent does not match."""
        monkeypatch.setenv("ALLOWED_USER_AGENT", "my-agent/1.0")

        response = client.get(
            "/openid/v1/jwks",
            headers={"User-Agent": "wrong-agent/1.0"},
        )
        assert response.status_code == 403

    def test_no_user_agent_restriction(self, client, mock_k8s_client, monkeypatch):
        """JWKS endpoint allows any request when ALLOWED_USER_AGENT is unset."""
        monkeypatch.delenv("ALLOWED_USER_AGENT", raising=False)

        jwks_doc = {"keys": [{"kid": "key1", "kty": "RSA"}]}
        mock_api = MagicMock()
        mock_api.get_service_account_issuer_open_id_keyset.return_value = MagicMock(
            data=json.dumps(jwks_doc).encode()
        )
        mock_k8s_client.OpenidApi.return_value = mock_api

        response = client.get(
            "/openid/v1/jwks",
            headers={"User-Agent": "any-agent"},
        )
        assert response.status_code == 200
