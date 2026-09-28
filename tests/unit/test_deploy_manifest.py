"""Unit tests for the Kubernetes deployment and optional edge manifests."""

import tomllib
from pathlib import Path

import pytest
import yaml

_DEPLOY_FILE = Path(__file__).parent.parent.parent / "deploy" / "deploy.yaml"
_INGRESS_FILE = Path(__file__).parent.parent.parent / "deploy" / "optional-ingress.yaml"
_GATEWAY_FILE = Path(__file__).parent.parent.parent / "deploy" / "optional-gateway-api.yaml"
_CERT_ISSUER_FILE = (
    Path(__file__).parent.parent.parent / "deploy" / "optional-ingress-cert-issuer.yaml"
)
_PROJECT_FILE = Path(__file__).parent.parent.parent / "pyproject.toml"
_PROJECT_VERSION = tomllib.loads(_PROJECT_FILE.read_text())["project"]["version"]
_LOCKED_PROJECT_VERSION = next(
    package["version"]
    for package in tomllib.loads((_PROJECT_FILE.parent / "uv.lock").read_text())["package"]
    if package["name"] == "kube-oidc-issuer-reflector"
)


def _load_documents(path=_DEPLOY_FILE):
    """Load all YAML documents from a deployment manifest."""
    with open(path) as f:
        return list(yaml.safe_load_all(f))


def _find_kind(docs, kind):
    """Return the first document of the given kind."""
    for doc in docs:
        if doc and doc.get("kind") == kind:
            return doc
    return None


class TestManifestStructure:
    """Validate structural correctness of deploy.yaml."""

    @pytest.fixture
    def docs(self):
        return _load_documents()

    def test_all_documents_valid(self, docs):
        """Every YAML document parses to a non-empty dict or None (separator)."""
        for doc in docs:
            assert doc is None or isinstance(doc, dict)

    def test_namespace_exists(self, docs):
        """A Namespace resource is defined."""
        ns = _find_kind(docs, "Namespace")
        assert ns is not None
        assert ns["metadata"]["name"] == "kube-oidc-issuer-reflector"

    def test_service_account_exists(self, docs):
        """A ServiceAccount is defined in the correct namespace."""
        sa = _find_kind(docs, "ServiceAccount")
        assert sa is not None
        assert sa["metadata"]["name"] == "kube-oidc-issuer-reflector"
        assert sa["metadata"]["namespace"] == "kube-oidc-issuer-reflector"

    def test_no_ineffective_namespaced_rbac(self, docs):
        """Non-resource OIDC URLs rely on Kubernetes' built-in discovery ClusterRole."""
        assert _find_kind(docs, "Role") is None
        assert _find_kind(docs, "RoleBinding") is None

    def test_deployment_exists(self, docs):
        """A Deployment is defined with correct selectors and probes."""
        dep = _find_kind(docs, "Deployment")
        assert dep is not None
        assert dep["metadata"]["namespace"] == "kube-oidc-issuer-reflector"

        spec = dep["spec"]
        assert spec["replicas"] == 2
        assert spec["selector"]["matchLabels"]["app"] == "kube-oidc-issuer-reflector"
        assert spec["template"]["metadata"]["labels"]["app"] == "kube-oidc-issuer-reflector"

    def test_deployment_uses_service_account(self, docs):
        """The Deployment pod template references the correct ServiceAccount."""
        dep = _find_kind(docs, "Deployment")
        template_spec = dep["spec"]["template"]["spec"]
        assert template_spec["serviceAccountName"] == "kube-oidc-issuer-reflector"

    def test_deployment_probes(self, docs):
        """Liveness and readiness probes are configured on the correct paths and ports."""
        dep = _find_kind(docs, "Deployment")
        container = dep["spec"]["template"]["spec"]["containers"][0]

        liveness = container["livenessProbe"]
        assert liveness["httpGet"]["path"] == "/livez"
        assert liveness["httpGet"]["port"] == 8080

        readiness = container["readinessProbe"]
        assert readiness["httpGet"]["path"] == "/readyz"
        assert readiness["httpGet"]["port"] == 8080
        assert readiness["timeoutSeconds"] > 10

    def test_deployment_resources(self, docs):
        """Container resources have requests and limits set."""
        dep = _find_kind(docs, "Deployment")
        container = dep["spec"]["template"]["spec"]["containers"][0]
        resources = container["resources"]

        assert "requests" in resources
        assert "limits" in resources
        assert "memory" in resources["requests"]
        assert "cpu" in resources["requests"]
        assert "memory" in resources["limits"]
        assert "cpu" in resources["limits"]

    def test_deployment_uses_canonical_image_and_hardening(self, docs):
        """The deployment runs the canonical non-root Chainguard image configuration."""
        dep = _find_kind(docs, "Deployment")
        pod_spec = dep["spec"]["template"]["spec"]
        container = pod_spec["containers"][0]

        assert container["image"] == (
            f"ghcr.io/djr747/kube-oidc-issuer-reflector:{_PROJECT_VERSION}"
        )
        assert _LOCKED_PROJECT_VERSION == _PROJECT_VERSION
        assert container["imagePullPolicy"] == "IfNotPresent"
        assert "env" not in container
        assert pod_spec["enableServiceLinks"] is False
        assert pod_spec["securityContext"]["runAsNonRoot"] is True
        assert pod_spec["securityContext"]["runAsUser"] == 65532
        assert container["securityContext"]["allowPrivilegeEscalation"] is False
        assert container["securityContext"]["readOnlyRootFilesystem"] is True

        assert container["volumeMounts"] == [{"name": "tmp", "mountPath": "/tmp"}]
        assert pod_spec["volumes"] == [
            {"name": "tmp", "emptyDir": {"medium": "Memory", "sizeLimit": "16Mi"}}
        ]

    def test_service_exists(self, docs):
        """A Service routes traffic to the Deployment on the correct port."""
        svc = _find_kind(docs, "Service")
        assert svc is not None
        assert svc["spec"]["selector"]["app"] == "kube-oidc-issuer-reflector"

        ports = svc["spec"]["ports"]
        assert len(ports) == 1
        assert ports[0]["port"] == 80
        assert ports[0]["targetPort"] == 8080

    def test_pod_disruption_budget_preserves_one_replica(self, docs):
        """Voluntary disruptions keep at least one reflector replica available."""
        pdb = _find_kind(docs, "PodDisruptionBudget")
        assert pdb is not None
        assert pdb["spec"]["minAvailable"] == 1
        assert pdb["spec"]["selector"]["matchLabels"]["app"] == "kube-oidc-issuer-reflector"

    def test_core_manifest_does_not_choose_an_edge_implementation(self, docs):
        """The core deployment does not require an Ingress or Gateway controller."""
        assert _find_kind(docs, "Ingress") is None
        assert _find_kind(docs, "HTTPRoute") is None

    def test_container_port(self, docs):
        """The container exposes port 8080."""
        dep = _find_kind(docs, "Deployment")
        container = dep["spec"]["template"]["spec"]["containers"][0]
        ports = container["ports"]
        assert any(p["containerPort"] == 8080 for p in ports)


