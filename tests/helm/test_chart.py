"""Render the release archive and check supported Helm configuration."""

import os
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.helm

ROOT = Path(__file__).resolve().parents[2]
HELM = os.environ.get("HELM_BIN", "helm")
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
DEFAULTS = yaml.safe_load((ROOT / "charts/kube-oidc-issuer-reflector/values.yaml").read_text())
RELEASE = "kube-oidc-issuer-reflector"
NAMESPACE = "chart-test"


@pytest.fixture(scope="module")
def chart_archive(tmp_path_factory):
    destination = tmp_path_factory.mktemp("helm-package")
    subprocess.run(
        [
            HELM,
            "package",
            str(ROOT / "charts/kube-oidc-issuer-reflector"),
            "--version",
            VERSION,
            "--app-version",
            VERSION,
            "--destination",
            str(destination),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return destination / f"{RELEASE}-{VERSION}.tgz"


@pytest.fixture
def render_chart(chart_archive, tmp_path):
    def render(values=None, *, check=True):
        values_file = tmp_path / "values.yaml"
        values_file.write_text(yaml.safe_dump(values or {}))
        result = subprocess.run(
            [
                HELM,
                "template",
                RELEASE,
                str(chart_archive),
                "--namespace",
                NAMESPACE,
                "--values",
                str(values_file),
            ],
            check=check,
            capture_output=True,
            text=True,
        )
        if not check:
            return result
        return {
            document["kind"]: document for document in yaml.safe_load_all(result.stdout) if document
        }

    return render


def test_release_metadata_and_default_workload(chart_archive, render_chart):
    metadata = yaml.safe_load(
        subprocess.run(
            [HELM, "show", "chart", str(chart_archive)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    assert metadata["version"] == VERSION
    assert metadata["appVersion"] == VERSION
    documents = render_chart()
    assert set(documents) == {
        "Deployment",
        "Service",
        "ServiceAccount",
        "ClusterRoleBinding",
        "PodDisruptionBudget",
    }
    deployment = documents["Deployment"]
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert container["image"] == f"ghcr.io/djr747/{RELEASE}:{VERSION}"
    assert pod["securityContext"] == DEFAULTS["podSecurityContext"]
    assert container["securityContext"] == DEFAULTS["containerSecurityContext"]
    assert container["resources"] == DEFAULTS["resources"]
    assert container["livenessProbe"] == DEFAULTS["livenessProbe"]
    assert container["readinessProbe"] == DEFAULTS["readinessProbe"]
    assert deployment["spec"]["replicas"] == 2
    assert pod["automountServiceAccountToken"] is True
    assert pod["enableServiceLinks"] is False
    labels = deployment["spec"]["template"]["metadata"]["labels"]
    assert deployment["spec"]["selector"]["matchLabels"].items() <= labels.items()
    assert documents["Service"]["spec"]["selector"].items() <= labels.items()


def test_all_application_configuration_overrides(render_chart):
    documents = render_chart(
        {
            "config": {
                "defaultRateLimit": "25 per minute",
                "allowedUserAgent": "example-validator",
                "kubernetesRequestTimeoutSeconds": 2.5,
                "logLevel": "DEBUG",
                "gunicornProcesses": 3,
                "gunicornThreads": 6,
                "gunicornTimeout": 60,
            },
            "oidcDocumentCache": {
                "ttlSeconds": 12.5,
                "staleIfErrorSeconds": 90,
                "errorBackoffSeconds": 2,
                "maxDocumentBytes": 2097152,
            },
            "extraEnv": [{"name": "EXAMPLE_SETTING", "value": "extra"}],
        }
    )
    env = documents["Deployment"]["spec"]["template"]["spec"]["containers"][0]["env"]
    assert {entry["name"]: entry["value"] for entry in env} == {
        "DEFAULT_RATE_LIMIT": "25 per minute",
        "ALLOWED_USER_AGENT": "example-validator",
        "KUBERNETES_REQUEST_TIMEOUT_SECONDS": "2.5",
        "LOG_LEVEL": "DEBUG",
        "GUNICORN_PROCESSES": "3",
        "GUNICORN_THREADS": "6",
        "GUNICORN_TIMEOUT": "60",
        "OIDC_DOCUMENT_CACHE_TTL_SECONDS": "12.5",
        "OIDC_DOCUMENT_CACHE_STALE_IF_ERROR_SECONDS": "90",
        "OIDC_DOCUMENT_CACHE_ERROR_BACKOFF_SECONDS": "2",
        "OIDC_DOCUMENT_CACHE_MAX_DOCUMENT_BYTES": "2097152",
        "EXAMPLE_SETTING": "extra",
    }


def test_deployment_overrides(render_chart):
    documents = render_chart(
        {
            "replicaCount": 3,
            "image": {"repository": "example/reflector", "tag": "candidate", "pullPolicy": "Never"},
            "podAnnotations": {"example.com/annotation": "value"},
            "podLabels": {"example.com/label": "value"},
            "resources": {"requests": {"cpu": "100m"}, "limits": {"cpu": "1"}},
            "readinessProbe": {"timeoutSeconds": 20},
            "livenessProbe": {"periodSeconds": 15},
            "revisionHistoryLimit": 5,
            "minReadySeconds": 10,
            "strategy": {"rollingUpdate": {"maxSurge": 2}},
            "tmp": {"sizeLimit": "32Mi"},
            "service": {"port": 8081},
            "podDisruptionBudget": {"enabled": False},
        }
    )
    deployment = documents["Deployment"]
    template = deployment["spec"]["template"]
    pod = template["spec"]
    container = pod["containers"][0]
    assert deployment["spec"]["replicas"] == 3
    assert deployment["spec"]["revisionHistoryLimit"] == 5
    assert deployment["spec"]["minReadySeconds"] == 10
    assert deployment["spec"]["strategy"]["rollingUpdate"]["maxSurge"] == 2
    assert template["metadata"]["annotations"]["example.com/annotation"] == "value"
    assert template["metadata"]["labels"]["example.com/label"] == "value"
    assert container["image"] == "example/reflector:candidate"
    assert container["imagePullPolicy"] == "Never"
    assert container["resources"]["requests"]["cpu"] == "100m"
    assert container["resources"]["limits"]["cpu"] == "1"
    assert container["readinessProbe"]["timeoutSeconds"] == 20
    assert container["livenessProbe"]["periodSeconds"] == 15
    assert pod["volumes"][0]["emptyDir"]["sizeLimit"] == "32Mi"
    assert documents["Service"]["spec"]["ports"][0]["port"] == 8081
    assert "PodDisruptionBudget" not in documents


@pytest.mark.parametrize(
    ("create", "binding"), [(True, True), (True, False), (False, True), (False, False)]
)
def test_service_account_and_rbac_are_independent(render_chart, create, binding):
    documents = render_chart(
        {
            "serviceAccount": {"create": create, "name": "existing-account", "automount": True},
            "rbac": {"create": binding},
        }
    )
    pod = documents["Deployment"]["spec"]["template"]["spec"]
    assert pod["serviceAccountName"] == "existing-account"
    assert pod["automountServiceAccountToken"] is True
    assert ("ServiceAccount" in documents) is create
    assert ("ClusterRoleBinding" in documents) is binding
    if binding:
        assert (
            documents["ClusterRoleBinding"]["roleRef"]["name"]
            == "system:service-account-issuer-discovery"
        )
        assert documents["ClusterRoleBinding"]["subjects"] == [
            {"kind": "ServiceAccount", "name": "existing-account", "namespace": NAMESPACE}
        ]


@pytest.mark.parametrize("tls", [True, False])
def test_ingress_hosts_tls_and_annotations(render_chart, tls):
    documents = render_chart(
        {
            "ingress": {
                "enabled": True,
                "host": "oidc.example.com",
                "additionalHosts": ["alias.example.com"],
                "className": "internal-gateway",
                "annotations": {"example.com/setting": "enabled"},
                "tls": {"enabled": tls, "secretName": "issuer-tls"},
            },
        }
    )
    ingress = documents["Ingress"]
    assert ingress["metadata"]["annotations"]["example.com/setting"] == "enabled"
    assert ingress["spec"]["ingressClassName"] == "internal-gateway"
    assert [rule["host"] for rule in ingress["spec"]["rules"]] == [
        "oidc.example.com",
        "alias.example.com",
    ]
    for rule in ingress["spec"]["rules"]:
        assert [(path["path"], path["pathType"]) for path in rule["http"]["paths"]] == [
            ("/.well-known/openid-configuration", "Exact"),
            ("/openid/v1/jwks", "Exact"),
        ]
    assert ("tls" in ingress["spec"]) is tls
    if tls:
        assert ingress["spec"]["tls"] == [
            {"hosts": ["oidc.example.com", "alias.example.com"], "secretName": "issuer-tls"}
        ]


def test_gateway_routes_and_backend_port(render_chart):
    documents = render_chart(
        {
            "gateway": {
                "enabled": True,
                "name": "private-gateway",
                "namespace": "edge",
                "sectionName": "https",
                "host": "oidc.example.com",
            },
            "service": {"port": 8081},
        }
    )
    route = documents["HTTPRoute"]["spec"]
    assert route["parentRefs"] == [
        {"name": "private-gateway", "namespace": "edge", "sectionName": "https"}
    ]
    assert route["hostnames"] == ["oidc.example.com"]
    assert [rule["matches"][0]["path"] for rule in route["rules"]] == [
        {"type": "Exact", "value": "/.well-known/openid-configuration"},
        {"type": "Exact", "value": "/openid/v1/jwks"},
    ]
    for rule in route["rules"]:
        assert rule["backendRefs"] == [{"name": RELEASE, "port": 8081}]


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (
            {
                "ingress": {"enabled": True, "host": "oidc.example.com"},
                "gateway": {"enabled": True, "name": "edge", "host": "oidc.example.com"},
            },
            "enable either ingress or gateway",
        ),
        ({"ingress": {"enabled": True}}, "ingress.host is required"),
        ({"gateway": {"enabled": True}}, "gateway.name is required"),
        ({"gateway": {"enabled": True, "name": "edge"}}, "gateway.host is required"),
        ({"serviceAccount": {"create": False}}, "serviceAccount.name must be set"),
    ],
)
def test_invalid_route_and_account_combinations_fail(render_chart, values, message):
    result = render_chart(values, check=False)
    assert result.returncode != 0
    assert message in result.stderr
