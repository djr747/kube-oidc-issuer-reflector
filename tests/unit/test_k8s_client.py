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

    def test_kube_config_exception_is_logged(self, app_module, monkeypatch, caplog):
        """A missing local kubeconfig is logged without preventing startup."""
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        config_exception = type("ConfigException", (Exception,), {})
        mock_config = MagicMock()
        mock_config.ConfigException = config_exception
        mock_config.load_kube_config.side_effect = config_exception("no kubeconfig")
        monkeypatch.setattr(app_module, "config", mock_config)

        result = app_module.get_k8s_client()

        assert result is app_module.client
        assert "no kubeconfig" in caplog.text
