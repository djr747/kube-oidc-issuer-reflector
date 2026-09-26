"""Kind integration tests for the deployed OIDC issuer reflector."""

import json
import os
import subprocess
import time
from typing import Any

import pytest

pytestmark = pytest.mark.integration

NAMESPACE = "kube-oidc-issuer-reflector"
SERVICE = "kube-oidc-issuer-reflector"
CONTEXT = os.environ.get("INTEGRATION_CONTEXT", "kind-oidc-reflector-integration")


def kubectl_command(*args: str) -> list[str]:
    """Pin every integration operation to the designated test context."""
    return ["kubectl", "--context", CONTEXT, *args]


@pytest.fixture(scope="session", autouse=True)
def require_disposable_kind_cluster():
    """Refuse destructive authorization tests outside the test cluster."""
    if not CONTEXT.startswith("kind-oidc-reflector-"):
        pytest.fail("Integration tests require a designated oidc-reflector Kind context")
    discovery = json.loads(run_kubectl("get", "--raw=/.well-known/openid-configuration"))
    if discovery.get("issuer") != "https://issuer.kind.test":
        pytest.fail("Integration tests require the disposable cluster's test issuer")


def run_kubectl(*args: str) -> str:
    """Run kubectl against the configured Kind context and return stdout."""
    result = subprocess.run(
        kubectl_command(*args), check=False, capture_output=True, text=True, env=os.environ.copy()
    )
    if result.returncode:
        pytest.fail(
            f"kubectl {' '.join(args)} failed with exit code {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def service_response(path: str) -> dict[str, Any]:
    """Fetch a Service endpoint through a temporary in-cluster curl pod."""
    probe_name = (
        "oidc-reflector-test-jwks" if path.endswith("jwks") else "oidc-reflector-test-discovery"
    )
    try:
        run_kubectl(
            "-n",
            NAMESPACE,
            "run",
            probe_name,
            "--restart=Never",
            "--image=curlimages/curl:8.12.1",
            "--",
            "curl",
            "--fail",
            "--silent",
            f"http://{SERVICE}.{NAMESPACE}.svc.cluster.local{path}",
        )

        for _ in range(240):
            pod = json.loads(run_kubectl("-n", NAMESPACE, "get", "pod", probe_name, "-o", "json"))
            phase = pod["status"].get("phase")
            if phase in {"Succeeded", "Failed"}:
                output = run_kubectl("-n", NAMESPACE, "logs", probe_name)
                if phase == "Failed":
                    pytest.fail(f"probe pod {probe_name} failed:\n{output}")
                return json.loads(output)
            time.sleep(0.5)

        pytest.fail(f"probe pod {probe_name} did not finish within 120 seconds")
    finally:
        subprocess.run(
            kubectl_command(
                "-n",
                NAMESPACE,
                "delete",
                "pod",
                probe_name,
                "--ignore-not-found",
                "--wait=true",
            ),
            check=False,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )


def test_effective_service_account_authorization():
    """The deployed service account has effective access to OIDC API endpoints."""
    service_account = f"system:serviceaccount:{NAMESPACE}:{SERVICE}"
    service_account_groups = (
        "--as-group=system:serviceaccounts",
        f"--as-group=system:serviceaccounts:{NAMESPACE}",
        "--as-group=system:authenticated",
    )

    discovery = run_kubectl(
        "auth",
        "can-i",
        "get",
        "/.well-known/openid-configuration",
        "--as",
        service_account,
        *service_account_groups,
    ).strip()
    jwks = run_kubectl(
        "auth",
        "can-i",
        "get",
        "/openid/v1/jwks",
        "--as",
        service_account,
        *service_account_groups,
    ).strip()

    assert discovery == "yes"
    assert jwks == "yes"


def test_reflects_discovery_document():
    """The Service reflects the API server discovery document unchanged."""
    expected = json.loads(run_kubectl("get", "--raw=/.well-known/openid-configuration"))
    actual = service_response("/.well-known/openid-configuration")

    assert actual == expected
    assert actual["issuer"] == "https://issuer.kind.test"


def test_reflects_jwks_document():
    """The Service reflects the API server JWKS document unchanged."""
    expected = json.loads(run_kubectl("get", "--raw=/openid/v1/jwks"))
    actual = service_response("/openid/v1/jwks")

    assert actual == expected
    assert actual["keys"]


def test_deployment_is_ready_and_non_root():
    """All replicas are ready and the runtime user is the Chainguard non-root UID."""
    deployment = json.loads(
        run_kubectl("-n", NAMESPACE, "get", "deployment", SERVICE, "-o", "json")
    )
    labels = deployment["spec"]["selector"]["matchLabels"]
    selector = ",".join(f"{key}={value}" for key, value in labels.items())
    pods = json.loads(run_kubectl("-n", NAMESPACE, "get", "pods", "-l", selector, "-o", "json"))

    assert deployment["status"]["readyReplicas"] == 2
    assert len(pods["items"]) == 2
    for pod in pods["items"]:
        assert pod["status"]["containerStatuses"][0]["restartCount"] == 0
        assert pod["spec"]["securityContext"]["runAsUser"] == 65532


def test_serves_stale_documents_after_oidc_api_access_is_revoked():
    """Cached documents remain available through API authorization failures."""
    expected_discovery = json.loads(run_kubectl("get", "--raw=/.well-known/openid-configuration"))
    expected_jwks = json.loads(run_kubectl("get", "--raw=/openid/v1/jwks"))

    # Readiness has populated each single-worker pod's cache during rollout.
    assert service_response("/.well-known/openid-configuration") == expected_discovery
    assert service_response("/openid/v1/jwks") == expected_jwks
    time.sleep(0.01)

    service_account = f"system:serviceaccount:{NAMESPACE}:{SERVICE}"
    service_account_groups = (
        "--as-group=system:serviceaccounts",
        f"--as-group=system:serviceaccounts:{NAMESPACE}",
        "--as-group=system:authenticated",
    )
    bindings = (
        "kube-oidc-issuer-reflector-discovery",
        "system:service-account-issuer-discovery",
    )
    run_kubectl("delete", "clusterrolebinding", *bindings)

    try:
        for path in ("/.well-known/openid-configuration", "/openid/v1/jwks"):
            result = subprocess.run(
                kubectl_command(
                    "auth",
                    "can-i",
                    "get",
                    path,
                    "--as",
                    service_account,
                    *service_account_groups,
                ),
                check=False,
                capture_output=True,
                text=True,
                env=os.environ.copy(),
            )
            assert result.returncode == 1
            assert result.stdout.strip() == "no"

        assert service_response("/.well-known/openid-configuration") == expected_discovery
        assert service_response("/openid/v1/jwks") == expected_jwks
    finally:
        run_kubectl(
            "create",
            "clusterrolebinding",
            "kube-oidc-issuer-reflector-discovery",
            "--clusterrole=system:service-account-issuer-discovery",
            f"--serviceaccount={NAMESPACE}:{SERVICE}",
        )
        run_kubectl(
            "create",
            "clusterrolebinding",
            "system:service-account-issuer-discovery",
            "--clusterrole=system:service-account-issuer-discovery",
            "--group=system:serviceaccounts",
        )