class TestOptionalIngress:
    """Validate the controller-neutral Kubernetes Ingress."""

    @pytest.fixture
    def ingress(self):
        return _find_kind(_load_documents(_INGRESS_FILE), "Ingress")

    def test_class_and_hostname_are_operator_selected(self, ingress):
        assert ingress["spec"]["ingressClassName"] == "$INGRESS_CLASS_NAME"
        assert ingress["spec"]["rules"][0]["host"] == "$OIDC_ISSUER_FQDN"
        assert (
            ingress["metadata"]["annotations"]["cert-manager.io/cluster-issuer"]
            == "$CLUSTER_ISSUER_NAME"
        )

    def test_only_exact_oidc_endpoints_are_exposed(self, ingress):
        paths = ingress["spec"]["rules"][0]["http"]["paths"]
        assert {(item["path"], item["pathType"]) for item in paths} == {
            ("/.well-known/openid-configuration", "Exact"),
            ("/openid/v1/jwks", "Exact"),
        }
        assert all(
            item["backend"]["service"]
            == {"name": "kube-oidc-issuer-reflector", "port": {"number": 80}}
            for item in paths
        )


class TestOptionalGatewayApi:
    """Validate the implementation-neutral Gateway API HTTPRoute."""

    @pytest.fixture
    def route(self):
        return _find_kind(_load_documents(_GATEWAY_FILE), "HTTPRoute")

    def test_route_targets_an_operator_selected_https_listener(self, route):
        assert route["apiVersion"] == "gateway.networking.k8s.io/v1"
        assert route["spec"]["parentRefs"] == [
            {
                "name": "$GATEWAY_NAME",
                "namespace": "$GATEWAY_NAMESPACE",
                "sectionName": "$GATEWAY_LISTENER_NAME",
            }
        ]
        assert route["spec"]["hostnames"] == ["$OIDC_ISSUER_FQDN"]

    def test_only_exact_oidc_endpoints_are_exposed(self, route):
        rules = route["spec"]["rules"]
        assert {
            (rule["matches"][0]["path"]["value"], rule["matches"][0]["path"]["type"])
            for rule in rules
        } == {
            ("/.well-known/openid-configuration", "Exact"),
            ("/openid/v1/jwks", "Exact"),
        }
        assert all(
            rule["backendRefs"] == [{"name": "kube-oidc-issuer-reflector", "port": 80}]
            for rule in rules
        )


class TestOptionalIngressCertificateIssuer:
    """Validate the optional cert-manager Cloudflare API-token example."""

    @pytest.fixture
    def docs(self):
        return _load_documents(_CERT_ISSUER_FILE)

    def test_cloudflare_secret_uses_api_token(self, docs):
        secret = _find_kind(docs, "Secret")
        assert secret["metadata"] == {
            "name": "cloudflare-api-token-secret",
            "namespace": "cert-manager",
        }
        assert secret["stringData"] == {"api-token": "$CLOUDFLARE_API_TOKEN"}

    def test_cluster_issuer_references_api_token_without_global_key_email(self, docs):
        issuer = _find_kind(docs, "ClusterIssuer")
        cloudflare = issuer["spec"]["acme"]["solvers"][0]["dns01"]["cloudflare"]
        assert cloudflare == {
            "apiTokenSecretRef": {
                "name": "cloudflare-api-token-secret",
                "key": "api-token",
            }
        }
