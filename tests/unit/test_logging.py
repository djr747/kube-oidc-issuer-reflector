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


def test_exception_description_includes_type_and_message(app_module):
    """Exception descriptions are concise and useful in logs."""
    description = app_module.get_exception_description(ValueError("invalid value"))

    assert description == "ValueError: invalid value"


def test_debug_logging_for_discovery(client, app_module, mock_k8s_client, caplog):
    """Discovery request details are logged when debug logging is enabled."""
    app_module.app.logger.setLevel(logging.DEBUG)
    api = MagicMock()
    api.get_service_account_issuer_open_id_configuration.return_value = MagicMock(
        data=b'{"issuer": "https://issuer.example.test"}'
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
        "{X-Forwarded-For}i": "192.0.2.1",
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
    assert payload["remote_ip"] == "192.0.2.1"


def test_json_error_formatter_adds_log_level():
    """Gunicorn error records include their severity in structured JSON."""
    from app.gunicorn_config import JsonErrorFormatter

    formatter = JsonErrorFormatter()
    record = logging.LogRecord("test", logging.ERROR, "", 0, "failure", (), None)

    payload = formatter.json_record("failure", {}, record)

    assert payload["level"] == "ERROR"
