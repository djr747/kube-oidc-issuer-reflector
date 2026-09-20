"""Unit tests for application and Gunicorn logging helpers."""

import logging
from unittest.mock import MagicMock


def test_endpoint_filter_excludes_its_path(app_module):
    """Health endpoint records are excluded from access logs."""
    record = logging.LogRecord("test", logging.INFO, "", 0, "GET /livez", (), None)

    assert app_module.EndpointFilter("/livez").filter(record) is False


def test_endpoint_filter_keeps_other_paths(app_module):
    """Non-health access records remain visible."""
    record = logging.LogRecord("test", logging.INFO, "", 0, "GET /openid/v1/jwks", (), None)

    assert app_module.EndpointFilter("/livez").filter(record) is True


def test_debug_logging_for_discovery(client, app_module, mock_k8s_client, caplog):
    """Discovery request details are logged when debug logging is enabled."""
    app_module.app.logger.setLevel(logging.DEBUG)
    api = MagicMock()
    api.get_service_account_issuer_open_id_configuration.return_value = MagicMock(
        data=b'{"issuer": "https://issuer.example.test", "jwks_uri": "https://issuer.example.test/openid/v1/jwks"}'
    )
    mock_k8s_client.WellKnownApi.return_value = api

    response = client.get("/.well-known/openid-configuration")

    assert response.status_code == 200
    assert "Incoming request" in caplog.text


def test_debug_logging_for_jwks(client, app_module, mock_k8s_client, caplog):
    """JWKS request details are logged when debug logging is enabled."""
    app_module.app.logger.setLevel(logging.DEBUG)
    api = MagicMock()
    api.get_service_account_issuer_open_id_keyset.return_value = MagicMock(data=b'{"keys": []}')
    mock_k8s_client.OpenidApi.return_value = api

    response = client.get("/openid/v1/jwks")

    assert response.status_code == 200
    assert "Incoming request" in caplog.text


def test_json_request_formatter_formats_access_record():
    """Gunicorn access records are converted to structured JSON fields."""
    from app.gunicorn_config import JsonRequestFormatter

    formatter = JsonRequestFormatter()
    record = MagicMock()
    record.args = {
        "t": "[30/Jul/2026:12:00:00 +0000]",
        "U": "/openid/v1/jwks",
        "q": "",
        "h": "192.0.2.1",
        "{X-Forwarded-For}i": "198.51.100.7, 192.0.2.1",
        "m": "GET",
        "s": "200",
        "a": "test-agent",
        "f": "-",
        "M": "12",
        "p": "1",
    }

    payload = formatter.json_record("request", {}, record)

    assert payload["path"] == "/openid/v1/jwks"
    assert payload["status"] == "200"
    assert payload["remote_ip"] == "198.51.100.7"
    assert payload["forwarded_for"] == "198.51.100.7, 192.0.2.1"


def test_json_request_formatter_includes_query_string():
    """Gunicorn access records retain the request query string."""
    from app.gunicorn_config import JsonRequestFormatter

    formatter = JsonRequestFormatter()
    record = MagicMock()
    record.args = {
        "t": "[30/Jul/2026:12:00:00 +0000]",
        "U": "/openid/v1/jwks",
        "q": "cache=false",
        "h": "192.0.2.1",
        "{X-Forwarded-For}i": "-",
        "m": "GET",
        "s": "200",
        "a": "test-agent",
        "f": "-",
        "M": "12",
        "p": "1",
    }

    payload = formatter.json_record("request", {}, record)

    assert payload["path"] == "/openid/v1/jwks?cache=false"


def test_json_error_formatter_adds_log_level():
    """Gunicorn error records include their severity in structured JSON."""
    from app.gunicorn_config import JsonErrorFormatter

    formatter = JsonErrorFormatter()
    record = logging.LogRecord("test", logging.ERROR, "", 0, "failure", (), None)

    payload = formatter.json_record("failure", {}, record)

    assert payload["level"] == "ERROR"
