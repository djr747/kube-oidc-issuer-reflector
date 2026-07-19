"""Offline test for the /readyz readiness probe endpoint.

Neutralizes Kubernetes configuration before importing app.main so that
no cluster access is required to exercise the Flask test client.
"""

import os
import sys

# Ensure the repository root is on sys.path so `from app.main import app`
# works when pytest runs from the repository root.  Compute it relative to
# this file so the path stays valid even if the repo is moved.
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from unittest.mock import patch, MagicMock

# Neutralize Kubernetes configuration before importing app.main.
os.environ["KUBERNETES_SERVICE_HOST"] = ""

# Mock the kubernetes config module to prevent any cluster connection attempts.
with patch("kubernetes.config") as mock_config:
    mock_config.load_incluster_config.side_effect = Exception("no cluster")
    mock_config.load_kube_config.side_effect = Exception("no kubeconfig")

    from app.main import app  # noqa: E402


def test_readiness():
    """GET /readyz should return HTTP 200 with the expected readiness body."""
    client = app.test_client()
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.data.decode("utf-8") == "I am ready!"
