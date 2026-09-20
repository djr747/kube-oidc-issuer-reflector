"""Unit tests for Kubernetes client configuration logic."""

from unittest.mock import MagicMock


class TestK8sClientConfig:
    """Tests for get_k8s_client configuration detection."""

    def test_incluster_config(self, app_module, monkeypatch):
        """Use in-cluster configuration when Kubernetes supplies its host variable."""
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
        mock_config = MagicMock()
        monkeypatch.setattr(app_module, "config", mock_config)

        result = app_module.get_k8s_client()

        mock_config.load_incluster_config.assert_called_once()
        assert result is app_module.client

    def test_kube_config_fallback(self, app_module, monkeypatch):
        """Use the local kubeconfig outside Kubernetes."""
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        mock_config = MagicMock()
        mock_config.ConfigException = type("ConfigException", (Exception,), {})
        monkeypatch.setattr(app_module, "config", mock_config)

        app_module.get_k8s_client()

        mock_config.load_kube_config.assert_called_once()
        mock_config.load_incluster_config.assert_not_called()

    def test_kube_config_exception_is_propagated(self, app_module, monkeypatch):
        """A missing local kubeconfig is propagated to the endpoint error handler."""
        import pytest

        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        config_exception = type("ConfigException", (Exception,), {})
        mock_config = MagicMock()
        mock_config.ConfigException = config_exception
        mock_config.load_kube_config.side_effect = config_exception("no kubeconfig")
        monkeypatch.setattr(app_module, "config", mock_config)

        with pytest.raises(config_exception, match="no kubeconfig"):
            app_module.get_k8s_client()


class TestKubernetesRequestTimeout:
    """Tests for Kubernetes API request timeout configuration."""

    def test_default_timeout(self, app_module):
        assert app_module.get_kubernetes_request_timeout() == 5

    def test_timeout_override_is_forwarded(self, client, mock_k8s_client, monkeypatch):
        monkeypatch.setenv("KUBERNETES_REQUEST_TIMEOUT_SECONDS", "1.5")
        api = mock_k8s_client.WellKnownApi.return_value
        api.get_service_account_issuer_open_id_configuration.return_value = MagicMock(
            data=b'{"issuer": "https://issuer.example", "jwks_uri": "https://issuer.example/openid/v1/jwks"}'
        )

        response = client.get("/.well-known/openid-configuration")

        assert response.status_code == 200
        api.get_service_account_issuer_open_id_configuration.assert_called_once_with(
            _preload_content=False, _request_timeout=1.5
        )
        api_client = mock_k8s_client.ApiClient.return_value
        mock_k8s_client.WellKnownApi.assert_called_once_with(api_client.__enter__.return_value)
        api_client.__exit__.assert_called_once()

    def test_non_positive_timeout_rejected(self, app_module, monkeypatch):
        import pytest

        monkeypatch.setenv("KUBERNETES_REQUEST_TIMEOUT_SECONDS", "0")

        with pytest.raises(ValueError, match="greater than zero"):
            app_module.get_kubernetes_request_timeout()

    def test_non_numeric_timeout_rejected(self, app_module, monkeypatch):
        import pytest

        monkeypatch.setenv("KUBERNETES_REQUEST_TIMEOUT_SECONDS", "fast")

        with pytest.raises(ValueError, match="must be a number"):
            app_module.get_kubernetes_request_timeout()
