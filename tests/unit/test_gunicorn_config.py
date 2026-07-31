"""Unit tests for Gunicorn configuration."""

import importlib


def test_gunicorn_defaults(monkeypatch):
    """Gunicorn config defaults are loaded from environment or use standard values."""
    for key in ("LOG_LEVEL", "GUNICORN_PROCESSES", "GUNICORN_THREADS", "GUNICORN_TIMEOUT"):
        monkeypatch.delenv(key, raising=False)

    from app import gunicorn_config

    assert gunicorn_config.loglevel == "INFO"
    assert gunicorn_config.workers == 2
    assert gunicorn_config.threads == 4
    assert gunicorn_config.timeout == 120
    assert gunicorn_config.forwarded_allow_ips == "*"
    assert gunicorn_config.accesslog == "-"
    assert gunicorn_config.errorlog == "-"
    assert gunicorn_config.bind == "0.0.0.0:8080"


def test_gunicorn_env_overrides(monkeypatch):
    """Gunicorn config reads overrides from environment variables."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("GUNICORN_PROCESSES", "4")
    monkeypatch.setenv("GUNICORN_THREADS", "8")
    monkeypatch.setenv("GUNICORN_TIMEOUT", "60")

    from app import gunicorn_config

    importlib.reload(gunicorn_config)

    assert gunicorn_config.loglevel == "DEBUG"
    assert gunicorn_config.workers == 4
    assert gunicorn_config.threads == 8
    assert gunicorn_config.timeout == 60


def test_gunicorn_logconfig_dict_structure():
    """The Gunicorn logconfig dict has JSON formatters and stream handlers."""
    from app.gunicorn_config import logconfig_dict

    assert "formatters" in logconfig_dict
    assert "handlers" in logconfig_dict
    assert "loggers" in logconfig_dict
    assert "json_request" in logconfig_dict["formatters"]
    assert "json_error" in logconfig_dict["formatters"]
    assert "gunicorn.access" in logconfig_dict["loggers"]
    assert "gunicorn.error" in logconfig_dict["loggers"]


def test_gunicorn_access_logger_filtered(app_module):
    """The gunicorn.access logger has EndpointFilters for /livez and /readyz."""
    import logging

    access_logger = logging.getLogger("gunicorn.access")
    filters = access_logger.filters
    paths = [f._path for f in filters if hasattr(f, "_path")]
    assert "/livez" in paths
    assert "/readyz" in paths
