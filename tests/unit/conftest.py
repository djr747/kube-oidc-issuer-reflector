"""Shared fixtures and configuration for the unit test suite."""

import importlib
import os
import sys
from unittest.mock import MagicMock

import pytest

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


@pytest.fixture
def clean_env(monkeypatch):
    """Remove environment variables that affect application configuration."""
    for key in ("KUBERNETES_SERVICE_HOST", "ALLOWED_USER_AGENT", "DEFAULT_RATE_LIMIT"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def app_module(monkeypatch, clean_env):
    """Import app.main with kubernetes.config fully mocked."""
    mock_client = MagicMock()
    mock_config = MagicMock()
    mock_config.ConfigException = type("ConfigException", (Exception,), {})

    modules_to_patch = {
        "kubernetes": mock_client,
        "kubernetes.client": mock_client.client,
        "kubernetes.config": mock_config,
    }

    for mod_name, mod_obj in modules_to_patch.items():
        monkeypatch.setitem(sys.modules, mod_name, mod_obj)

    # Remove any cached app.main so the mocked kubernetes takes effect
    for mod in list(sys.modules.keys()):
        if mod.startswith("app."):
            del sys.modules[mod]

    import app.main

    importlib.reload(app.main)
    return app.main


@pytest.fixture
def client(app_module):
    """Return a Flask test client."""
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def mock_k8s_client(app_module, monkeypatch):
    """Mock get_k8s_client so it returns a mock client with all API groups."""
    mock_client_obj = MagicMock()
    monkeypatch.setattr(app_module, "get_k8s_client", lambda: mock_client_obj)
    return mock_client_obj
